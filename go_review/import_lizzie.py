"""Convert a LizzieYZY analysed SGF into the review report's per-game
JSON, with NO engine call.

LizzieYZY stores KataGo analysis inline in the SGF:
  * the root node carries  LZOP[...]   -- analysis of the empty board (before B1)
  * every move node carries LZ[...]     -- analysis of the position *after* that
                                            move was played

So to evaluate the move played at node i we read the *before* analysis, which is
the LZ of node (i-1)  (or LZOP for i == 1).  We find the candidate whose move ==
the coordinate actually played and compare its winrate / scoreMean to the best
candidate (listed first).  This mirrors analyze.analyze_game exactly, only the
numbers come from the SGF instead of a live engine.

Pure standard library.  No KataGo, no Java.
"""

import argparse
import hashlib
import json
import os
import re
import sys

import analyze
import estimate_score as es
import report
import sgfparse


# ---------------------------------------------------------------------------
# 1. SGF node scanner  (bracket/escape aware)
# ---------------------------------------------------------------------------
def _scan_nodes(text):
    """Split SGF text into a list of nodes; each node is a list of
    (property_ident, [values]).  Bracket- and backslash-escape aware."""
    nodes = []
    cur = None            # current node: list of (ident, [vals])
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == ';':
            cur = []
            nodes.append(cur)
            i += 1
            continue
        if c in '()':
            i += 1
            continue
        if c.isspace():
            i += 1
            continue
        # property identifier: uppercase letters
        m = re.match(r'[A-Za-z]+', text[i:])
        if not m or cur is None:
            i += 1
            continue
        ident = m.group(0)
        i += len(ident)
        vals = []
        # one or more [value] groups
        while i < n and text[i] == '[':
            i += 1
            start = i
            buf = []
            while i < n:
                ch = text[i]
                if ch == '\\':       # escape: take next char literally
                    if i + 1 < n:
                        buf.append(text[i + 1])
                    i += 2
                    continue
                if ch == ']':
                    break
                buf.append(ch)
                i += 1
            vals.append(''.join(buf))
            i += 1               # skip closing ']'
            # skip whitespace between consecutive value groups
            while i < n and text[i].isspace():
                i += 1
        cur.append((ident, vals))
    return nodes


def _node_prop(node, ident):
    for k, vals in node:
        if k == ident:
            return vals[0] if vals else ''
    return None


# ---------------------------------------------------------------------------
# 2. LZ block parser  ->  candidates + ownership
# ---------------------------------------------------------------------------
# A candidate looks like:
#   move Q16 visits 1234 winrate 6236 prior 850 scoreMean -1.23 pv Q16 D16 ...
# winrate is an integer = pct * 100  (6236 -> 0.6236).  Several candidates are
# separated by ' info '.  An 'ownership' section (361 floats) follows.
_NUM = r'-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?'
_CAND_RE = re.compile(
    r'move\s+(\S+)\s+visits\s+(\d+)\s+winrate\s+(' + _NUM + r')'
    r'(?:\s+\S+\s+\S+)*?\s+scoreMean\s+(' + _NUM + r')'
    r'(?:\s+\S+\s+\S+)*?\s+pv\s+([A-Za-z0-9 ]+?)(?=\s+info\b|\s+ownership\b|$)'
)


def _norm_winrate(raw):
    """Normalise a candidate's winrate to a 0..1 fraction.

    LizzieYZY/KataGo lz-analyze stores winrate as an INTEGER per-ten-thousand
    (0..10000): e.g. 9998 -> 0.9998, and 1 -> 0.0001 (≈0%, NOT 100%).  In
    decided endgames the losing side's candidates show tiny integers like 0/1/2;
    a naive ">1.5 ? /10000 : raw" rule misread '1' as 1.0 (100%) and produced
    bogus ~100% win-rate swings.  Integers are always /10000; a value written
    with a decimal point is treated as a 0-1 fraction (or 0-100 percent)."""
    raw = (raw or "").strip()
    try:
        if "." in raw or "e" in raw or "E" in raw:
            f = float(raw)
            wr = f if f <= 1.0 else f / 100.0
        else:
            wr = int(raw) / 10000.0
    except ValueError:
        return 0.0
    return 0.0 if wr < 0 else (1.0 if wr > 1.0 else wr)


