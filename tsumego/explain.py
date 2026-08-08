"""Everything the cache knows about one problem, as a coaching brief.

The dashboard answers "which problems beat me". This answers "what happened in
*this* problem" -- and the crowd tree makes one thing visible that the site's
own review does not: **where the problem is actually decided.**

A tsumego is not uniformly hard. Walk the correct line and ask, at each of your
turns, what share of players found the right move. The answer is usually 80-90%
for move 1 and then falls off a cliff at exactly one turn. That turn is the
crux; everything before it is shape recognition and everything after it is
usually forced. Knowing which turn it is turns "I got it wrong" into "I got it
wrong at the one move that separates the people who solve this from the people
who do not", which is a lesson you can actually carry to the next problem.

    python3 -m tsumego explain 453591      # by the Q-number the site shows
    python3 -m tsumego explain --qid 506795
"""

from .api import pt_to_gtp
from .analyze import CORRECT, S_OK, S_FAIL, level_label

STATUS = {S_OK: "correct", S_FAIL: "loses", "c": "off-book"}


def _children(diagram, node_id):
    node = diagram.get(str(node_id))
    if not node:
        return []
    return [diagram[str(s)] for s in node.get("subs", []) if str(s) in diagram]


def _options(diagram, node_id):
    """Every move played from here, most popular first, with crowd share.

    The share is out of the players who *reached this node*, not out of everyone
    who attempted the problem -- otherwise the numbers shrink down the line and
    stop being comparable between turns.
    """
    kids = sorted(_children(diagram, node_id), key=lambda c: -c.get("num", 0))
    total = sum(c.get("num", 0) for c in kids)
    return [{
        "gtp": pt_to_gtp(c.get("pt", "")),
        "pt": c.get("pt", ""),
        "num": c.get("num", 0),
        "share": (c.get("num", 0) / total) if total else 0.0,
        "status": STATUS.get(c.get("s"), "off-book"),
        "id": c.get("id"),
    } for c in kids]


def main_line(diagram):
    """The correct sequence, following the most-played correct move each ply.

    There can be several correct answers; this takes the one the crowd actually
    walks, which is the one worth learning first.
    """
    line, cur, seen = [], 0, set()
    while True:
        best = max((c for c in _children(diagram, cur) if c.get("s") == S_OK),
                   key=lambda c: c.get("num", 0), default=None)
        if best is None or best.get("id") in seen:
            break            # a malformed tree must not spin forever
        seen.add(best.get("id"))
        line.append({"gtp": pt_to_gtp(best.get("pt", "")), "pt": best.get("pt", ""),
                     "num": best.get("num", 0), "id": best.get("id")})
        cur = best["id"]
    return line


def decision_points(diagram):
    """Your turns along the correct line, with how often the crowd got each one.

    Even plies are yours: the tree starts at the position you are asked to solve,
    so node depth 0, 2, 4 ... are the moves you choose and the odd ones are the
    opponent's reply.
    """
    out, cur = [], 0
    for ply in range(2 * 20):
        opts = _options(diagram, cur)
        if not opts:
            break
        right = next((o for o in opts if o["status"] == "correct"), None)
        if right is None:
            break
        if ply % 2 == 0:
            out.append({
                "ply": ply // 2 + 1,
                "answer": right["gtp"],
                "found": right["share"],       # share of survivors who got it
                "reached": right["num"],
                "alternatives": [o for o in opts if o["gtp"] != right["gtp"]][:4],
                "forced": len(opts) == 1,
            })
        cur = right["id"]
    return out


def crux(points):
    """The turn where the fewest players find the move -- where the problem lives."""
    real = [p for p in points if not p["forced"]]
    return min(real, key=lambda p: p["found"]) if real else None


def attempts_for(runs, qid=None, publicid=None):
    """Every time you have met this problem, oldest first."""
    out = []
    for run in runs:
        for q in run.get("questions", []):
            if (qid is not None and q.get("qid") == qid) or \
               (publicid is not None and q.get("publicid") == publicid):
                out.append((run, q))
    return sorted(out, key=lambda rq: rq[1].get("at") or rq[0].get("t") or 0)


def _walk(diagram, moves):
    """Label each of my moves against the tree. Unknown moves end the walk."""
    out, cur = [], 0
    for i, mv in enumerate(moves):
        match = next((c for c in _children(diagram, cur) if c.get("pt") == mv), None)
        if match is None:
            out.append({"gtp": pt_to_gtp(mv), "mine": i % 2 == 0,
                        "status": "off-book", "share": 0.0})
            break
        opts = _options(diagram, cur)
        share = next((o["share"] for o in opts if o["pt"] == mv), 0.0)
        out.append({"gtp": pt_to_gtp(mv), "mine": i % 2 == 0,
                    "status": STATUS.get(match.get("s"), "off-book"), "share": share})
        cur = match["id"]
    return out


