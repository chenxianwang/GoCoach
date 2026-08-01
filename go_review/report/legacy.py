"""Unused code paths kept for reference (not wired into build_html)."""

from .constants import PHASE_LABEL
from .data import esc
from .board import full_board_svg


# ---- coach's qualitative review --------------------------------------------

def coach_review(games, agg):
    """A written, data-driven diagnosis: the player's main weakness, the Go
    principles they may be misunderstanding, and concrete suggestions.

    The numbers (worst phase, the point KataGo kept recommending, how often a
    winning game was thrown away) are computed from the data so the text stays
    honest as more games are analysed; the framing is the coaching layer."""
    moves = [m for g in games for m in g.get("all_user_moves", [])]
    if not moves:
        return ""
    pa = agg.get("phase_avg", {}) or {}
    worst = max(pa, key=lambda k: pa.get(k, 0)) if any(pa.values()) else "middlegame"
    worst_lbl = PHASE_LABEL.get(worst, worst)
    best_phase = min(pa, key=lambda k: pa.get(k, 0)) if any(pa.values()) else "opening"
    best_lbl = PHASE_LABEL.get(best_phase, best_phase)

    # The single point KataGo kept recommending while you played elsewhere.
    miss_cnt, miss_pts = {}, {}
    for m in moves:
        best, played = m.get("best"), m.get("played")
        if not best or best == played:
            continue
        if m.get("points_lost", 0) >= 1.5 or m.get("winrate_lost", 0) >= 0.08:
            miss_cnt[best] = miss_cnt.get(best, 0) + 1
            miss_pts[best] = miss_pts.get(best, 0.0) + m.get("points_lost", 0)
    top_pt, top_n, top_pts = "", 0, 0.0
    if miss_cnt:
        top_pt = max(miss_cnt, key=lambda k: (miss_cnt[k], miss_pts[k]))
        top_n = miss_cnt[top_pt]
        top_pts = miss_pts[top_pt]

    big_swings = sum(1 for m in moves if m.get("winrate_lost", 0) >= 0.30)
    decided_leaks = sum(1 for m in moves
                        if m.get("points_lost", 0) >= 6
                        and m.get("winrate_lost", 0) < 0.03)

    paras = []

    # 1. Overall diagnosis.
    paras.append(
        f"<p>Your <b>opening fundamentals are solid</b> -- in the {best_lbl} phase "
        f"you lose only {pa.get(best_phase, 0)} pts per move on average, and your "
        f"joseki and big-point choices are broadly right. Where you actually bleed "
        f"points is <b>{worst_lbl}</b> ({pa.get(worst, 0)} pts per move) -- the phase "
        f"where the board opens up and you have to judge the whole board yourself. In "
        f"other words: <b>what you have memorised is enough, but your live whole-board "
        f"judgement has not caught up</b>.</p>")

    # 2. Core weakness — the recurring missed big point.
    if top_n >= 4:
        paras.append(
            f"<p><b>The core problem: you keep missing the biggest move on the "
            f"board.</b> Across these games KataGo marked the area around "
            f"<b>{esc(top_pt)}</b> as best as many as <b>{top_n} times</b> "
            f"(costing roughly {top_pts:.0f} pts in total), and you almost never "
            f"took it -- instead you kept patching the area you had just been "
            f"fighting in, reinforcing a group that was already alive, or playing "
            f"small local moves. This is the classic combination of "
            f"<b>clinging to stones / refusing to play tenuki</b> and a "
            f"<b>weak feel for big points</b>.</p>")
    elif top_n >= 2:
        paras.append(
            f"<p><b>Core problem: finding the biggest point on the board.</b> "
            f"KataGo repeatedly ({top_n} times around {esc(top_pt)}) pointed at the "
            f"same big point you were slow to take, which means you often choose "
            f"wrongly between <b>answering locally</b> and <b>turning away to take "
            f"the big point</b>.</p>")
    else:
        paras.append(
            "<p><b>Your core problem is whole-board judgement in the middlegame.</b> "
            "Most of your mistakes are not reading errors -- they are choosing the "
            "wrong area to play in.</p>")

    if big_swings:
        paras.append(
            f"<p>Worse, playing in the unimportant place threw away a <b>game you "
            f"were leading or level in</b> on <b>{big_swings} occasions</b> (a single "
            f"move dropping the win rate by 30% or more). You do not lose the margin "
            f"gradually -- you hand it over all at once on a few critical moves.</p>")
    if decided_leaks >= 2:
        paras.append(
            f"<p>Another <b>{decided_leaks}</b> blunders came in already-decided "
            f"positions (they cost points without changing the result). That points "
            f"to <b>loose endgame and life-and-death finishing</b>: you relax when "
            f"winning and get flustered when losing.</p>")

    # 3. Go theory the player may be misunderstanding.
    paras.append(
        "<p><b>Go principles you may be misreading or ignoring:</b></p>"
        "<ul>"
        "<li><b>Vital points and big points (the largest move):</b> before every "
        "move, ask where the biggest area on the board is and compare two or three "
        "candidate big points, instead of reflexively answering next to your "
        "opponent's last stone.</li>"
        "<li><b>Once a group is alive, play tenuki:</b> if a group is unconditionally "
        "alive or already settled, another reinforcing move creates almost no value. "
        "Save the tesuji and the reinforcement for when you actually need them; when "
        "it is time to turn away, turn away.</li>"
        "<li><b>Direction of play:</b> attack and expand so that you drive your "
        "opponent towards your own thickness and lead your development towards the "
        "largest open area -- rather than pushing from behind in a small corner of "
        "the board.</li>"
        "<li><b>When behind, look for the biggest exchange:</b> in a bad position, "
        "look for a large group or a genuine game-turning move that wins back ten "
        "points at once, instead of patching with a series of small plays -- that "
        "only locks the deficit in.</li>"
        "</ul>")

    # 4. Concrete suggestions.
    sug = [
        f"Force yourself to do a whole-board scan before every move: find the "
        f"largest open area or the weakest group, and weigh it against the local "
        f"move you want to play -- especially the kind of big point you keep "
        f"missing around {esc(top_pt) if top_pt else 'the biggest open area'}.",
        "Practise the tenuki decision: every time a local exchange comes to a rest, "
        "pause and ask yourself, 'Does this group still need a move? Is there "
        "anything bigger elsewhere on the board?'",
        "Roughly count the score around moves 50, 100 and 150 to build the habit of "
        "positional judgement -- knowing whether you are ahead or behind is what "
        "tells you whether to play safe or to fight.",
        "Drill endgame value comparison and life-and-death finishing, so you close "
        "won games out cleanly and stop leaking points.",
        "Your opening is already decent: the biggest lever is not memorising more "
        "joseki but whole-board judgement in the middlegame -- focus your reviews on "
        "direction of play and big points.",
    ]
    paras.append("<p><b>What to do about it:</b></p><ol>"
                 + "".join(f"<li>{s}</li>" for s in sug) + "</ol>")

    return ("<h2>Coach's review (overall diagnosis)</h2>"
            "<div class='coach'>" + "".join(paras) + "</div>")