def parse_lz(block):
    """Return {'cands': [ {move, visits, winrate(0-1), score, pv:[..]} ... ],
                'own': [floats] or None }.  Candidates best-first (as stored)."""
    if not block:
        return {"cands": [], "own": None}

    own = None
    mo = re.search(r'\bownership\b\s+(.*)$', block, re.DOTALL)
    if mo:
        nums = re.findall(_NUM, mo.group(1))
        own = [float(x) for x in nums]
        block = block[:mo.start()]

    cands = []
    for m in _CAND_RE.finditer(block):
        move = m.group(1).upper()
        visits = int(m.group(2))
        winrate = _norm_winrate(m.group(3))
        score = float(m.group(4))
        pv = m.group(5).split()
        cands.append({"move": move, "visits": visits, "winrate": winrate,
                      "score": score, "pv": pv})
    return {"cands": cands, "own": own}


# ---------------------------------------------------------------------------
# 3. Extract per-node analysis aligned to the move list
# ---------------------------------------------------------------------------
def extract_analysis(path):
    """Return (game, before_list) where:
       game        = sgfparse.parse_sgf(path)  (board_size, komi, moves, ...)
       before_list = list aligned to game['moves']; before_list[i] is the
                     parsed LZ describing the position *before* move i+1.
       Also returns after_last = parsed LZ after the final move (for scoring)."""
    text = open(path, encoding='utf-8', errors='replace').read()
    game = sgfparse.parse_sgf(path)
    # Only scan the main line; analysis SGFs embed candidate variations as real
    # sub-trees, which would otherwise inflate the move/LZ list (and misalign it
    # with game['moves']).
    nodes = _scan_nodes(sgfparse.main_line_text(text))

    root_lz = None
    move_lz = []          # parsed LZ that each move node carries (= AFTER state)
    for nd in nodes:
        lzop = _node_prop(nd, 'LZOP')
        if lzop is not None and root_lz is None:
            root_lz = parse_lz(lzop)
        # is this a move node?
        has_move = any(k in ('B', 'W') for k, _ in nd)
        if has_move:
            lz = _node_prop(nd, 'LZ')
            move_lz.append(parse_lz(lz) if lz is not None else
                           {"cands": [], "own": None})

    empty = {"cands": [], "own": None}
    n_moves = len(game['moves'])
    # before[i] = analysis of the position BEFORE move i+1
    #   i == 0 -> root LZOP ; i >= 1 -> LZ of move node i (= after move i)
    # after[i] = analysis of the position AFTER move i+1 = LZ of move node i+1
    before, after = [], []
    for i in range(n_moves):
        if i == 0:
            before.append(root_lz or empty)
        else:
            before.append(move_lz[i - 1] if i - 1 < len(move_lz) else empty)
        after.append(move_lz[i] if i < len(move_lz) else empty)
    after_last = move_lz[-1] if move_lz else None
    return game, before, after, after_last


# ---------------------------------------------------------------------------
# 4. Build the per-game summary  (mirrors analyze.analyze_game, no engine)
# ---------------------------------------------------------------------------
def _find_cand(cands, gtp_move):
    t = (gtp_move or '').upper()
    for c in cands:
        if c['move'] == t:
            return c
    return None