def explain(runs, load_diagram, ident, by_qid=False):
    """Assemble the brief. `ident` is the site's Q-number unless by_qid."""
    pairs = attempts_for(runs, qid=ident if by_qid else None,
                         publicid=None if by_qid else ident)
    if not pairs:
        return None
    qid = pairs[-1][1].get("qid")
    diagram = load_diagram(qid) or {}
    points = decision_points(diagram)
    tries = []
    for run, q in pairs:
        walk = _walk(diagram, q.get("moves") or [])
        mine = [w for w in walk if w["mine"]]
        bad = next((i for i, w in enumerate(mine) if w["status"] != "correct"), None)
        tries.append({
            "guanid": run.get("guanid"),
            "level": level_label(run.get("number")),
            "n": q.get("n"),
            "at": q.get("at"),
            "costtime": q.get("costtime") or 0,
            "solved": q.get("result") == CORRECT,
            "expired": bool(q.get("expired")),
            "walk": walk,
            "got_right": bad if bad is not None else len(mine),
            "wrong_at": None if bad is None else bad + 1,
        })
    last = pairs[-1][1]
    yes, no = last.get("yes") or 0, last.get("no") or 0
    return {
        "qid": qid,
        "publicid": last.get("publicid"),
        "type": last.get("qtypename"),
        "levelname": last.get("levelname"),
        "blackfirst": last.get("blackfirst"),
        "crowd_rate": yes / (yes + no) if (yes + no) else None,
        "url": f"https://www.101weiqi.com/q/{last.get('publicid')}/",
        "line": main_line(diagram),
        "points": points,
        "crux": crux(points),
        "attempts": tries,
        "has_diagram": bool(diagram),
    }


# -- text rendering ------------------------------------------------------

def _pct(x):
    return "--" if x is None else f"{x * 100:.0f}%"


def to_text(e):
    L = []
    add = L.append
    add(f"Q-{e['publicid']}  {e['type']}  {e['levelname']}   "
        f"{'Black' if e['blackfirst'] else 'White'} first")
    add(f"{e['url']}")
    add(f"Solved by {_pct(e['crowd_rate'])} of players.  "
        f"You have met it {len(e['attempts'])}x.")
    if not e["has_diagram"]:
        add("")
        add("No crowd tree cached for this problem yet -- run "
            "`python3 -m tsumego fetch` to pull it.")
        return "\n".join(L)

    add("")
    add("ANSWER   " + " ".join(
        ("B " if i % 2 == 0 else "W ") + m["gtp"] for i, m in enumerate(e["line"])))

    add("")
    add("WHERE IT IS DECIDED  (of the players still on the correct line)")
    for p in e["points"]:
        if p["forced"]:
            add(f"  move {p['ply']}:  {p['answer']:<4}  forced -- no other move exists")
            continue
        alts = ", ".join(f"{o['gtp']} {_pct(o['share'])} {o['status']}"
                         for o in p["alternatives"])
        add(f"  move {p['ply']}:  {p['answer']:<4}  found by {_pct(p['found'])}"
            + (f"   others: {alts}" if alts else ""))
    if e["crux"]:
        c = e["crux"]
        add(f"  -> the problem is move {c['ply']} ({c['answer']}): "
            f"{_pct(1 - c['found'])} of the players who got this far go wrong here.")

    add("")
    add("YOUR ATTEMPTS")
    for t in e["attempts"]:
        mark = "solved" if t["solved"] else ("ran out of time" if t["expired"] else "wrong")
        add(f"  run {t['guanid']} q{t['n']} ({t['level']}, {t['costtime']}s) -- {mark}")
        played = "  ".join(
            ("B " if w["mine"] else "W ") + w["gtp"]
            + ("" if w["status"] == "correct" else f" <-{w['status']}")
            for w in t["walk"])
        add("      " + (played or "(no move played -- the clock ran out first)"))
        if not t["solved"]:
            if t["wrong_at"] is None and t["got_right"]:
                add(f"      {t['got_right']} correct move(s), then the clock ran "
                    f"out -- the reading was right, the finish was not")
            elif t["wrong_at"] is None:
                add("      nothing was played, so there is no misread to diagnose "
                    "-- only the clock")
            else:
                add(f"      first wrong move: your move {t['wrong_at']}")
    return "\n".join(L)
