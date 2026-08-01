"""Loading, aggregating and summarising per-game review data."""

import os
import re
import json
import glob
import html
import datetime

try:
    import sgfparse  # sibling module; used to recover boards from raw SGF
except Exception:
    sgfparse = None

from .constants import PHASES, PTS_BLUNDER, WR_BLUNDER


def load_config(path=None):
    import appconfig
    return appconfig.load_config(path)


def load_games(out_dir, games_dirs=None):
    games = []
    for p in sorted(glob.glob(os.path.join(out_dir, "*.json"))):
        if os.path.basename(p) in ("index.json", "notes.json", "practice_hidden.json"):
            continue
        with open(p, "r", encoding="utf-8") as f:
            g = json.load(f)
        _enrich_from_sgf(g, games_dirs or [])
        games.append(g)
    games.sort(key=lambda g: date_key(g), reverse=True)
    return games


def load_hidden(report_dir):
    """Set of blunder keys (filename#move) the user deleted from the practice
    set, read from <report_dir>/practice_hidden.json."""
    if not report_dir:
        return set()
    p = os.path.join(report_dir, "practice_hidden.json")
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def practice_cleared(report_dir):
    """True if the user has 'cleared' this project's blunder set (a finished
    project they won't review move-by-move again).  Marked by an empty file
    <report_dir>/practice_cleared."""
    return bool(report_dir and
                os.path.exists(os.path.join(report_dir, "practice_cleared")))


def _enrich_from_sgf(game, games_dirs):
    """Older analysis JSON lacks moves/setup/board_size (needed to draw boards).
    Recover them by re-reading the original SGF, matched by filename."""
    if game.get("moves") or sgfparse is None:
        return game
    fn = game.get("filename")
    if not fn:
        return game
    safe_fn = glob.escape(fn)  # filenames contain [..] which are glob wildcards
    for d in games_dirs:
        d = os.path.expanduser(d)
        for cand in glob.glob(os.path.join(d, "**", safe_fn), recursive=True):
            try:
                src = sgfparse.parse_sgf(cand)
            except Exception:
                continue
            game["moves"] = src["moves"]
            game["setup"] = src["setup"]
            game.setdefault("board_size", src["board_size"])
            return game
    return game


def esc(x):
    return html.escape(str(x))


# ---- dates -----------------------------------------------------------------

def parse_date(g):
    for s in (g.get("date", ""), g.get("filename", "")):
        m = re.search(r"(20\d{2})[-/_.]?(\d{2})[-/_.]?(\d{2})", s or "")
        if m:
            try:
                return datetime.date(int(m.group(1)), int(m.group(2)),
                                     int(m.group(3)))
            except ValueError:
                continue
    return None


def date_key(g):
    d = parse_date(g)
    return d.isoformat() if d else "0000-00-00"


def date_label(g):
    d = parse_date(g)
    return d.strftime("%m-%d") if d else "?"


# ---- per-game metrics ------------------------------------------------------

def blunder_count(g):
    """Union blunder count for a game: a move counts if it lost >= PTS_BLUNDER
    points OR dropped win-rate by >= WR_BLUNDER.  Recomputed from the move list
    so the figure is correct regardless of when the game was analysed/imported."""
    return sum(1 for m in g.get("all_user_moves", [])
               if (m.get("points_lost", 0) or 0) >= PTS_BLUNDER
               or (m.get("winrate_lost", 0) or 0) >= WR_BLUNDER)


def game_metrics(g):
    """Return {phase: {n, apl, br_pts, br_wr, blunders}} for one game."""
    moves = g.get("all_user_moves", [])
    out = {}
    for ph in PHASES:
        sub = moves if ph == "overall" else [m for m in moves
                                             if m.get("phase") == ph]
        n = len(sub)
        if n == 0:
            out[ph] = {"n": 0, "apl": None, "br_pts": None,
                       "br_wr": None, "blunders": 0}
            continue
        nb_pts = sum(1 for m in sub if m.get("points_lost", 0) >= PTS_BLUNDER)
        nb_wr = sum(1 for m in sub if m.get("winrate_lost", 0) >= WR_BLUNDER)
        nb_either = sum(1 for m in sub
                        if m.get("points_lost", 0) >= PTS_BLUNDER
                        or m.get("winrate_lost", 0) >= WR_BLUNDER)
        out[ph] = {
            "n": n,
            "apl": round(sum(m.get("points_lost", 0) for m in sub) / n, 2),
            "br_pts": round(nb_pts / n * 100, 1),
            "br_wr": round(nb_wr / n * 100, 1),
            "blunders": nb_either,
        }
    return out