def build_summary(game, before, after, after_last, cfg):
    bs = game['board_size']
    moves = game['moves']
    total = len(moves)
    user_color = game['user_color']

    timeline, per_move, mistakes = [], [], []
    mistake_t = cfg.get('mistake_threshold', 2.0)
    blunder_t = cfg.get('blunder_threshold', 6.0)
    wr_blunder = cfg.get('wr_blunder') or 0.15

    for idx, (color, coord) in enumerate(moves, start=1):
        an = before[idx - 1]
        cands = an['cands']
        if not cands:
            continue
        best = cands[0]
        # LZ winrate/score are side-to-move perspective (== `color`).
        stm_score = best['score']
        stm_wr = best['winrate']
        black_score = stm_score if color == 'B' else -stm_score
        black_wr = stm_wr if color == 'B' else 1.0 - stm_wr
        timeline.append({
            "move_number": idx,
            "black_score_lead": round(black_score, 2),
            "black_winrate": round(black_wr, 4),
        })

        if color == user_color and coord != 'pass':
            # Evaluate the played move from the AFTER position (a dedicated
            # KataGo search of the resulting board), negated to the mover's
            # perspective.  This matches what LizzieYZY itself reports as the
            # move's winrate (verified against the SGF's own move-difference list) and is
            # more accurate than the shallow before-candidate visit counts.
            aft = after[idx - 1]
            if aft and aft['cands']:
                opp = aft['cands'][0]
                played_score = -opp['score']
                played_wr = 1.0 - opp['winrate']
            else:
                played = _find_cand(cands, coord)
                if played is not None:
                    played_score = played['score']
                    played_wr = played['winrate']
                else:
                    played_score, played_wr = best['score'], best['winrate']
            points_lost = max(0.0, best['score'] - played_score)
            winrate_lost = max(0.0, best['winrate'] - played_wr)
            rec = {
                "move_number": idx,
                "played": coord,
                "best": best['move'],
                "best_pv": " ".join(best['pv'][:6]),
                "points_lost": round(points_lost, 2),
                "winrate_lost": round(winrate_lost, 4),
                "phase": analyze.phase_of(idx, total),
                "score_after_black": round(black_score, 2),
            }
            per_move.append(rec)
            if points_lost >= mistake_t:
                mistakes.append(rec)
            is_blunder = (points_lost >= blunder_t or winrate_lost >= wr_blunder)
            own = an['own']
            if is_blunder and own and len(own) == bs * bs:
                analyze._store_ownership(color, rec, bs, own)

    summary = analyze.summarize_game(game, timeline, per_move, mistakes, cfg)
    summary['final_score'] = _final_score(game, after_last, cfg)
    return summary


def _final_score(game, after_last, cfg):
    """Estimate the final score from the last move node's ownership map."""
    if not after_last or not after_last.get('own'):
        return None
    size = game['board_size']
    komi = float(game.get('komi', 7.5))
    own = after_last['own']
    if len(own) != size * size:
        return None
    board, stm, _ = es.replay(game, None)
    own_black = own if stm == 'B' else [-v for v in own]
    cands = after_last['cands']
    score_stm = cands[0]['score'] if cands else 0.0
    score_black = score_stm if stm == 'B' else -score_stm
    sc = es.score_from_ownership(board, own_black, es.find_groups(board), komi)
    return {
        "score_black": round(score_black, 1),
        "komi": komi,
        "moves_played": len(game['moves']),
        "black_area": sc['black_area'],
        "white_area": sc['white_area'],
        "net_area": sc['net_area'],
        "final_area": sc['final_area'],
        "ownership": [round(v, 2) for v in own_black],
        "own_size": size,
        "groups": [g for g in sc['groups'] if g['points'] >= 0.05],
    }


# ---------------------------------------------------------------------------
# 5. Routing, de-duplication and report rebuild
# ---------------------------------------------------------------------------
DEFAULTS = {
    # The user's own handle on Fox.  Case-insensitive substring match against the
    # SGF player fields decides "personal" vs "study".
    "personal_name": "cxw1990",
    # Where the personal report lives (already holds the user's analysed games).
    "personal_dir": "yehu_3d",
    # Root under which per-player study folders (study_<name>/) are created.
    "study_root": "study",
}


