"""Turn cached Skill Test runs into the numbers worth looking at.

The interesting question is not "how many did I get wrong" but *how* I got them
wrong, and the crowd move tree makes that answerable. For every failed attempt
we can tell apart:

  * trap        -- I played a move the site knows is wrong, and lots of other
                   players play it too. A shared misconception: learn the shape
                   once and a whole class of problems stops costing points.
  * off_book    -- I played a move that is not in the answer tree, and almost
                   nobody else plays. An idiosyncratic misread (or a guess).
  * depth       -- I started down the correct line and left it at move k. The
                   idea was right; the reading ran out. This is the one that
                   responds to "read to the end before you play".

Those three want completely different training, which is the whole point of
separating them.
"""

import math
import datetime
from collections import Counter, defaultdict

from .api import pt_to_gtp

CORRECT = 1          # myan.result
WRONG = 2

# node["s"] in the crowd tree
S_OK = "o"           # on a correct line
S_FAIL = "f"         # on a known losing line
S_OFF = "c"          # played by humans but not part of the answer tree


def _children(diagram, node_id):
    node = diagram.get(str(node_id)) or diagram.get(node_id)
    if not node:
        return []
    out = []
    for sid in node.get("subs", []):
        child = diagram.get(str(sid)) or diagram.get(sid)
        if child:
            out.append(child)
    return out


def first_move_distribution(diagram):
    """The opening-move split: what everyone played, most popular first."""
    if not diagram:
        return []
    root = diagram.get("0") or diagram.get(0)
    if not root:
        return []
    total = root.get("num") or 0
    kids = _children(diagram, 0)
    kids.sort(key=lambda c: c.get("num", 0), reverse=True)
    return [{
        "pt": c.get("pt", ""),
        "gtp": pt_to_gtp(c.get("pt", "")),
        "num": c.get("num", 0),
        "share": (c.get("num", 0) / total) if total else 0.0,
        "status": c.get("s", S_OFF),
    } for c in kids]


def walk_my_line(diagram, moves):
    """Follow my actual moves down the crowd tree.

    Returns (nodes, diverge_at) where diverge_at is the index of my first move
    that was not on a correct line, or None if I never left it. Only my own
    moves are checked -- the tree alternates colours, so we step two at a time.
    """
    if not diagram or not moves:
        return [], 0
    nodes = []
    cur = 0
    diverge_at = None
    for i, mv in enumerate(moves):
        match = None
        for c in _children(diagram, cur):
            if c.get("pt") == mv:
                match = c
                break
        if match is None:
            if diverge_at is None and i % 2 == 0:
                diverge_at = i // 2
            break
        nodes.append(match)
        if match.get("s") != S_OK and diverge_at is None and i % 2 == 0:
            diverge_at = i // 2
        cur = match.get("id")
    return nodes, diverge_at


def classify(question, diagram):
    """Diagnose a single attempt. See the module docstring for the taxonomy."""
    moves = question.get("moves") or []
    dist = first_move_distribution(diagram)
    by_pt = {d["pt"]: d for d in dist}
    mine = by_pt.get(moves[0]) if moves else None
    best = next((d for d in dist if d["status"] == S_OK), None)
    top = dist[0] if dist else None

    out = {
        "qid": question.get("qid"),
        "publicid": question.get("publicid"),
        "levelname": question.get("levelname"),
        "qtypename": question.get("qtypename") or "Unknown",
        "n": question.get("n"),
        "costtime": question.get("costtime") or 0,
        "at": question.get("at"),
        "result": question.get("result"),
        "my_first": pt_to_gtp(moves[0]) if moves else "",
        "my_first_share": mine["share"] if mine else 0.0,
        "my_first_status": mine["status"] if mine else "unseen",
        "best_move": best["gtp"] if best else "",
        "best_share": best["share"] if best else 0.0,
        "top_move": top["gtp"] if top else "",
        "top_share": top["share"] if top else 0.0,
        "n_moves": len(moves),
        "crowd_rate": crowd_rate(question),
        "vote": question.get("vote"),
        "dist": dist[:6],
    }

    if question.get("result") == CORRECT:
        out["kind"] = "correct"
        out["diverge_at"] = None
        return out

    _, diverge_at = walk_my_line(diagram, moves)
    out["diverge_at"] = diverge_at
    if diverge_at is not None and diverge_at > 0:
        out["kind"] = "depth"
    elif out["my_first_status"] == S_FAIL:
        out["kind"] = "trap"
    else:
        out["kind"] = "off_book"
    return out


