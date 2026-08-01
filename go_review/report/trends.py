"""The Trends section: per-phase point-loss and blunder-rate trend lines."""

from .constants import PHASES, PHASE_COLOR, PHASE_LABEL, PTS_BLUNDER, WR_BLUNDER
from .assets import TRENDS_JS
from .data import date_label, game_metrics
from .charts import trend_chart


def trends_section(chron):
    """chron: games oldest->newest. Returns HTML with the 4 trend charts."""
    if not chron:
        return ""
    seq = [str(i + 1) for i in range(len(chron))]
    tips = [f"Game {i + 1}  {date_label(g)}" for i, g in enumerate(chron)]
    gms = [game_metrics(g) for g in chron]

    def series_for(key):
        return [(PHASE_LABEL[ph], PHASE_COLOR[ph],
                 [gms[i][ph][key] for i in range(len(chron))])
                for ph in PHASES]

    # Pooled per-phase figures, computed from every move (not the mean of the
    # per-game dots), so the "phase mean" shown on each chart matches the overview
    # cards exactly. The "Overall" row pools every move; each phase row pools only
    # the moves belonging to that phase.
    st = {ph: {"cnt": 0, "loss": 0.0, "nb_pts": 0, "nb_wr": 0, "nb_either": 0}
          for ph in PHASES}
    for g in chron:
        for m in g.get("all_user_moves", []):
            pl = m.get("points_lost", 0) or 0
            isb = pl >= PTS_BLUNDER
            isw = (m.get("winrate_lost", 0) or 0) >= WR_BLUNDER
            for ph in ("overall", m.get("phase")):
                if ph not in st:
                    continue
                st[ph]["cnt"] += 1
                st[ph]["loss"] += pl
                if isb:
                    st[ph]["nb_pts"] += 1
                if isw:
                    st[ph]["nb_wr"] += 1
                if isb or isw:
                    st[ph]["nb_either"] += 1
    ng = max(1, len(chron))

    def ov(metric):
        out = []
        for ph in PHASES:
            s = st[ph]
            c = s["cnt"]
            if metric == "apl":
                out.append(f"{(s['loss']/c):.2f}" if c else "—")
            elif metric == "br_pts":
                out.append(f"{(s['nb_pts']/c*100):.1f}%" if c else "—")
            elif metric == "br_wr":
                out.append(f"{(s['nb_wr']/c*100):.1f}%" if c else "—")
            elif metric == "blunders":
                out.append(f"{(s['nb_either']/ng):.1f}")
        return out

    charts = [
        trend_chart("Average points lost per move", seq,
                    series_for("apl"), "pts/move", tip_labels=tips,
                    avg_overrides=ov("apl")),
        trend_chart("Blunder rate — lost >= 6 pts", seq,
                    series_for("br_pts"), "share %", tip_labels=tips,
                    avg_overrides=ov("br_pts")),
        trend_chart("Blunder rate — win-rate drop >= 15%", seq,
                    series_for("br_wr"), "share %", tip_labels=tips,
                    avg_overrides=ov("br_wr")),
        trend_chart("Blunders per game (>=6 pts or win-rate -15%)", seq,
                    series_for("blunders"), "count", tip_labels=tips,
                    avg_overrides=ov("blunders")),
    ]
    body = "".join(f"<div class='chart'>{c}</div>" for c in charts)
    return ("<h2>Trends over time</h2>"
            "<p class='sub'>Each chart is ordered oldest-to-newest; the x-axis is "
            "the game number (1 = earliest). The four curves are the phases of the "
            "game. Hover a dot to see which game it is, its date and its value; "
            "<b>click a legend entry to hide/show that curve</b>.</p>"
            "<p class='sub'>The <b>phase mean</b> in each chart's top-right corner "
            "pools every move from every game and averages per move (the same basis "
            "as the overview cards above, so it is a move-weighted average, not a "
            "plain average of the per-game dots).<br>"
            "<b>Phase split</b> (by move number): <b>Fuseki</b> = moves 1-40; "
            "<b>Yose</b> = the last 40 moves, or anything past ~72% of the game; "
            "<b>Middlegame</b> = everything in between; "
            "<b>Overall</b> = all moves combined.</p>"
            f"<div class='charts2' id='homeCharts'>{body}</div>"
            + TRENDS_JS)


# ---- improvement metric ----------------------------------------------------

def _window_apl(games):
    """Pooled average points lost per user move over a set of games."""
    loss, cnt = 0.0, 0
    for g in games:
        for m in g.get("all_user_moves", []):
            cnt += 1
            loss += (m.get("points_lost", 0) or 0)
    return (loss / cnt) if cnt else None


def improvement_metric(chron):
    """Compare the most-recent block of games to the block before it on points
    lost per move (lower = stronger). chron is oldest->newest. Returns a dict
    or None when there are too few games / moves."""
    g = len(chron)
    if g < 6:
        return None
    n = min(10, g // 2)
    recent = chron[-n:]
    earlier = chron[-2 * n:-n]
    r = _window_apl(recent)
    e = _window_apl(earlier)
    if r is None or e is None or e == 0:
        return None
    delta = r - e
    pct = delta / e * 100
    if pct <= -10:
        verdict = "good"
    elif pct >= 10:
        verdict = "bad"
    else:
        verdict = "flat"
    return {"n": n, "recent": r, "earlier": e, "delta": delta,
            "pct": pct, "verdict": verdict}


def _improve_banner_html(chron):
    m = improvement_metric(chron)
    if not m:
        return ("<div class='improve imp-na' id='homeImprove'>"
                "<div class='impl'>Improvement trend</div>"
                "<div class='impv'>Too few games to judge yet</div>"
                "<div class='impd'>Once you have 6 or more games, this compares the "
                "average points lost per move in your recent games against the "
                "batch before them, and calls it improving / flat / slipping."
                "</div></div>")
    cls = {"good": "imp-good", "bad": "imp-bad", "flat": "imp-flat"}[m["verdict"]]
    title = {"good": "Improving", "bad": "Slipping",
             "flat": "Roughly flat"}[m["verdict"]]
    ar = {"good": "▼", "bad": "▲", "flat": "→"}[m["verdict"]]
    direction = "down" if m["delta"] < 0 else ("up" if m["delta"] > 0 else "flat")
    less_more = "losing" if m["delta"] < 0 else "losing an extra"
    pcttxt = f"{abs(m['pct']):.0f}%"
    desc = (f"Your last {m['n']} games lose <b>{m['recent']:.2f}</b> pts per move, "
            f"{direction} {pcttxt} from <b>{m['earlier']:.2f}</b> pts in the "
            f"{m['n']} games before them ({less_more} {abs(m['delta']):.2f} "
            f"pts/move). The lower the loss per move, the steadier your play.")
    return (f"<div class='improve {cls}' id='homeImprove'>"
            f"<div class='impl'>Improvement trend &middot; avg points lost per move</div>"
            f"<div class='impv'><span class='ar'>{ar}</span>{title}"
            f"<span class='pct'>{pcttxt}</span></div>"
            f"<div class='impd'>{desc}</div></div>")
