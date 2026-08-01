"""Analyze a batch of the user's recent games with ikatago and save results.

For every position we ask KataGo for its evaluation (winrate + score lead). For
each of the *user's* moves we compute "points lost" = (best move's score lead) -
(the move actually played's score lead), the same idea KaTrain uses. We also keep
a score-lead timeline (from Black's perspective) for a whole-game graph.

Output: one JSON file per game in OUTPUT_DIR, plus an index.json.
"""

import os
import re
import sys
import json
import glob
import time
import datetime

import sgfparse
import estimate_score as es
from gtp_engine import IkatagoEngine, GtpError


HERE = os.path.dirname(os.path.abspath(__file__))


def load_config(path=None):
    import appconfig
    return appconfig.load_config(path)


# ---- game selection --------------------------------------------------------
DATE_IN_NAME = re.compile(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})")
TRAILING_ID = re.compile(r"(\d+)\.sgf$", re.IGNORECASE)


def game_id_key(game):
    """Sort by the trailing numeric ID in the filename (a timestamp-based id).

    Newer games have larger ids, so sorting descending puts the newest first.
    Falls back to the date if no trailing number is present.
    """
    m = TRAILING_ID.search(game.get("filename", ""))
    if m:
        return (1, int(m.group(1)))
    # no trailing id: fall back to date string so these still order sensibly
    return (0, game_sort_key(game))


def game_sort_key(game):
    """Sort by date. Prefer the SGF DT field, fall back to the filename."""
    dt = game.get("date") or ""
    m = re.search(r"(20\d{2})[-/](\d{2})[-/](\d{2})", dt)
    if m:
        return m.group(1) + m.group(2) + m.group(3)
    m = DATE_IN_NAME.search(game.get("filename", ""))
    if m:
        return m.group(1) + m.group(2) + m.group(3)
    return "00000000"


def collect_games(cfg):
    paths = []
    for d in cfg["games_dirs"]:
        d = os.path.expanduser(d)
        paths.extend(glob.glob(os.path.join(d, "**", "*.sgf"), recursive=True))
    games = []
    for p in sorted(set(paths)):
        try:
            g = sgfparse.parse_sgf(p)
        except Exception as e:
            print(f"[skip] cannot parse {p}: {e}")
            continue
        color = sgfparse.detect_user_color(g, cfg["user_names"])
        if color is None:
            continue  # not the user's game (or name not recognised)
        if g["board_size"] != 19:
            continue  # keep it simple: 19x19 only
        g["user_color"] = color
        games.append(g)
    games.sort(key=game_id_key, reverse=True)
    return games


# ---- result helpers --------------------------------------------------------
def user_won(game):
    """Best-effort: did the user win? Returns True/False/None."""
    res = (game.get("result") or "")
    color = game["user_color"]
    # Western SGF style: RE[B+...] / RE[W+...]
    m = re.match(r"\s*([BW])\+", res)
    if m:
        return m.group(1) == color
    # Chinese style from yikeweiqi, e.g. "Black wins" / "White wins by resignation".
    # The SGF is written by the server in Chinese, so match on those characters.
    if "\u9ed1" in res and "\u80dc" in res:
        return color == "B"
    if "\u767d" in res and "\u80dc" in res:
        return color == "W"
    return None


def phase_of(move_number, total_moves):
    """Classify a move into opening / middlegame / endgame by progress."""
    if move_number <= 40:
        return "opening"
    if total_moves and move_number >= total_moves - 40:
        return "endgame"
    if move_number <= 100:
        return "middlegame"
    return "endgame" if total_moves and move_number > total_moves * 0.72 else "middlegame"


