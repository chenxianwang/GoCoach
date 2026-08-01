"""Overview and Game-by-game page assembly."""

import re
import datetime

from .constants import PTS_BLUNDER
from .assets import GAMES_JS
from .data import blunder_count, date_key, esc, parse_date
from .board import final_score_html, full_board_svg, score_svg
from .charts import metric_hist_svg, moves_hist_svg


def _home_page(agg, chron=None):
    record = f"{agg['wins']}–{agg['losses']}"
    src = agg.get("source_label", "")
    src_html = (f" &middot; project <b>{esc(src)}</b>" if src else "")
    p = [f"<h1>KataGo Game Review</h1>",
         f"<p class='sub'>Generated {esc(datetime.date.today().isoformat())} "
         f"&middot; {agg['n']} games &middot; {agg['n_user_moves']} of your moves analysed"
         f"{src_html}</p>",
         "<div class='ovctl'><label class='exw'>"
         "<input type='checkbox' id='exWorst'> Exclude the worst game (outlier)"
         "</label><span class='exwnote' id='exWorstNote'></span></div>",
         "<div class='cards' id='homeCards'>"]
    for v, l in ((record, "Win - Loss"),
                 (agg["avg_points_lost"], "Avg points lost per move"),
                 (f"{agg['blunder_rate']}%", "Blunder rate (&ge;6 pts or WR &minus;15%)"),
                 (agg["n_blunders"], "Total blunders"),
                 (agg.get("avg_moves", 0), "Avg moves per game")):
        p.append(f"<div class='card'><div class='v'>{v}</div>"
                 f"<div class='l'>{l}</div></div>")
    p.append("</div>")
    p.append("<p class='sub'>Use the sidebar to open the other sections: "
             "the blunder set and the game-by-game review.</p>")
    return "".join(p)


def _moves_hist_section(agg, games=None):
    games = games or []
    pl, wl = [], []
    for g in games:
        for m in g.get("all_user_moves", []):
            pl.append(m.get("points_lost", 0) or 0)
            wl.append((m.get("winrate_lost", 0) or 0) * 100)
    apl_hist = metric_hist_svg(
        pl, "Points lost per move (distribution)", 0.5,
        "x-axis: points lost on a single move (0.5-pt bins, 15+ pooled); "
        "the red dashed line is the 6-pt blunder line",
        thresh=6, thresh_label="blunder line 6 pts", cap=15, color="#4c6ef5")
    wl_hist = metric_hist_svg(
        wl, "Win-rate lost per move (distribution)", 2.5,
        "x-axis: win-rate drop on a single move (2.5% bins, 50%+ pooled); "
        "the red dashed line is the 15% blunder line",
        thresh=15, thresh_label="blunder line 15%", cap=50, pct=True, color="#7048e8")
    moves = moves_hist_svg(agg.get("moves_counts", []))
    # Wrapped with ids so the date-range filter / exclude-worst toggle can re-render.
    return ("<div class='chartbox' id='homeHistApl'>" + (apl_hist or "") + "</div>"
            "<div class='chartbox' id='homeHistWr'>" + (wl_hist or "") + "</div>"
            "<div class='chartbox' id='homeHist'>" + (moves or "") + "</div>")


def _game_recency_key(g):
    """Sort key for "newest first": the trailing chess-id in the SGF filename
    (a globally increasing number on Fox) is the most reliable recency signal;
    fall back to the parsed date when no id is present."""
    fn = g.get("filename", "") or ""
    nums = re.findall(r"\d{6,}", fn)
    cid = int(nums[-1]) if nums else 0
    return (date_key(g), cid)