# ---- aggregate + recommendations -------------------------------------------

def aggregate(games):
    all_moves = []
    for g in games:
        for m in g.get("all_user_moves", []):
            mm = dict(m)
            mm["game"] = g["filename"]
            mm["opponent"] = g.get("opponent", "")
            mm["date"] = g.get("date", "")
            all_moves.append(mm)

    def avg(xs):
        return round(sum(xs) / len(xs), 2) if xs else 0.0

    phase_vals = {"opening": [], "middlegame": [], "endgame": []}
    for m in all_moves:
        phase_vals.setdefault(m["phase"], []).append(m["points_lost"])

    blunders = sorted((m for m in all_moves
                       if m["points_lost"] >= PTS_BLUNDER
                       or (m.get("winrate_lost", 0) or 0) >= WR_BLUNDER),
                      key=lambda m: m["points_lost"], reverse=True)

    by_date = sorted(games, key=date_key)
    half = len(by_date) // 2 or 1

    def mean_apl(gs):
        v = [g["avg_points_lost"] for g in gs if g.get("n_user_moves")]
        return round(sum(v) / len(v), 2) if v else 0.0

    return {
        "n": len(games),
        "wins": sum(1 for g in games if g.get("won") is True),
        "losses": sum(1 for g in games if g.get("won") is False),
        "avg_points_lost": avg([m["points_lost"] for m in all_moves]),
        "phase_avg": {k: avg(v) for k, v in phase_vals.items()},
        "n_blunders": len(blunders),
        "blunder_rate": round(len(blunders) / max(1, len(all_moves)) * 100, 1),
        "top_blunders": blunders[:15],
        "trend_older": mean_apl(by_date[:half]),
        "trend_newer": mean_apl(by_date[half:]),
        "n_user_moves": len(all_moves),
        "avg_moves": (round(sum(len(g.get("moves", [])) for g in games)
                            / len(games)) if games else 0),
        "moves_counts": [len(g.get("moves", [])) for g in games],
    }


def recommendations(agg):
    recs = []
    pa = agg["phase_avg"]
    if agg["n_user_moves"] == 0:
        return ["No analysed moves yet."]
    phase_cn = {"opening": "the fuseki",
                "middlegame": "the middlegame",
                "endgame": "the yose"}
    if any(pa.values()):
        worst = max(pa, key=lambda k: pa[k])
        recs.append(
            f"Your biggest average loss is in {phase_cn[worst]} "
            f"(about {pa[worst]} pts/move) -- that is where study pays off most, "
            f"so work on it first.")
    if agg["blunder_rate"] > 4:
        recs.append(
            f"{agg['blunder_rate']}% of your moves are blunders (&ge;6 pts or win "
            f"rate &minus;15%). Cutting out obvious blunders raises your strength "
            f"faster than polishing good moves -- slow down in the positions below.")
    if pa.get("endgame", 0) >= 1.5:
        recs.append(
            "Your yose losses are noticeable. Getting into the habit of counting "
            "and taking the largest endgame plays first is a cheap, repeatable win.")
    if agg["trend_newer"] and agg["trend_older"]:
        if agg["trend_newer"] < agg["trend_older"]:
            recs.append(
                f"You are improving: recent games lose {agg['trend_newer']} pts per "
                f"move versus {agg['trend_older']} pts earlier on.")
        elif agg["trend_newer"] > agg["trend_older"] * 1.1:
            recs.append(
                f"Recent games ({agg['trend_newer']} pts/move) are slightly worse "
                f"than earlier ones ({agg['trend_older']} pts/move) -- tougher "
                f"opponents, or are you playing too fast?")
    recs.append(
        "Review with the practice diagrams below, then open the same move number in "
        "Lizzie to study KataGo's full variation.")
    return recs


def phase_label(k):
    return {"opening": "Fuseki", "middlegame": "Middlegame",
            "endgame": "Yose"}[k]


def source_label_from_path(path):
    """Derive a human-readable player/source label from the output folder name,
    e.g. '.../yehu_3d' -> 'Fox 3 dan', '.../fox_5k' -> 'Fox 5 kyu'."""
    base = os.path.basename((path or "").rstrip("/"))
    plat = "Fox" if re.search(r"yehu|fox|\u91ce\u72d0", base, re.I) else ""
    m = re.search(r"(\d+)\s*d\b", base, re.I)
    rank = f"{m.group(1)} dan" if m else ""
    if not rank:
        m = re.search(r"(\d+)\s*k\b", base, re.I)
        rank = f"{m.group(1)} kyu" if m else ""
    return " ".join(x for x in (plat, rank) if x)