# ---- per-game analysis -----------------------------------------------------
def analyze_game(engine, game, cfg):
    bs = game["board_size"]
    engine.send("clear_board")
    engine.send(f"boardsize {bs}")
    engine.send(f"komi {game['komi']}")
    for color, coord in game["setup"]:
        if coord != "pass":
            engine.send(f"play {color} {coord}")

    moves = game["moves"]
    total = len(moves)
    visits = cfg.get("max_visits", 300)
    max_time = cfg.get("max_time_per_move", 12.0)
    move_cap = cfg.get("max_moves_per_game", 0)  # 0 = no cap

    timeline = []   # {move_number, black_score_lead, black_winrate}
    mistakes = []   # user moves with points lost
    per_move = []   # full record for the user's moves

    for idx, (color, coord) in enumerate(moves, start=1):
        if move_cap and idx > move_cap:
            break

        # Analyse the position *before* the move is played. Ask for ownership in
        # the SAME search -- it's a free byproduct of kata-analyze -- so we never
        # have to re-search a blunder position later just to draw its territory
        # overlay (that used to double the cost of every blunder).
        own = None
        try:
            infos, own = engine.analyze_with_ownership(max_visits=visits,
                                                        max_time=max_time)
        except GtpError as e:
            print(f"    [warn] analyze failed at move {idx}: {e}")
            infos = []
        if not infos:
            # ownership variant returned nothing (cloud rejected it): fall back to
            # a plain analysis so the move still gets evaluated.
            try:
                infos = engine.analyze(max_visits=visits, max_time=max_time)
            except GtpError:
                infos = []
            own = None

        if infos:
            best = infos[0]
            # Perspective: stats are for the side to move == `color`.
            stm_score = best.get("scoreLead", 0.0)
            stm_winrate = best.get("winrate", 0.5)
            black_score = stm_score if color == "B" else -stm_score
            black_winrate = stm_winrate if color == "B" else 1.0 - stm_winrate
            timeline.append({
                "move_number": idx,
                "black_score_lead": round(black_score, 2),
                "black_winrate": round(black_winrate, 4),
            })

            if color == game["user_color"] and coord != "pass":
                played = _find_candidate(infos, coord)
                best_score = best.get("scoreLead", 0.0)
                best_wr = best.get("winrate", 0.5)
                if played is not None:
                    played_score = played.get("scoreLead", best_score)
                    played_wr = played.get("winrate", best_wr)
                else:
                    # Move not in candidate list: evaluate it directly.
                    played_score, played_wr = _evaluate_specific_move(
                        engine, color, coord, visits, max_time)
                points_lost = max(0.0, best_score - played_score)
                winrate_lost = max(0.0, best_wr - played_wr)
                rec = {
                    "move_number": idx,
                    "played": coord,
                    "best": best.get("move"),
                    "best_pv": " ".join(best.get("pv", [])[:6]),
                    "points_lost": round(points_lost, 2),
                    "winrate_lost": round(winrate_lost, 4),
                    "phase": phase_of(idx, total),
                    "score_after_black": round(black_score, 2),
                }
                per_move.append(rec)
                if points_lost >= cfg.get("mistake_threshold", 2.0):
                    mistakes.append(rec)
                # For positions shown as "blunders" in the report, keep the
                # per-point ownership (KataGo's territory estimate) so the report
                # can draw the territory-estimate overlay. We already fetched it above as a
                # byproduct of this move's analysis -- no extra search needed.
                is_blunder = (points_lost >= cfg.get("blunder_threshold", 6.0)
                              or winrate_lost >= cfg.get("wr_blunder", 0.15))
                if is_blunder and own and len(own) == bs * bs:
                    _store_ownership(color, rec, bs, own)

        # Now actually play the move to advance the position.
        if coord == "pass":
            engine.send(f"play {color} pass")
        else:
            try:
                engine.send(f"play {color} {coord}")
            except GtpError as e:
                print(f"    [warn] illegal move {color} {coord} at {idx}: {e}")
                break

        # Visible heartbeat so a long game doesn't look frozen in the log.
        if idx % 10 == 0 or idx == total:
            print(f"    ... progress {idx}/{total} moves", flush=True)

    summary = summarize_game(game, timeline, per_move, mistakes, cfg)
    try:
        summary["final_score"] = final_score_estimate(engine, game, cfg)
    except Exception as e:
        print(f"    [warn] score estimate failed: {type(e).__name__}: {e}")
        summary["final_score"] = None
    return summary