def crowd_rate(question):
    """Share of all players who solve this problem."""
    yes = question.get("yes") or 0
    no = question.get("no") or 0
    return yes / (yes + no) if (yes + no) else None


# -- aggregation ---------------------------------------------------------
LEVEL_NAMES = {  # `number` in the run index -> the label the site shows
    1: "15级", 2: "14级", 3: "13级", 4: "12级", 5: "11级", 6: "10级",
    7: "9级", 8: "8级", 9: "7级", 10: "6级", 11: "5级", 12: "4级",
    13: "3级", 14: "2级", 15: "1级", 16: "1段", 17: "2段", 18: "3段",
}


def level_label(number):
    return LEVEL_NAMES.get(number, f"level {number}")


def _rate(rows, pred=lambda a: a["result"] == CORRECT):
    if not rows:
        return None
    return sum(1 for a in rows if pred(a)) / len(rows)


def analyse(runs, load_diagram):
    """Build every table the dashboard renders."""
    attempts = []
    for run in runs:
        for q in run.get("questions", []):
            a = classify(q, load_diagram(q.get("qid")) or {})
            a["guanid"] = run.get("guanid")
            a["number"] = run.get("number")
            a["level"] = level_label(run.get("number"))
            a["run_t"] = run.get("t")
            attempts.append(a)
    attempts.sort(key=lambda a: a.get("at") or a.get("run_t") or 0)

    failed = [a for a in attempts if a["result"] != CORRECT]
    kinds = Counter(a["kind"] for a in failed)

    # accuracy per level
    by_level = defaultdict(list)
    for a in attempts:
        by_level[a["number"]].append(a)
    levels = [{
        "number": num,
        "label": level_label(num),
        "n": len(rows),
        "accuracy": _rate(rows),
        "runs": len({r["guanid"] for r in rows}),
        "kinds": Counter(r["kind"] for r in rows if r["result"] != CORRECT),
        "median_time": _median([r["costtime"] for r in rows if r["costtime"]]),
    } for num, rows in sorted(by_level.items())]

    # accuracy per problem type
    by_type = defaultdict(list)
    for a in attempts:
        by_type[a["qtypename"]].append(a)
    types = sorted(({
        "name": name,
        "n": len(rows),
        "accuracy": _rate(rows),
        "kinds": Counter(r["kind"] for r in rows if r["result"] != CORRECT),
    } for name, rows in by_type.items()), key=lambda d: -d["n"])

    # does accuracy decay through a run?
    by_pos = defaultdict(list)
    for a in attempts:
        by_pos[a["n"]].append(a)
    positions = [{
        "n": n,
        "count": len(rows),
        "accuracy": _rate(rows),
        "median_time": _median([r["costtime"] for r in rows if r["costtime"]]),
    } for n, rows in sorted(by_pos.items()) if n]

    # how long did I think, and did it help?
    buckets = [(0, 10), (10, 20), (20, 40), (40, 70), (70, 120), (120, 10 ** 6)]
    times = []
    for lo, hi in buckets:
        rows = [a for a in attempts if lo <= (a["costtime"] or 0) < hi]
        times.append({
            "label": f"{lo}-{hi}s" if hi < 10 ** 6 else f"{lo}s+",
            "count": len(rows),
            "accuracy": _rate(rows),
        })

    # am I missing problems that most people get right?
    diff_buckets = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]
    difficulty = []
    for lo, hi in diff_buckets:
        rows = [a for a in attempts
                if a["crowd_rate"] is not None and lo <= a["crowd_rate"] < hi]
        difficulty.append({
            "label": f"{int(lo * 100)}-{int(hi * 100)}%",
            "count": len(rows),
            "accuracy": _rate(rows),
            "crowd": (lo + min(hi, 1.0)) / 2,
        })

    # problems that keep beating me
    seen = defaultdict(list)
    for a in attempts:
        seen[a["qid"]].append(a)
    repeats = sorted(
        ({
            "qid": qid,
            "publicid": rows[0]["publicid"],
            "type": rows[0]["qtypename"],
            "levelname": rows[0]["levelname"],
            "seen": len(rows),
            "failed": sum(1 for r in rows if r["result"] != CORRECT),
            "best_move": rows[-1]["best_move"],
            "my_first": rows[-1]["my_first"],
            "kind": rows[-1]["kind"],
            "crowd_rate": rows[0]["crowd_rate"],
        } for qid, rows in seen.items() if len(rows) > 1),
        key=lambda d: (-d["failed"], -d["seen"]))

    # The traps that cost the most -- shared misconceptions, highest leverage.
    # Grouped by problem: falling for the same trap five times is one lesson to
    # learn, not five rows, and the repeat count is the whole point.
    trap_groups = defaultdict(list)
    for a in failed:
        if a["kind"] == "trap":
            trap_groups[a["qid"]].append(a)
    traps = sorted(({
        "qid": qid,
        "publicid": rows[0]["publicid"],
        "qtypename": rows[0]["qtypename"],
        "levelname": rows[0]["levelname"],
        "times": len(rows),
        "my_first": rows[-1]["my_first"],
        "best_move": rows[-1]["best_move"],
        "my_first_share": rows[-1]["my_first_share"],
        "crowd_rate": rows[0]["crowd_rate"],
    } for qid, rows in trap_groups.items()),
        key=lambda d: (-d["times"], -d["my_first_share"]))

    # rolling accuracy over time
    trend = _trend(attempts)

    runs_summary = _runs_summary(runs)

    return {
        "attempts": attempts,
        "n": len(attempts),
        "n_runs": len(runs),
        "accuracy": _rate(attempts),
        "kinds": kinds,
        "levels": levels,
        "types": types,
        "positions": positions,
        "times": times,
        "difficulty": difficulty,
        "repeats": repeats,
        "traps": traps,
        "trend": trend,
        "runs": runs_summary,
        "median_time": _median([a["costtime"] for a in attempts if a["costtime"]]),
        "median_time_correct": _median(
            [a["costtime"] for a in attempts
             if a["costtime"] and a["result"] == CORRECT]),
        "median_time_wrong": _median(
            [a["costtime"] for a in attempts
             if a["costtime"] and a["result"] != CORRECT]),
    }