def _recs_page(recs):
    p = ["<h2>What to work on</h2>"]
    for r in recs:
        p.append(f"<div class='rec'>{esc(r)}</div>")
    return "".join(p)


def _blunders_page(games, agg):
    gmap = {g["filename"]: g for g in games}
    p = ["<h2>Biggest mistakes across all games</h2>",
         "<table><tr><th>Points lost</th><th>Move</th><th>You played</th>"
         "<th>KataGo</th><th>Phase</th><th>Game</th><th>Board</th></tr>"]
    for k, m in enumerate(agg["top_blunders"]):
        p.append(f"<tr><td class='big'>{m['points_lost']}</td>"
                 f"<td class='mv'>#{m['move_number']}</td>"
                 f"<td class='mv'>{esc(m['played'])}</td>"
                 f"<td class='mv'>{esc(m.get('best'))}</td>"
                 f"<td>{esc(PHASE_LABEL.get(m['phase'], m['phase']))}</td>"
                 f"<td>{esc(m.get('date',''))} vs "
                 f"{esc(m.get('opponent',''))}</td>"
                 f"<td><button class='fbbtn' onclick=\"var r="
                 f"document.getElementById('fbrow-{k}');"
                 f"var s=r.style.display==='none';"
                 f"r.style.display=s?'':'none';"
                 f"this.textContent=s?'Hide':'Show full board';\">"
                 f"Show full board</button></td></tr>")
        g = gmap.get(m.get("game"))
        if g is not None and g.get("moves"):
            board_svg = full_board_svg(g, m, f"fb{k}")
            mvcb = (f"<label class='fbtog'><input type='checkbox' checked "
                    f"onchange=\"document.getElementById('fb{k}-mv')"
                    f".style.display=this.checked?'':'none'\"> Your move</label>")
            aicb = (f"<label class='fbtog'><input type='checkbox' checked "
                    f"onchange=\"document.getElementById('fb{k}-ai')"
                    f".style.display=this.checked?'':'none'\"> AI recommended line</label>")
            panel = (f"<div class='fbpanel'><div class='fbtogs'>"
                     f"{mvcb}{aicb}</div>{board_svg}</div>")
        else:
            panel = ("<div class='fbpanel'>(Cannot show the full board -- "
                     "re-run the analysis.)</div>")
        p.append(f"<tr class='fbrow' id='fbrow-{k}' style='display:none'>"
                 f"<td colspan='7'>{panel}</td></tr>")
    p.append("</table>")
    return "".join(p)