def _games_page(games):
    p = ["<h2>Game by game</h2>",
         "<p class='sub'>Newest game first. Use the filters below to narrow it down.</p>",
         "<div class='navbar'>",
         "<div class='navrow'><span class='navlbl'>Result</span>"
         "<button class='navbtn on' data-fr='all'>All</button>"
         "<button class='navbtn' data-fr='win'>Win</button>"
         "<button class='navbtn' data-fr='loss'>Loss</button></div>",
         "<div class='navrow'><span class='navlbl'>Colour</span>"
         "<button class='navbtn on' data-fc='all'>All</button>"
         "<button class='navbtn' data-fc='B'>Black</button>"
         "<button class='navbtn' data-fc='W'>White</button></div>",
         "<div class='navrow'><span class='navlbl'>Blunders</span>"
         "<button class='navbtn on' data-fb='0'>All</button>"
         "<button class='navbtn' data-fb='1'>&ge; 1</button>"
         "<button class='navbtn' data-fb='3'>&ge; 3</button>"
         "<button class='navbtn' data-fb='5'>&ge; 5</button></div>",
         "<div class='navrow'><span class='navlbl'>Avg loss</span>"
         "<button class='navbtn on' data-fa='0'>All</button>"
         "<button class='navbtn' data-fa='2'>&ge; 2 pts</button>"
         "<button class='navbtn' data-fa='3'>&ge; 3 pts</button>"
         "<button class='navbtn' data-fa='4'>&ge; 4 pts</button></div>",
         "</div>",
         "<div class='flcount' id='gmcount'></div>"]
    fbk = 0  # page-wide unique id for the expandable full-board rows
    for gi, g in enumerate(sorted(games, key=_game_recency_key, reverse=True)):
        wl = g.get("won")
        wl_html = ("<span class='win'>Win</span>" if wl is True else
                   "<span class='loss'>Loss</span>" if wl is False else "")
        res = "win" if wl is True else "loss" if wl is False else "na"
        try:
            avg = float(g.get("avg_points_lost") or 0)
        except (TypeError, ValueError):
            avg = 0.0
        _gd = parse_date(g)
        _gd = _gd.isoformat() if _gd else ""
        p.append(f"<div class='game' data-result='{res}' "
                 f"data-date='{_gd}' "
                 f"data-color='{g.get('user_color','')}' "
                 f"data-blunders='{blunder_count(g)}' "
                 f"data-avg='{avg:.2f}'>")
        p.append(f"<h3>{esc(g.get('date',''))} &mdash; vs {esc(g.get('opponent',''))} "
                 f"{wl_html} <span class='pill'>You: "
                 f"{'Black' if g['user_color']=='B' else 'White'}</span> "
                 f"<span class='pill'>{esc(g.get('result',''))}</span></h3>")
        pa = g.get("avg_points_lost_by_phase", {})
        p.append(f"<p class='sub'>Avg points lost per move: "
                 f"{g.get('avg_points_lost')} (fuseki {pa.get('opening',0)}, "
                 f"middlegame {pa.get('middlegame',0)}, yose "
                 f"{pa.get('endgame',0)}) &middot; {blunder_count(g)} blunders</p>")
        p.append(score_svg(g))
        p.append(final_score_html(g, f"fs{gi}"))
        mistakes = g.get("biggest_mistakes", [])
        if mistakes:
            p.append("<table><tr><th>Points lost</th><th>Move</th>"
                     "<th>You played</th><th>KataGo played</th>"
                     "<th>Recommended line</th><th></th></tr>")
            for m in mistakes:
                cls = "big" if m["points_lost"] >= PTS_BLUNDER else ""
                k = fbk
                fbk += 1
                btn = (f"<button class='fbbtn' onclick=\"var r="
                       f"document.getElementById('gmrow-{k}');"
                       f"var s=r.style.display==='none';"
                       f"r.style.display=s?'':'none';"
                       f"this.textContent=s?'Hide full position':'View full position';\">"
                       f"View full position</button>")
                p.append(f"<tr><td class='{cls}'>{m['points_lost']}</td>"
                         f"<td class='mv'>#{m['move_number']}</td>"
                         f"<td class='mv'>{esc(m['played'])}</td>"
                         f"<td class='mv'>{esc(m.get('best'))}</td>"
                         f"<td class='mv'>{esc(m.get('best_pv',''))}</td>"
                         f"<td>{btn}</td></tr>")
                # Expandable full-board row: actual move + AI line, toggleable.
                if g.get("moves"):
                    bsvg = full_board_svg(g, m, f"gm{k}")
                    mvcb = (f"<label class='fbtog'><input type='checkbox' checked "
                            f"onchange=\"document.getElementById('gm{k}-mv')"
                            f".style.display=this.checked?'':'none'\"> "
                            f"<span style='color:#e02424'>&#9632;</span> "
                            f"The move you played</label>")
                    aicb = (f"<label class='fbtog'><input type='checkbox' checked "
                            f"onchange=\"document.getElementById('gm{k}-ai')"
                            f".style.display=this.checked?'':'none'\"> "
                            f"<span style='color:#1f9d55'>&#9679;</span> "
                            f"AI recommendation (numbered continuation)</label>")
                    panel = (f"<div class='fbpanel'><div class='fbtogs'>"
                             f"{mvcb}{aicb}</div>{bsvg}</div>")
                else:
                    panel = ("<div class='fbpanel'>(Cannot show the full board -- "
                             "re-run the analysis.)</div>")
                p.append(f"<tr class='fbrow' id='gmrow-{k}' style='display:none'>"
                         f"<td colspan='6'>{panel}</td></tr>")
            p.append("</table>")
        p.append("</div>")
    p.append(GAMES_JS)
    return "".join(p)