def _safe_name(name):
    """Filesystem-safe player-folder name."""
    s = re.sub(r"\s+", "", name or "")
    s = re.sub(r"[^\w.-]", "_", s, flags=re.UNICODE)
    return s or "unknown"


def _signature(game):
    """Stable content id for a game: players + date + move sequence."""
    h = hashlib.sha1()
    parts = [game.get("pb", ""), game.get("pw", ""), game.get("date", ""),
             str(game.get("komi", "")),
             ";".join(f"{c}{m}" for c, m in game.get("moves", []))]
    h.update("|".join(parts).encode("utf-8", "replace"))
    return h.hexdigest()


def _existing_signatures(out_dir):
    """Two maps for de-duplication, both keyed to a json path:
       (signature -> path, source_filename -> path).
    The filename map lets a re-import of the same SGF overwrite the old entry
    even if its content signature changed (e.g. after a parser fix)."""
    sigs, names = {}, {}
    if not os.path.isdir(out_dir):
        return sigs, names
    for fn in os.listdir(out_dir):
        if not fn.endswith(".json") or fn in ("index.json", "notes.json", "practice_hidden.json"):
            continue
        try:
            with open(os.path.join(out_dir, fn), encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        path = os.path.join(out_dir, fn)
        sig = d.get("game_id")
        if sig:
            sigs[sig] = path
        src = d.get("filename")
        if src:
            names[src] = path
    return sigs, names


def _ask(prompt, choices):
    """Interactive choice; returns one of `choices`.  Non-tty -> first choice."""
    if not sys.stdin or not sys.stdin.isatty():
        return choices[0]
    while True:
        ans = input(prompt).strip().lower()
        for c in choices:
            if ans == c or ans == c[0]:
                return c


def _emit(summary, game, out_dir, sig, on_dup):
    """Write one per-game JSON into out_dir, honouring de-duplication.

    Returns ('written'|'overwritten'|'skipped', path)."""
    os.makedirs(out_dir, exist_ok=True)
    existing, by_name = _existing_signatures(out_dir)
    # Same game already present?  Match by content signature, or by source SGF
    # filename (so re-importing after a parser change overwrites, not duplicates).
    dup_path = existing.get(sig) or by_name.get(summary.get("filename"))
    if dup_path:
        action = on_dup
        if action == "ask":
            print(f"  ! this game is already present: {os.path.basename(dup_path)}")
            action = _ask("    overwrite or skip? [overwrite/skip] ",
                          ["skip", "overwrite"])
        if action == "skip":
            return "skipped", dup_path
        summary["game_id"] = sig
        with open(dup_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False)
        return "overwritten", dup_path

    base = analyze.out_name_for(game["filename"])
    path = os.path.join(out_dir, base)
    if os.path.exists(path):           # name clash, different game
        path = os.path.join(out_dir, base[:-5] + "-" + sig[:8] + ".json")
    summary["game_id"] = sig
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False)
    return "written", path