def _runs_summary(runs):
    out = []
    for r in sorted(runs, key=lambda r: r.get("t") or 0):
        qs = r.get("questions", [])
        if not qs:
            continue
        out.append({
            "guanid": r.get("guanid"),
            "level": level_label(r.get("number")),
            "number": r.get("number"),
            "t": r.get("t"),
            "date": _date(r.get("t")),
            "n": len(qs),
            "ok": sum(1 for q in qs if q.get("result") == CORRECT),
            "totaltime": r.get("totaltime"),
        })
    return out


def _trend(attempts, window=40):
    """Rolling accuracy, so a slow improvement is visible through the noise."""
    pts = []
    for i in range(len(attempts)):
        lo = max(0, i - window + 1)
        chunk = attempts[lo:i + 1]
        if len(chunk) < min(window, 10):
            continue
        pts.append({
            "i": i,
            "t": attempts[i].get("at") or attempts[i].get("run_t"),
            "accuracy": _rate(chunk),
        })
    return pts


def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def _date(ts):
    if not ts:
        return ""
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def pass_probability(accuracy, need, total):
    """Chance of clearing a run at a given per-problem accuracy.

    The test is *not* sudden death -- you answer `total` questions and need
    `need` right -- so this is the binomial tail, and it is very steep: a few
    points of accuracy move the pass rate a lot. That is the argument for
    training accuracy rather than re-taking the test.
    """
    if accuracy is None:
        return None
    p = max(0.0, min(1.0, accuracy))
    return sum(math.comb(total, k) * p ** k * (1 - p) ** (total - k)
               for k in range(need, total + 1))