def final_score_estimate(engine, game, cfg):
    """Score the *final* position: total lead + per-side and per-group territory.

    Replays the whole game onto the engine, then asks KataGo for ownership and
    derives an (approximate) per-group breakdown. Returns None if unavailable.
    """
    size = game["board_size"]
    komi = float(game.get("komi", 7.5))
    board, stm, _ = es.replay(game, None)

    engine.send("clear_board")
    engine.send(f"boardsize {size}")
    engine.send(f"komi {komi}")
    for color, coord in game.get("setup", []):
        if coord != "pass":
            engine.send(f"play {color} {coord}")
    played = 0
    for color, coord in game.get("moves", []):
        try:
            engine.send(f"play {color} {'pass' if coord == 'pass' else coord}")
        except GtpError as e:
            print(f"    [warn] engine rejected move {played + 1} {color} {coord} "
                  f"({e}); scoring the position reached so far")
            break
        played += 1
    # Re-sync the local board to the position the engine actually reached, so the
    # ownership map lines up with our group extraction.
    if played < len(game.get("moves", [])):
        board, stm, _ = es.replay(game, played)

    visits = cfg.get("score_visits", 600)
    max_time = cfg.get("score_max_time", 15.0)
    infos, own = engine.analyze_with_ownership(max_visits=visits,
                                               max_time=max_time)
    if not infos:
        # ownership variant returned nothing (unsupported / timed out) -- still
        # report the total lead from a plain analysis.
        print("    [warn] ownership read empty; falling back to score-only")
        infos = engine.analyze(max_visits=visits, max_time=max_time)
        own = None
    if not infos:
        return None

    score_lead_stm = infos[0].get("scoreLead", 0.0)
    score_black = score_lead_stm if stm == "B" else -score_lead_stm
    out = {"score_black": round(score_black, 1), "komi": komi,
           "moves_played": played}
    if own and len(own) == size * size:
        own_black = own if stm == "B" else [-v for v in own]
        sc = es.score_from_ownership(board, own_black, es.find_groups(board),
                                     komi)
        out.update({
            "black_area": sc["black_area"],
            "white_area": sc["white_area"],
            "net_area": sc["net_area"],
            "final_area": sc["final_area"],
            # raw per-point ownership (black perspective, row-major from top-left)
            # so the report can draw the territory-square overlay on the board.
            "ownership": [round(v, 2) for v in own_black],
            "own_size": size,
            # keep essentially all groups (only drop ones worth ~nothing) so the
            # per-side totals still add up to the area; the report aggregates the
            # small ones into a single row for readability.
            "groups": [g for g in sc["groups"] if g["points"] >= 0.05],
        })
    return out


def _store_ownership(color, rec, board_size, own):
    """Attach an already-fetched ownership map to `rec`, converted to a fixed
    Black perspective (row-major from top-left) plus each side's total.

    `own` comes from this move's own analysis (side-to-move perspective), so no
    extra engine search is performed here. Values rounded to 2 dp to keep the
    JSON small.
    """
    own_black = own if color == "B" else [-v for v in own]
    black_pts = round(sum(v for v in own_black if v > 0), 1)
    white_pts = round(sum(-v for v in own_black if v < 0), 1)
    rec["ownership"] = [round(v, 2) for v in own_black]
    rec["own_size"] = board_size
    rec["own_black_pts"] = black_pts
    rec["own_white_pts"] = white_pts


def _find_candidate(infos, gtp_move):
    target = gtp_move.upper()
    for c in infos:
        if (c.get("move") or "").upper() == target:
            return c
    return None