def rebuild_report(out_dir, games_dirs=None):
    """Rebuild review_report.html for a folder of per-game JSON."""
    games = report.load_games(out_dir, games_dirs or [])
    if not games:
        return None
    agg = report.aggregate(games)
    agg["source_label"] = report.source_label_from_path(out_dir)
    recs = report.recommendations(agg)
    out_path = os.path.join(out_dir, "review_report.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report.build_html(games, agg, recs, report_dir=out_dir))
    return out_path


def _detect_subject(game, names):
    """Which colour is the review subject?  First name (case-insensitive
    substring) that matches a player field wins; else None."""
    return sgfparse.detect_user_color(game, [n for n in names if n])


def list_report_dirs(base=None):
    """Existing report folders under `base` (those holding per-game JSON or a
    review_report.html).  Returns absolute paths, sorted."""
    base = base or os.path.dirname(os.path.abspath(__file__))
    found = []
    for root, dirs, files in os.walk(base):
        # don't descend into hidden / vcs dirs
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        has = ("review_report.html" in files or
               any(f.endswith(".json") and f not in ("index.json", "notes.json", "practice_hidden.json")
                   for f in files))
        if has and root != base:
            found.append(os.path.abspath(root))
    return sorted(found)


def run_import(paths, target_dir, cfg, subject_name=None, personal_name=None,
               on_dup="skip", games_dirs=None, rebuild=True, log=print):
    """High-level entry used by the GUI.  Imports every .sgf in `paths`
    (files or folders) into `target_dir`, then rebuilds that report.
    Returns (n_imported, report_path_or_None)."""
    files = []
    for p in paths:
        p = os.path.expanduser(p)
        if os.path.isdir(p):
            for fn in sorted(os.listdir(p)):
                if fn.lower().endswith(".sgf"):
                    files.append(os.path.join(p, fn))
        elif p.lower().endswith(".sgf"):
            files.append(p)
    if not files:
        log("No .sgf files found.")
        return 0, None

    opts = {
        "target_dir": target_dir,
        "subject_name": subject_name,
        "personal_name": personal_name
            or cfg.get("import_personal_name", DEFAULTS["personal_name"]),
        "on_dup": on_dup,
    }
    n = 0
    for f in files:
        log(f"Importing {os.path.basename(f)} ...")
        try:
            if import_sgf(f, opts, cfg):
                n += 1
        except Exception as e:                      # noqa: BLE001
            log(f"  [error] {type(e).__name__}: {e}")

    report_path = None
    if rebuild:
        report_path = rebuild_report(os.path.abspath(target_dir),
                                     games_dirs or cfg.get("games_dirs", []))
        if report_path:
            log(f"Report updated: {report_path}")
    log(f"Done. Processed {len(files)} file(s), imported {n} game(s).")
    return n, report_path


def import_sgf(path, opts, cfg):
    """Convert one analysed SGF and route its JSON.  Returns list of dirs
    whose report needs rebuilding.

    Two modes:
      * single-target  (opts['target_dir'] set): every game is written into
        that one report folder.  The review subject is detected from
        opts['subject_name'] then personal_name; if neither is a player the
        subject defaults to Black.
      * auto-routing   (no target_dir): personal_name's games go to
        personal_dir; other games split into per-player study_<name>/ folders.
    """
    game, before, after, after_last = extract_analysis(path)
    # Skip SGFs that carry no KataGo analysis (e.g. a raw Fox download sitting in
    # the same folder as the analysed copy) — importing them would create an
    # empty, duplicate game record.
    if not any(c["cands"] for c in before) and not any(c["cands"] for c in after):
        print(f"  skipped (no analysis data): {os.path.basename(path)}")
        return []
    pb, pw = game.get("pb", ""), game.get("pw", "")
    pname = (opts.get("personal_name") or "").lower()
    sig = _signature(game)
    touched = []

    base = os.path.dirname(os.path.abspath(__file__))
    def resolve(d):
        return d if os.path.isabs(d) else os.path.join(base, d)

    # ---- single-target mode -------------------------------------------------
    if opts.get("target_dir"):
        color = _detect_subject(game, [opts.get("subject_name"),
                                       opts.get("personal_name")]) or "B"
        game["user_color"] = color
        summary = build_summary(game, before, after, after_last, cfg)
        out_dir = resolve(opts["target_dir"])
        status, p = _emit(summary, game, out_dir, sig, opts["on_dup"])
        opp = pw if color == "B" else pb
        print(f"  [{color} vs {opp}] {status} -> {os.path.basename(p)}")
        if status != "skipped":
            touched.append(out_dir)
        return touched

    # ---- auto-routing mode --------------------------------------------------
    # personal?  cxw1990 substring-matches a player field.
    personal_side = None
    if pname and pname in (pb or "").lower():
        personal_side = "B"
    elif pname and pname in (pw or "").lower():
        personal_side = "W"

    if personal_side:
        game["user_color"] = personal_side
        summary = build_summary(game, before, after, after_last, cfg)
        out_dir = resolve(opts["personal_dir"])
        status, p = _emit(summary, game, out_dir, sig, opts["on_dup"])
        opp = pw if personal_side == "B" else pb
        print(f"  [personal] {personal_side} vs {opp}: {status} -> "
              f"{os.path.basename(p)}")
        if status != "skipped":
            touched.append(out_dir)
        return touched

    # study game: one report per player, that player as the subject.
    for side, name in (("B", pb), ("W", pw)):
        if not name:
            continue
        game["user_color"] = side
        summary = build_summary(game, before, after, after_last, cfg)
        out_dir = os.path.join(resolve(opts["study_root"]),
                               "study_" + _safe_name(name))
        status, p = _emit(summary, game, out_dir, sig, opts["on_dup"])
        print(f"  [study:{_safe_name(name)}] subject {side}: {status} -> "
              f"{os.path.basename(p)}")
        if status != "skipped":
            touched.append(out_dir)
    return touched


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Import LizzieYZY analysed SGF(s) into the review report.")
    ap.add_argument("paths", nargs="+", help="analysed .sgf file(s) or folder(s)")
    ap.add_argument("--personal-name", default=None)
    ap.add_argument("--personal-dir", default=None)
    ap.add_argument("--study-root", default=None)
    ap.add_argument("--target", default=None,
                    help="single-target mode: put every game into this report "
                         "folder (overrides personal/study routing)")
    ap.add_argument("--subject", default=None,
                    help="single-target mode: player name to review as subject")
    ap.add_argument("--on-dup", choices=["ask", "skip", "overwrite"],
                    default="ask")
    ap.add_argument("--no-rebuild", action="store_true",
                    help="write JSON only; don't regenerate HTML")
    args = ap.parse_args(argv)

    try:
        cfg = analyze.load_config()
    except Exception:
        cfg = {}
    opts = {
        "personal_name": args.personal_name
            or cfg.get("import_personal_name", DEFAULTS["personal_name"]),
        "personal_dir": args.personal_dir
            or cfg.get("import_personal_dir", DEFAULTS["personal_dir"]),
        "study_root": args.study_root
            or cfg.get("import_study_root", DEFAULTS["study_root"]),
        "target_dir": args.target,
        "subject_name": args.subject,
        "on_dup": args.on_dup,
    }

    # expand files / folders
    files = []
    for p in args.paths:
        p = os.path.expanduser(p)
        if os.path.isdir(p):
            for fn in sorted(os.listdir(p)):
                if fn.lower().endswith(".sgf"):
                    files.append(os.path.join(p, fn))
        elif p.lower().endswith(".sgf"):
            files.append(p)
    if not files:
        print("No .sgf files found.")
        return 1

    games_dirs = cfg.get("games_dirs", [])
    touched = set()
    for f in files:
        print(f"Importing {os.path.basename(f)} ...")
        try:
            for d in import_sgf(f, opts, cfg):
                touched.add(d)
        except Exception as e:
            print(f"  [error] {type(e).__name__}: {e}")

    if not args.no_rebuild:
        for d in sorted(touched):
            out = rebuild_report(d, games_dirs)
            if out:
                print(f"Report updated: {out}")
    print(f"Done. Imported {len(files)} game(s), updated {len(touched)} report(s).")
    return 0


if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[1] == "--calib":
        path = sys.argv[2]
        game, before, after, after_last = extract_analysis(path)
        print("players  B=%r  W=%r  moves=%d  komi=%s  size=%d" % (
            game['pb'], game['pw'], len(game['moves']), game['komi'],
            game['board_size']))
        print("root cands:", len(before[0]['cands']),
              "own:", None if before[0]['own'] is None else len(before[0]['own']))
    else:
        sys.exit(main())
