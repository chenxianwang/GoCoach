"""Win-rate trajectory classification (lead conversion / comeback rate)."""

from .constants import BEHIND_TH, LEAD_TH, TRAJ_CLASS, TRAJ_LABEL, TRAJ_TYPES
from .assets import TRAJ_JS
from .data import date_key, esc, parse_date
from .charts import _traj_spark


# ---- game trajectory (win-rate curve shape) --------------------------------

def _user_wr_curve(g):
    """The user's win-rate over the game (0..1), flipped to their colour."""
    uc = g.get("user_color")
    out = []
    for t in g.get("timeline", []):
        bw = t.get("black_winrate")
        if bw is None:
            continue
        out.append(bw if uc == "B" else 1.0 - bw)
    return out


def classify_trajectory(g):
    """Classify a game by the shape of the user's win-rate curve."""
    w = _user_wr_curve(g)
    if len(w) < 6:
        return None
    won = bool(g.get("won"))
    n = len(w)
    seg = lambda a, b: (sum(w[a:b]) / len(w[a:b])) if w[a:b] else 0.5
    o, m, e = seg(0, n // 3), seg(n // 3, 2 * n // 3), seg(2 * n // 3, n)
    mx, mn, final = max(w), min(w), w[-1]
    AH, BE = 0.60, 0.40
    # fraction of the game spent clearly ahead / behind (robust to blips)
    frac_ahead = sum(1 for v in w if v >= AH) / n
    frac_behind = sum(1 for v in w if v <= BE) / n
    eg = w[2 * n // 3:] or w[-1:]
    eg_ahead = sum(1 for v in eg if v >= AH) / len(eg)

    def mark(v):
        return "▲" if v >= AH else ("▼" if v <= BE else "●")
    shape = mark(o) + mark(m) + mark(e)
    if won:
        if frac_behind < 0.12:
            tid = "wire_win"              # rarely behind → led throughout
        elif frac_behind >= 0.25:
            tid = "comeback"              # behind a good chunk, then won
        else:
            tid = "seesaw_win"
    else:
        if eg_ahead >= 0.4 and final < 0.5:
            tid = "collapse"             # led most of the endgame, still lost
        elif frac_ahead >= 0.25:
            tid = "blew_lead"            # substantially ahead at some point
        elif frac_ahead < 0.12:
            tid = "wire_loss"            # barely ever ahead
        else:
            tid = "narrow_loss"
    return {"type": tid, "shape": shape, "curve": w, "won": won,
            "o": o, "m": m, "e": e, "mx": mx, "mn": mn, "final": final,
            "frac_ahead": frac_ahead, "frac_behind": frac_behind}


def _shape_html(shape):
    cmap = {"▲": "#2f855a", "●": "#a08a6a", "▼": "#c53030"}
    return "".join(f"<span style='color:{cmap[c]}'>{c}</span>" for c in shape)


def _wr_at(w, frac):
    """Smoothed win-rate at a fraction of the game (small window)."""
    if not w:
        return 0.5
    i = int(round(frac * (len(w) - 1)))
    seg = w[max(0, i - 2):i + 3]
    return sum(seg) / len(seg) if seg else 0.5


def _lead_flags(w):
    """(led_entering_middle, led_entering_endgame) at LEAD_TH."""
    return (_wr_at(w, 1 / 3) >= LEAD_TH, _wr_at(w, 2 / 3) >= LEAD_TH)


def _behind_flags(w):
    """(behind_entering_middle, behind_entering_endgame) at BEHIND_TH."""
    return (_wr_at(w, 1 / 3) <= BEHIND_TH, _wr_at(w, 2 / 3) <= BEHIND_TH)


def trajectory_section(games):
    rows = []
    for g in games:
        c = classify_trajectory(g)
        if c:
            rows.append((g, c))
    if not rows:
        return ""
    rows.sort(key=lambda gc: date_key(gc[0]), reverse=True)
    counts = {}
    for _, c in rows:
        counts[c["type"]] = counts.get(c["type"], 0) + 1
    # summary chips (server-side; JS recomputes for the date filter)
    chips = []
    for tid, label, cls, prob, _ in TRAJ_TYPES:
        n = counts.get(tid, 0)
        if n:
            chips.append(f"<span class='tjchip {cls}' data-t='{tid}'>"
                         f"{esc(label)} <b>{n}</b></span>")
    # insights for the problem types that actually occurred, most common first
    insights = []
    for tid, label, cls, prob, tip in sorted(
            TRAJ_TYPES, key=lambda t: counts.get(t[0], 0), reverse=True):
        if prob and tip and counts.get(tid, 0):
            insights.append(f"<li><b>{esc(label)} ({counts[tid]} games):</b> "
                            f"{esc(tip)}</li>")
    ins_html = (f"<ul class='tjins'>{''.join(insights)}</ul>" if insights else "")

    # Lead conversion & comeback rate: of games led / behind entering
    # a phase, win %.
    lm = lmw = le = lew = 0          # led entering middle / endgame -> won
    bm = bmw = be = bew = 0          # behind entering middle / endgame -> won
    cards = []
    for g, c in rows:
        won = c["won"]
        led_mid, led_end = _lead_flags(c["curve"])
        beh_mid, beh_end = _behind_flags(c["curve"])
        if led_mid:
            lm += 1
            lmw += 1 if won else 0
        if led_end:
            le += 1
            lew += 1 if won else 0
        if beh_mid:
            bm += 1
            bmw += 1 if won else 0
        if beh_end:
            be += 1
            bew += 1 if won else 0
        res = ("<span class='win'>Win</span>" if won
               else "<span class='loss'>Loss</span>")
        _gd = parse_date(g)
        _gd = _gd.isoformat() if _gd else ""
        cards.append(
            f"<div class='trajcard' data-type='{c['type']}' data-date='{_gd}' "
            f"data-won='{1 if won else 0}' data-ledmid='{1 if led_mid else 0}' "
            f"data-ledend='{1 if led_end else 0}' "
            f"data-behmid='{1 if beh_mid else 0}' "
            f"data-behend='{1 if beh_end else 0}'>"
            f"<div class='tjhead'><span class='tjbadge {TRAJ_CLASS[c['type']]}'>"
            f"{esc(TRAJ_LABEL[c['type']])}</span>"
            f"<span class='tjshape' title='Fuseki / middlegame / yose: ahead (up), level (dot), behind (down)'>"
            f"{_shape_html(c['shape'])}</span></div>"
            f"<div class='tjspark'>{_traj_spark(c['curve'], won)}</div>"
            f"<div class='tjmeta'>{esc(g.get('date',''))} vs "
            f"{esc(g.get('opponent',''))} · {res} · "
            f"peak {c['mx']*100:.0f}% / trough {c['mn']*100:.0f}%</div></div>")

    def pct(a, b):
        return f"{round(a / b * 100)}%" if b else "—"
    conv = (
        "<div class='cvbox'>"
        "<div class='cvgrp'>"
        "<div class='cvstat'><div class='cvv' id='cvMid'>" + pct(lmw, lm) + "</div>"
        "<div class='cvl'>Middlegame lead conversion<span id='cvMidN'>" +
        (f"led into middlegame {lm} &middot; held {lmw}" if lm else "&mdash;") + "</span></div></div>"
        "<div class='cvstat'><div class='cvv' id='cvEnd'>" + pct(lew, le) + "</div>"
        "<div class='cvl'>Yose lead conversion<span id='cvEndN'>" +
        (f"led into yose {le} &middot; held {lew}" if le else "&mdash;") + "</span></div></div>"
        "</div>"
        "<div class='cvgrp'>"
        "<div class='cvstat'><div class='cvv' id='cbMid'>" + pct(bmw, bm) + "</div>"
        "<div class='cvl'>Middlegame comeback rate<span id='cbMidN'>" +
        (f"behind into middlegame {bm} &middot; turned it around {bmw}" if bm else "&mdash;") + "</span></div></div>"
        "<div class='cvstat'><div class='cvv' id='cbEnd'>" + pct(bew, be) + "</div>"
        "<div class='cvl'>Yose comeback rate<span id='cbEndN'>" +
        (f"behind into yose {be} &middot; turned it around {bew}" if be else "&mdash;") + "</span></div></div>"
        "</div>"
        "<div class='cvnote'><b>Lead conversion</b> = of the games you entered this "
        "phase clearly winning (win rate &ge; 90%), the share you went on to win. "
        "<b>Comeback rate</b> = of the games you entered this phase clearly losing "
        "(&le; 10%), the share you still turned around. Read them together: low "
        "conversion plus a high comeback rate means you enjoy a brawl but cannot hold "
        "an advantage -- raising your lead conversion is the shortest route to the "
        "next rank.</div>"
        "</div>")

    return ("<h2>Game trajectory &middot; shape classification</h2>"
            "<p class='sub'>Every game sorted by the <b>shape of your win-rate "
            "curve</b> -- led throughout, comeback win, lead thrown away, endgame "
            "collapse. Above 50% means you are ahead. "
            "<b>&#9650;&#9679;&#9660;</b> = ahead / level / behind across the three "
            "phases (fuseki, middlegame, yose).</p>"
            + conv
            + f"<div class='tjsum' id='trajSummary'>{''.join(chips)}</div>"
            + ins_html
            + "<div class='flcount' id='tjcount'></div>"
            + f"<div class='trajgrid'>{''.join(cards)}</div>"
            + TRAJ_JS)