def _evaluate_specific_move(engine, color, coord, visits, max_time):
    """Play the move, analyse, undo. Returns (score_for_mover, winrate_for_mover)."""
    try:
        engine.send(f"play {color} {coord}")
    except GtpError:
        return 0.0, 0.5
    infos = []
    try:
        infos = engine.analyze(max_visits=max(80, visits // 2), max_time=max_time)
    except GtpError:
        pass
    try:
        engine.send("undo")
    except GtpError:
        pass
    if not infos:
        return 0.0, 0.5
    # After our move it's the opponent to move; negate to get our perspective.
    opp = infos[0]
    return -opp.get("scoreLead", 0.0), 1.0 - opp.get("winrate", 0.5)


def summarize_game(game, timeline, per_move, mistakes, cfg):
    blunder_threshold = cfg.get("blunder_threshold", 6.0)
    by_phase = {"opening": [], "middlegame": [], "endgame": []}
    for r in per_move:
        by_phase.setdefault(r["phase"], []).append(r["points_lost"])

    def avg(xs):
        return round(sum(xs) / len(xs), 2) if xs else 0.0

    wr_blunder = cfg.get("wr_blunder", 0.15)
    blunders = [r for r in per_move
                if r["points_lost"] >= blunder_threshold
                or (r.get("winrate_lost", 0) or 0) >= wr_blunder]
    summary = {
        "filename": game["filename"],
        "date": game["date"],
        "opponent": game["pw"] if game["user_color"] == "B" else game["pb"],
        "user_color": game["user_color"],
        "result": game["result"],
        "won": user_won(game),
        "komi": game["komi"],
        "board_size": game["board_size"],
        "setup": game["setup"],
        "moves": game["moves"],
        "n_user_moves": len(per_move),
        "avg_points_lost": avg([r["points_lost"] for r in per_move]),
        "avg_points_lost_by_phase": {k: avg(v) for k, v in by_phase.items()},
        "n_mistakes": len(mistakes),
        "n_blunders": len(blunders),
        "biggest_mistakes": sorted(per_move, key=lambda r: r["points_lost"],
                                   reverse=True)[:8],
        "timeline": timeline,
        "all_user_moves": per_move,
    }
    return summary


# ---- self-check (no engine) ------------------------------------------------
def selfcheck(cfg, limit):
    games = collect_games(cfg)[:limit]
    print(f"\nFound {len(games)} candidate game(s) (showing up to {limit}):\n")
    for g in games:
        opp = g["pw"] if g["user_color"] == "B" else g["pb"]
        print(f"  {game_sort_key(g)}  you={g['user_color']:<1}  "
              f"vs {opp:<16}  moves={len(g['moves']):<3}  "
              f"result={g['result']}  [{g['filename']}]")
    print("\nSelf-check OK. No engine was contacted.")


# ---- output bookkeeping ----------------------------------------------------
INDEX_FIELDS = ("filename", "date", "opponent", "user_color", "result",
                "won", "avg_points_lost", "n_blunders", "n_user_moves")


def out_name_for(filename):
    """Stable per-game JSON name, derived from the SGF filename."""
    return re.sub(r"[^\w.-]", "_", filename) + ".json"


def rebuild_index(out_dir):
    """Rebuild index.json from every per-game JSON currently on disk.

    This keeps previously analysed games in the report even though we only
    analyse new games on each run. Sorted newest-first by the trailing id.
    """
    rows = []
    for path in glob.glob(os.path.join(out_dir, "*.json")):
        if os.path.basename(path) in ("index.json", "notes.json", "practice_hidden.json"):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                s = json.load(f)
        except Exception as e:
            print(f"    [warn] cannot read {path}: {e}")
            continue
        row = {"file": os.path.basename(path)}
        for k in INDEX_FIELDS:
            row[k] = s.get(k)
        rows.append(row)

    def sort_key(row):
        m = TRAILING_ID.search(row.get("filename") or "")
        return (1, int(m.group(1))) if m else (0, 0)

    rows.sort(key=sort_key, reverse=True)
    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"generated": datetime.datetime.now().isoformat(),
                   "games": rows}, f, ensure_ascii=False, indent=2)
    return rows


