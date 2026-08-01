"""The Compare-two-reports page."""

import report          # noqa: E402

from .listing import list_reports, report_dir_from_rel
from .assets import COMPARE_CSS
from .shell import _page
from .htmlutil import _esc
from .config_jobs import _safe_cfg


# ---------------------------------------------------------------------------
# Compare two reports (e.g. 3 dan vs 4 dan) to see progress
# ---------------------------------------------------------------------------

def _report_metrics(rel):
    rdir = report_dir_from_rel(rel)
    if not rdir:
        return None
    cfg = _safe_cfg()
    games = report.load_games(rdir, cfg.get("games_dirs", []))
    if not games:
        return None
    agg = report.aggregate(games)
    pl, wl = [], []
    for g in games:
        for m in g.get("all_user_moves", []):
            pl.append(m.get("points_lost", 0) or 0)
            wl.append((m.get("winrate_lost", 0) or 0) * 100)
    try:
        source = report.source_label_from_path(rdir)
    except Exception:
        source = ""
    last_date = max((g.get("date") or "" for g in games), default="")
    wins, losses = agg["wins"], agg["losses"]
    winpct = (wins / (wins + losses) * 100) if (wins + losses) else 0.0
    # Lead conversion & comeback rate, by phase checkpoint
    lm = lmw = le = lew = 0
    bm = bmw = be = bew = 0
    for g in games:
        c = report.classify_trajectory(g)
        if not c:
            continue
        won = c["won"]
        md, ed = report._lead_flags(c["curve"])
        bd, bed = report._behind_flags(c["curve"])
        if md:
            lm += 1
            lmw += 1 if won else 0
        if ed:
            le += 1
            lew += 1 if won else 0
        if bd:
            bm += 1
            bmw += 1 if won else 0
        if bed:
            be += 1
            bew += 1 if won else 0
    return {
        "rel": rel, "label": rel, "source": source, "last_date": last_date,
        "n": agg["n"], "wins": wins, "losses": losses, "winpct": winpct,
        "apl": agg["avg_points_lost"], "brate": agg["blunder_rate"],
        "nb": agg["n_blunders"], "nb_per_game": (agg["n_blunders"] / agg["n"]
                                                 if agg["n"] else 0),
        "avg_moves": agg["avg_moves"], "n_moves": agg["n_user_moves"],
        "mid_conv": (lmw / lm * 100) if lm else None, "mid_led": lm,
        "end_conv": (lew / le * 100) if le else None, "end_led": le,
        "mid_come": (bmw / bm * 100) if bm else None, "mid_beh": bm,
        "end_come": (bew / be * 100) if be else None, "end_beh": be,
        "pl": pl, "wl": wl,
    }


A_COLOR, B_COLOR = "#4c6ef5", "#f76707"