# ---- main ------------------------------------------------------------------
def update_scores_only(cfg, out_dir, all_games):
    """Recompute only `final_score` for games that already have a JSON on disk.

    Much cheaper than a full re-analysis: for each game we just set up its final
    position and run a single ownership read, then patch the existing JSON.
    """
    targets = []
    for g in all_games:
        out_path = os.path.join(out_dir, out_name_for(g["filename"]))
        if os.path.exists(out_path):
            targets.append((g, out_path))
    if not targets:
        print("No analysed games found. Run analyze.py first, then --scores-only.")
        return 1

    engine = IkatagoEngine(cfg["ikatago_command"],
                           ready_timeout=cfg.get("ready_timeout", 120),
                           verbose=True)
    engine.start()
    try:
        for i, (g, out_path) in enumerate(targets, start=1):
            print(f"\n[{i}/{len(targets)}] scoring final position: {g['filename']}")
            try:
                fs = final_score_estimate(engine, g, cfg)
            except Exception as e:
                print(f"    [warn] score estimate failed: {type(e).__name__}: {e}")
                fs = None
            with open(out_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["final_score"] = fs
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            rebuild_index(out_dir)
    finally:
        engine.close()
    print(f"\nFinal-position scores updated in {out_dir}")
    return 0


def main(argv):
    cfg = load_config()
    limit = cfg.get("num_games", 30)

    if "--selfcheck" in argv:
        selfcheck(cfg, limit)
        return 0

    out_dir = os.path.expanduser(cfg["output_dir"])
    os.makedirs(out_dir, exist_ok=True)
    force = ("--force" in argv) or ("--reanalyze" in argv)

    all_games = collect_games(cfg)
    if not all_games:
        print("No games matched your names in the configured folders. "
              "Check 'user_names' and 'games_dirs' in config.json.")
        return 1

    # Final-score-only mode: refresh just the final-position score estimate on games that
    # are already analysed, WITHOUT redoing the per-move analysis. This only
    # asks KataGo to evaluate each game's final position once.
    if ("--scores-only" in argv) or ("--score-only" in argv):
        return update_scores_only(cfg, out_dir, all_games)

    # Skip games we've already analysed (a per-game JSON already exists),
    # so re-running only picks up new games. Use --force to re-analyse all.
    pending = []
    skipped = 0
    for g in all_games:
        out_path = os.path.join(out_dir, out_name_for(g["filename"]))
        if not force and os.path.exists(out_path):
            skipped += 1
            continue
        pending.append(g)

    games = pending[:limit]
    if skipped:
        print(f"Skipping {skipped} already-analysed game(s). "
              f"(Use --force to re-analyse everything.)")
    if not games:
        print("No new games to analyse — everything is already up to date.")
        # still refresh the index from whatever is on disk
        rebuild_index(out_dir)
        return 0

    engine = IkatagoEngine(cfg["ikatago_command"],
                           ready_timeout=cfg.get("ready_timeout", 120),
                           verbose=True)
    engine.start()

    try:
        for i, g in enumerate(games, start=1):
            print(f"\n[{i}/{len(games)}] {g['filename']} "
                  f"(you={g['user_color']}, {len(g['moves'])} moves)")
            t0 = time.time()
            summary = analyze_game(engine, g, cfg)
            dt = time.time() - t0
            out_name = out_name_for(g["filename"])
            with open(os.path.join(out_dir, out_name), "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            print(f"    done in {dt:.0f}s | avg points lost "
                  f"{summary['avg_points_lost']} | blunders {summary['n_blunders']}")
            # incremental save so a crash doesn't lose everything; rebuild the
            # index from every per-game JSON on disk so previously analysed
            # games stay in the report.
            rebuild_index(out_dir)
    finally:
        engine.close()

    print(f"\nAnalysis complete. Per-game JSON written to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