def _cmp_hist_svg(av, bv, alab, blab, title, bin_size, x_note, thresh=None,
                  thresh_label=None, cap=None, pct=False, width=760, height=280):
    """Overlaid (grouped-bar) distribution of a per-move metric for two reports,
    each normalised to % of ITS OWN moves so different sample sizes are
    comparable.  Draws each report's mean line + the blunder threshold."""
    av = [v for v in av if v is not None]
    bv = [v for v in bv if v is not None]
    if not av and not bv:
        return ""
    meanA = sum(av) / len(av) if av else 0
    meanB = sum(bv) / len(bv) if bv else 0
    allv = av + bv
    if cap is not None:
        av = [min(v, cap) for v in av]
        bv = [min(v, cap) for v in bv]
        hi = cap
    else:
        hi = (int(max(allv) / bin_size) + 1) * bin_size
    lo = 0.0
    nbins = max(1, int((hi - lo) / bin_size + 0.5))

    def binned(vals):
        b = [0] * nbins
        for v in vals:
            i = int((v - lo) / bin_size)
            i = 0 if i < 0 else (nbins - 1 if i >= nbins else i)
            b[i] += 1
        tot = len(vals) or 1
        return [c / tot * 100 for c in b]  # percent of moves

    pa, pb = binned(av), binned(bv)
    ymax = max(pa + pb + [1])
    yscale = ymax * 1.18 or 1
    pad_l, pad_r, pad_t, pad_b = 46, 14, 44, 46
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    bw = plot_w / nbins

    def fmt(v):
        s = f"{v:.0f}" if abs(v - round(v)) < 1e-9 else f"{v:.1f}"
        return s + ("%" if pct else "")

    def py(v):
        return pad_t + (1 - v / yscale) * plot_h

    def px(v):
        x = pad_l + ((v - lo) / (hi - lo)) * plot_w
        return max(pad_l, min(pad_l + plot_w, x))

    p = [f'<svg viewBox="0 0 {width} {height}" width="100%" '
         f'preserveAspectRatio="xMidYMid meet" '
         f'style="background:#fff;border:1px solid #e3e3e3;border-radius:8px">']
    p.append(f'<text x="{pad_l}" y="20" font-size="14" font-weight="700" '
             f'fill="#1a202c">{_esc(title)}</text>')
    # legend
    lx = width - pad_r - 210
    for i, (lab, col) in enumerate([(alab, A_COLOR), (blab, B_COLOR)]):
        ly = 14 + i * 15
        p.append(f'<rect x="{lx}" y="{ly-8}" width="11" height="11" rx="2" '
                 f'fill="{col}" fill-opacity="0.85"/>')
        p.append(f'<text x="{lx+16}" y="{ly+1}" font-size="10.5" fill="#444">'
                 f'{_esc(lab)}</text>')
    for k in range(5):
        yval = yscale * k / 4
        y = py(yval)
        p.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" '
                 f'y2="{y:.1f}" stroke="#eee"/>')
        p.append(f'<text x="{pad_l-6}" y="{y+3:.1f}" font-size="10" '
                 f'text-anchor="end" fill="#888">{yval:.0f}%</text>')
    p.append(f'<text x="12" y="{pad_t-20}" font-size="10" fill="#888">share</text>')
    base = pad_t + plot_h

    def curve(series, col):
        pts = [(pad_l + (i + 0.5) * bw, py(series[i])) for i in range(nbins)]
        area = ("M " + f"{pts[0][0]:.1f},{base:.1f} "
                + " ".join(f"L {x:.1f},{y:.1f}" for x, y in pts)
                + f" L {pts[-1][0]:.1f},{base:.1f} Z")
        p.append(f'<path d="{area}" fill="{col}" fill-opacity="0.12"/>')
        p.append('<path d="M ' + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                 + f'" fill="none" stroke="{col}" stroke-width="2.2" '
                 f'stroke-linejoin="round"/>')
    curve(pa, A_COLOR)
    curve(pb, B_COLOR)
    step = max(1, nbins // 10)
    for i in range(0, nbins + 1, step):
        p.append(f'<text x="{pad_l + i*bw:.1f}" y="{height-pad_b+15:.1f}" '
                 f'font-size="9" fill="#888" text-anchor="middle">'
                 f'{fmt(lo + i*bin_size)}</text>')
    p.append(f'<text x="{pad_l+plot_w:.1f}" y="{height-pad_b+15:.1f}" '
             f'font-size="9" fill="#888" text-anchor="middle">'
             f'{fmt(hi)}{"+" if cap is not None else ""}</text>')
    if thresh is not None and lo <= thresh <= hi:
        tx = px(thresh)
        p.append(f'<line x1="{tx:.1f}" y1="{pad_t:.1f}" x2="{tx:.1f}" '
                 f'y2="{pad_t+plot_h:.1f}" stroke="#e03131" stroke-width="1.3" '
                 f'stroke-dasharray="4 3"/>')
        if thresh_label:
            p.append(f'<text x="{tx+4:.1f}" y="{pad_t+34:.1f}" font-size="10" '
                     f'fill="#e03131" font-weight="700">{_esc(thresh_label)}</text>')
    for mean, col in ((meanA, A_COLOR), (meanB, B_COLOR)):
        mx = px(mean)
        p.append(f'<line x1="{mx:.1f}" y1="{pad_t:.1f}" x2="{mx:.1f}" '
                 f'y2="{pad_t+plot_h:.1f}" stroke="{col}" stroke-width="1.6" '
                 f'stroke-dasharray="5 4"/>')
        p.append(f'<text x="{mx+3:.1f}" y="{pad_t+12:.1f}" font-size="10" '
                 f'fill="{col}" font-weight="700">mean {fmt(mean)}</text>')
    p.append(f'<text x="{pad_l}" y="{height-8}" font-size="10" fill="#888">'
             f'{_esc(x_note)}</text>')
    p.append("</svg>")
    return "".join(p)


def _cmp_select(cur, other_param_val, which):
    opts = []
    for r in list_reports():
        sel = " selected" if r["rel"] == cur else ""
        opts.append(f'<option value="{_esc(r["rel"])}"{sel}>{_esc(r["label"])}'
                    f'</option>')
    return (f"<select class='cmpsel' data-which='{which}' "
            f"data-other='{_esc(other_param_val)}'>{''.join(opts)}</select>")


NEUTRAL_PCT = 4.0   # changes smaller than this are treated as ≈ flat (noise)


def _delta_cell(a, b, lower_better, fmt="{:.2f}", suffix=""):
    """A colored delta cell.  green = B improved over A, red = got worse, gray =
    negligible (|Δ| < NEUTRAL_PCT%) or a neutral metric (lower_better is None,
    e.g. game length).  For a metric where lower is better, a HIGHER value is
    worse (red); this matches points lost per move, where lower is better."""
    d = b - a
    if abs(d) < 1e-9:
        return "<td class='dl dl-flat'>flat</td>"
    pct = (abs(d) / a * 100) if a else 0
    sign = "" if d < 0 else "+"
    arrow = "▼" if d < 0 else "▲"
    val = f"{sign}{fmt.format(d)}{suffix}"
    # neutral metric, or a change too small to matter → gray, no good/bad
    if lower_better is None or pct < NEUTRAL_PCT:
        mark = arrow if lower_better is None else "≈"
        return (f"<td class='dl dl-flat'>{mark} {val}"
                f"<span class='dlp'>{pct:.0f}%</span></td>")
    improved = (d < 0) if lower_better else (d > 0)
    cls = "dl-good" if improved else "dl-bad"
    return (f"<td class='dl {cls}'>{arrow} {val}"
            f"<span class='dlp'>{pct:.0f}%</span></td>")


def compare_page(a, b, embed=False):
    reps = list_reports()
    rels = [r["rel"] for r in reps]
    # defaults: two reports ordered older -> newer by last game date
    if not (a and b):
        by_date = sorted(reps, key=lambda r: r["summary"].get("last_date") or "")
        if len(by_date) >= 2:
            a = a or by_date[-2]["rel"]
            b = b or by_date[-1]["rel"]
        elif reps:
            a = a or reps[0]["rel"]
            b = b or reps[0]["rel"]
    ma, mb = _report_metrics(a), _report_metrics(b)
    head = ("" if embed else
            "<div class='hero'><a class='back' href='/'>&larr; Back to dashboard</a>"
            "<h1>Compare reports &middot; track progress</h1>"
            "<p class='sub'>Pick two reports and compare points lost per move, blunder rate and distributions.</p></div>")
    if not ma or not mb:
        body = (head + "<main><section class='card'>"
                "<div class='card-h'><h2>Report comparison</h2></div>"
                f"<div class='cmpbar'>A {_cmp_select(a, b or '', 'a')} "
                f"vs B {_cmp_select(b, a or '', 'b')}</div>"
                "<p class='empty'>Pick two reports that contain games.</p>"
                "</section></main>")
        return _page("Report comparison &middot; Mirror of Go", body, COMPARE_CSS)

    la = f"A - {ma['label']}" + (f" ({ma['source']})" if ma['source'] else "")
    lb = f"B - {mb['label']}" + (f" ({mb['source']})" if mb['source'] else "")

    # verdict from apl (avg points lost per move), lower is better
    da = mb["apl"] - ma["apl"]
    pct = (abs(da) / ma["apl"] * 100) if ma["apl"] else 0
    if da <= -0.05 and pct >= 5:
        vcls, vt, arr = "imp-good", "Improved", "&#9660;"
    elif da >= 0.05 and pct >= 5:
        vcls, vt, arr = "imp-bad", "Slipped", "&#9650;"
    else:
        vcls, vt, arr = "imp-flat", "Roughly flat", "&rarr;"
    direction = "down" if da < 0 else ("up" if da > 0 else "flat")
    verdict = (
        f"<div class='improve {vcls}'>"
        f"<div class='impl'>Progress verdict &middot; avg points lost per move (A &rarr; B)</div>"
        f"<div class='impv'><span class='ar'>{arr}</span>{vt}"
        f"<span class='pct'>{pct:.0f}%</span></div>"
        f"<div class='impd'>From <b>{_esc(ma['label'])}</b> to <b>{_esc(mb['label'])}</b>, "
        f"average points lost per move went {direction} from <b>{ma['apl']:.2f}</b> to "
        f"<b>{mb['apl']:.2f}</b> "
        f"({'losing' if da<0 else 'losing an extra'} {abs(da):.2f} pts/move). "
        f"The lower the loss per move, the steadier your play.</div></div>")

    # comparison table
    def row(label, av, bv, lower_better, fmt="{:.2f}", suffix=""):
        return (f"<tr><td class='ml'>{_esc(label)}</td>"
                f"<td>{fmt.format(av)}{suffix}</td>"
                f"<td>{fmt.format(bv)}{suffix}</td>"
                f"{_delta_cell(av, bv, lower_better, fmt, suffix)}</tr>")

    def conv_row(label, av, an, bv, bn):
        def cell(v, n):
            return (f"{v:.0f}% <span class='sub2'>({n})</span>"
                    if v is not None else "—")
        if av is None or bv is None:
            delta = "<td class='dl dl-flat'>—</td>"
        else:
            delta = _delta_cell(av, bv, False, "{:.0f}", "%")  # higher = better
        return (f"<tr><td class='ml'>{_esc(label)}</td>"
                f"<td>{cell(av, an)}</td><td>{cell(bv, bn)}</td>{delta}</tr>")
    table = (
        "<table class='cmp'><thead><tr><th></th>"
        f"<th>{_esc(ma['label'])}</th><th>{_esc(mb['label'])}</th>"
        "<th>Change (A&rarr;B)</th></tr></thead><tbody>"
        f"<tr><td class='ml'>Games / moves</td><td>{ma['n']} games &middot; {ma['n_moves']} moves</td>"
        f"<td>{mb['n']} games &middot; {mb['n_moves']} moves</td><td class='dl dl-flat'>&mdash;</td></tr>"
        + row("Win rate", ma["winpct"], mb["winpct"], False, "{:.0f}", "%")
        + conv_row("Middlegame lead conversion", ma["mid_conv"], ma["mid_led"],
                   mb["mid_conv"], mb["mid_led"])
        + conv_row("Yose lead conversion", ma["end_conv"], ma["end_led"],
                   mb["end_conv"], mb["end_led"])
        + conv_row("Middlegame comeback rate", ma["mid_come"], ma["mid_beh"],
                   mb["mid_come"], mb["mid_beh"])
        + conv_row("Yose comeback rate", ma["end_come"], ma["end_beh"],
                   mb["end_come"], mb["end_beh"])
        + row("Avg points lost per move", ma["apl"], mb["apl"], True, "{:.2f}")
        + row("Blunder rate (&ge;6 pts / WR &minus;15%)", ma["brate"], mb["brate"], True, "{:.1f}", "%")
        + row("Blunders per game", ma["nb_per_game"], mb["nb_per_game"], True, "{:.1f}")
        + row("Avg moves per game", ma["avg_moves"], mb["avg_moves"], False, "{:.0f}")
        + "</tbody></table>")

    apl_hist = _cmp_hist_svg(
        ma["pl"], mb["pl"], la, lb,
        "Points lost per move (distribution, share of moves)", 0.5,
        "x-axis: points lost on a single move (0.5-pt bins, 15+ pooled); "
        "the red dashed line is the 6-pt blunder line",
        thresh=6, thresh_label="blunder line 6 pts", cap=15)
    wl_hist = _cmp_hist_svg(
        ma["wl"], mb["wl"], la, lb,
        "Win-rate lost per move (distribution, share of moves)", 2.5,
        "x-axis: win-rate drop on a single move (2.5% bins, 50%+ pooled); "
        "the red dashed line is the 15% blunder line",
        thresh=15, thresh_label="blunder line 15%", cap=50, pct=True)

    body = (
        head + "<main>"
        "<section class='card'><div class='card-h'><h2>Choose two reports to compare</h2></div>"
        f"<div class='cmpbar'>A {_cmp_select(a, b, 'a')} "
        f"<span class='vs'>vs</span> B {_cmp_select(b, a, 'b')}</div></section>"
        f"<section class='card'>{verdict}{table}</section>"
        f"<section class='card'>{apl_hist}</section>"
        f"<section class='card'>{wl_hist}</section>"
        "</main>"
        "<script>document.querySelectorAll('.cmpsel').forEach(function(sel){"
        "sel.addEventListener('change',function(){"
        "var w=this.dataset.which, other=this.dataset.other, v=this.value;"
        "var a=(w==='a')?v:other, b=(w==='b')?v:other;"
        "var e=/[?&]embed=1/.test(location.search)?'&embed=1':'';"
        "location.href='/compare?a='+encodeURIComponent(a)+'&b='+encodeURIComponent(b)+e;"
        "});});</script>")
    return _page("Report comparison &middot; Mirror of Go", body, COMPARE_CSS)
