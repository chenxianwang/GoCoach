"""Reusable SVG chart building blocks and client-side data blobs."""

import json

from .constants import PHASES, PHASE_COLOR, PHASE_LABEL, PTS_BLUNDER, WR_BLUNDER
from .data import esc, parse_date


# ---- per-game data embedded for the JS date-range filter --------------------

def _games_data_js(chron):
    """Compact per-game records (oldest->newest) the in-page JS uses to
    recompute the overview cards/charts/histogram for any date range.
    Each phase carries raw [n, sum_points_lost, n_blunders_pts, n_blunders_wr]
    so move-weighted pooled averages can be recomputed client-side."""
    rows = []
    for g in chron:
        d = parse_date(g)
        won = g.get("won")
        ph = {}
        allm = g.get("all_user_moves", [])
        for phase in PHASES:
            sub = allm if phase == "overall" else [
                m for m in allm if m.get("phase") == phase]
            n = len(sub)
            loss = sum((m.get("points_lost", 0) or 0) for m in sub)
            nbp = sum(1 for m in sub
                      if (m.get("points_lost", 0) or 0) >= PTS_BLUNDER)
            nbw = sum(1 for m in sub
                      if (m.get("winrate_lost", 0) or 0) >= WR_BLUNDER)
            nbe = sum(1 for m in sub
                      if (m.get("points_lost", 0) or 0) >= PTS_BLUNDER
                      or (m.get("winrate_lost", 0) or 0) >= WR_BLUNDER)
            ph[phase] = [n, round(loss, 3), nbp, nbw, nbe]
        # per-move [points_lost, winrate_lost%] for move-level distribution plots
        pm = [[round(m.get("points_lost", 0) or 0, 1),
               round((m.get("winrate_lost", 0) or 0) * 100, 1)]
              for m in allm]
        rows.append({
            "d": d.isoformat() if d else None,
            "w": 1 if won is True else (0 if won is False else -1),
            "mv": len(g.get("moves", [])),
            "p": ph,
            "pm": pm,
        })
    return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))


def _date_filter_bar():
    """Shared date-range control inserted at the top of every module. All bars
    are kept in sync by the GR JS module (they share class names)."""
    return (
        "<div class='datebar'>"
        "<span class='navlbl' style='width:auto'>Date range</span>"
        "<input type='date' class='dffrom' "
        "onchange=\"GR.manual(this)\">"
        "<span class='dfsep'>—</span>"
        "<input type='date' class='dfto' "
        "onchange=\"GR.manual(this)\">"
        "<button class='navbtn dfp' data-days='30' "
        "onclick=\"GR.preset(30,this)\">Last 30 days</button>"
        "<button class='navbtn dfp' data-days='90' "
        "onclick=\"GR.preset(90,this)\">Last 90 days</button>"
        "<button class='navbtn dfp on dfreset' data-days='all' "
        "onclick=\"GR.preset(null,this)\">All</button>"
        "</div>")


# ---- trend chart (multi-series line) ---------------------------------------

def trend_chart(title, labels, series, ylabel, width=760, height=250,
                tip_labels=None, avg_overrides=None):
    """series: list of (name, color, [values aligned with labels, None=gap]).

    labels     -- short x-axis tick text (e.g. game number 1,2,3...).
    tip_labels -- richer text shown in the hover tooltip (e.g. "Game 3  06-18");
                  falls back to `labels` when not given.
    """
    tips = tip_labels or labels
    pad_l, pad_r, pad_t, pad_b = 46, 14, 54, 50
    n = len(labels)
    allv = [v for _, _, vals in series for v in vals if v is not None]
    ymax = max(allv) * 1.18 if allv and max(allv) > 0 else 1.0

    def px(i):
        if n <= 1:
            return (pad_l + width - pad_r) / 2
        return pad_l + i * (width - pad_l - pad_r) / (n - 1)

    def py(v):
        return pad_t + (1 - v / ymax) * (height - pad_t - pad_b)

    p = [f'<svg viewBox="0 0 {width} {height}" width="100%" '
         f'preserveAspectRatio="xMidYMid meet" '
         f'style="background:#fff;border:1px solid #e3e3e3;border-radius:8px">']
    p.append(f'<text x="{pad_l}" y="20" font-size="14" font-weight="700" '
             f'fill="#1a202c">{esc(title)}</text>')

    # per-phase averages, in the title band (top-right) so each phase's typical
    # level reads at a glance without hovering. Laid out as one horizontal row,
    # above the plot, so it never overlaps the curves. Colour-matched.
    avgs = []
    for si, (sname, scolor, svals) in enumerate(series):
        if avg_overrides is not None and si < len(avg_overrides):
            # caller supplies the headline (move-weighted) figure as a string so
            # the chart's phase mean matches the overview cards exactly.
            txt = avg_overrides[si]
        else:
            nums = [v for v in svals if v is not None]
            av = (sum(nums) / len(nums)) if nums else 0.0
            txt = f"{av:.1f}"
        avgs.append((sname, scolor, txt))
    entry_w = 74
    row_w = 44 + entry_w * len(avgs)
    ax = max(pad_l, width - pad_r - row_w)
    ay = 20
    p.append(f'<text x="{ax:.1f}" y="{ay}" font-size="9.5" fill="#aaa" '
             f'font-weight="600">phase mean</text>')
    ax += 44
    for sname, scolor, txt in avgs:
        p.append(f'<circle cx="{ax+3:.1f}" cy="{ay-3:.1f}" r="3" '
                 f'fill="{scolor}"/>')
        p.append(f'<text x="{ax+11:.1f}" y="{ay}" font-size="10" '
                 f'fill="#444">{esc(sname)} {esc(txt)}</text>')
        ax += entry_w

    # y gridlines + labels
    for k in range(5):
        yval = ymax * k / 4
        y = py(yval)
        p.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" '
                 f'y2="{y:.1f}" stroke="#eee"/>')
        p.append(f'<text x="{pad_l-6}" y="{y+3:.1f}" font-size="10" '
                 f'text-anchor="end" fill="#888">{yval:.1f}</text>')
    p.append(f'<text x="12" y="{pad_t-30}" font-size="10" fill="#888">'
             f'{esc(ylabel)}</text>')

    # x ticks (sequence numbers are short -> render horizontally centered)
    step = max(1, n // 12)
    for i in range(0, n, step):
        x = px(i)
        p.append(f'<text x="{x:.1f}" y="{height-pad_b+16:.1f}" font-size="10" '
                 f'fill="#888" text-anchor="middle">{esc(labels[i])}</text>')

    # series (each wrapped in a toggleable group keyed by index)
    for si, (name, color, vals) in enumerate(series):
        p.append(f'<g class="tser" data-si="{si}">')
        seg = []
        for i, v in enumerate(vals):
            if v is None:
                _flush_segment(p, seg, color)
                seg = []
            else:
                seg.append((px(i), py(v)))
        _flush_segment(p, seg, color)
        for i, v in enumerate(vals):
            if v is not None:
                p.append(f'<circle cx="{px(i):.1f}" cy="{py(v):.1f}" r="2.6" '
                         f'fill="{color}"/>')
                # larger transparent hit area so the value is easy to hover;
                # data-tip is read by the floating tooltip script.
                tip = f"{name} &middot; {tips[i]}: {v}"
                p.append(f'<circle class="pt" cx="{px(i):.1f}" '
                         f'cy="{py(v):.1f}" r="9" fill="transparent" '
                         f'data-tip="{esc(tip)}"></circle>')
        p.append('</g>')

    # legend — click an entry to show/hide that series.
    lx = pad_l
    ly = height - 8
    for si, (name, color, _) in enumerate(series):
        w = 20 + len(name) * 6.6
        p.append(f'<g class="tleg" data-si="{si}" '
                 f'onclick="toggleSeries(this)" style="cursor:pointer">')
        p.append(f'<rect x="{lx-2:.1f}" y="{ly-11:.1f}" width="{w:.1f}" '
                 f'height="16" fill="transparent"/>')
        p.append(f'<line x1="{lx}" y1="{ly-4}" x2="{lx+16}" y2="{ly-4}" '
                 f'stroke="{color}" stroke-width="2.5"/>')
        p.append(f'<text x="{lx+20}" y="{ly}" font-size="10" fill="#444">'
                 f'{esc(name)}</text>')
        p.append('</g>')
        lx += 26 + len(name) * 6.4
    p.append("</svg>")
    return "".join(p)


def _flush_segment(parts, seg, color):
    if len(seg) >= 2:
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in seg)
        parts.append(f'<polyline fill="none" stroke="{color}" '
                     f'stroke-width="2" points="{pts}"/>')


def moves_hist_svg(counts, width=760, height=260, bin_size=20):
    """Histogram of game length (total moves), binned into 20-move buckets."""
    counts = [c for c in counts if c and c > 0]
    if not counts:
        return ""
    pad_l, pad_r, pad_t, pad_b = 46, 14, 40, 46
    lo = (min(counts) // bin_size) * bin_size
    hi = ((max(counts) // bin_size) + 1) * bin_size
    nbins = max(1, (hi - lo) // bin_size)
    bins = [0] * nbins
    for c in counts:
        idx = min(nbins - 1, (c - lo) // bin_size)
        bins[idx] += 1
    ymax = max(bins) if bins else 1
    yscale = (ymax * 1.18) or 1
    avg = sum(counts) / len(counts)

    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    bw = plot_w / nbins

    def py(v):
        return pad_t + (1 - v / yscale) * plot_h

    p = [f'<svg viewBox="0 0 {width} {height}" width="100%" '
         f'preserveAspectRatio="xMidYMid meet" '
         f'style="background:#fff;border:1px solid #e3e3e3;border-radius:8px">']
    p.append(f'<text x="{pad_l}" y="20" font-size="14" font-weight="700" '
             f'fill="#1a202c">Game length distribution</text>')
    # y gridlines + labels
    for k in range(5):
        yval = yscale * k / 4
        y = py(yval)
        p.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" '
                 f'y2="{y:.1f}" stroke="#eee"/>')
        p.append(f'<text x="{pad_l-6}" y="{y+3:.1f}" font-size="10" '
                 f'text-anchor="end" fill="#888">{yval:.0f}</text>')
    p.append(f'<text x="12" y="{pad_t-18}" font-size="10" fill="#888">games</text>')
    # bars
    for i, c in enumerate(bins):
        x = pad_l + i * bw
        y = py(c)
        h = (pad_t + plot_h) - y
        b0 = lo + i * bin_size
        b1 = b0 + bin_size
        tip = f"{b0}-{b1} moves: {c} game(s)"
        p.append(f'<rect x="{x+1.5:.1f}" y="{y:.1f}" width="{bw-3:.1f}" '
                 f'height="{max(0,h):.1f}" fill="#4c6ef5" fill-opacity="0.82" '
                 f'rx="2" data-tip="{esc(tip)}"></rect>')
        if c > 0:
            p.append(f'<text x="{x+bw/2:.1f}" y="{y-4:.1f}" font-size="10" '
                     f'fill="#444" text-anchor="middle">{c}</text>')
        # x tick at left edge of each bar
        p.append(f'<text x="{x:.1f}" y="{height-pad_b+15:.1f}" font-size="9.5" '
                 f'fill="#888" text-anchor="middle">{b0}</text>')
    # final right edge tick
    p.append(f'<text x="{pad_l+plot_w:.1f}" y="{height-pad_b+15:.1f}" '
             f'font-size="9.5" fill="#888" text-anchor="middle">{hi}</text>')
    # average line
    ax = pad_l + ((avg - lo) / (hi - lo)) * plot_w
    ax = max(pad_l, min(pad_l + plot_w, ax))
    p.append(f'<line x1="{ax:.1f}" y1="{pad_t:.1f}" x2="{ax:.1f}" '
             f'y2="{pad_t+plot_h:.1f}" stroke="#e8590c" stroke-width="1.6" '
             f'stroke-dasharray="5 4"/>')
    p.append(f'<text x="{ax+4:.1f}" y="{pad_t+12:.1f}" font-size="10" '
             f'fill="#e8590c" font-weight="700">mean {avg:.0f}</text>')
    p.append(f'<text x="{pad_l}" y="{height-8}" font-size="10" fill="#888">'
             f'x-axis: total moves per game ({bin_size} moves per bin)</text>')
    p.append("</svg>")
    return "".join(p)


def metric_hist_svg(values, title, bin_size, x_note, thresh=None,
                    thresh_label=None, cap=None, pct=False, color="#4c6ef5",
                    width=760, height=260):
    """Move-level distribution histogram of a float metric (points lost / winrate
    drop) across every analysed move.  `cap` clamps a long tail into an overflow
    bin; `thresh` draws the blunder threshold line.  y-axis counts moves."""
    vals = [v for v in values if v is not None]
    if not vals:
        return ""
    mean = sum(vals) / len(vals)
    if cap is not None:
        vals = [min(v, cap) for v in vals]
        hi = cap
    else:
        hi = (int(max(vals) / bin_size) + 1) * bin_size
    lo = 0.0
    nbins = max(1, int((hi - lo) / bin_size + 0.5))
    bins = [0] * nbins
    for v in vals:
        idx = int((v - lo) / bin_size)
        if idx < 0:
            idx = 0
        if idx >= nbins:
            idx = nbins - 1
        bins[idx] += 1
    ymax = max(bins) or 1
    yscale = ymax * 1.18 or 1
    pad_l, pad_r, pad_t, pad_b = 46, 14, 40, 46
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    bw = plot_w / nbins

    def fmt(v):
        s = f"{v:.0f}" if abs(v - round(v)) < 1e-9 else f"{v:.1f}"
        return s + ("%" if pct else "")

    def py(v):
        return pad_t + (1 - v / yscale) * plot_h

    def px(v):  # value -> x
        x = pad_l + ((v - lo) / (hi - lo)) * plot_w
        return max(pad_l, min(pad_l + plot_w, x))

    p = [f'<svg viewBox="0 0 {width} {height}" width="100%" '
         f'preserveAspectRatio="xMidYMid meet" '
         f'style="background:#fff;border:1px solid #e3e3e3;border-radius:8px">']
    p.append(f'<text x="{pad_l}" y="20" font-size="14" font-weight="700" '
             f'fill="#1a202c">{esc(title)}</text>')
    for k in range(5):
        yval = yscale * k / 4
        y = py(yval)
        p.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" '
                 f'y2="{y:.1f}" stroke="#eee"/>')
        p.append(f'<text x="{pad_l-6}" y="{y+3:.1f}" font-size="10" '
                 f'text-anchor="end" fill="#888">{yval:.0f}</text>')
    p.append(f'<text x="12" y="{pad_t-18}" font-size="10" fill="#888">moves</text>')
    # frequency-polygon / area curve through the bin centres
    base = pad_t + plot_h
    pts = [(pad_l + (i + 0.5) * bw, py(bins[i])) for i in range(nbins)]
    area = (f"M {pts[0][0]:.1f},{base:.1f} "
            + " ".join(f"L {x:.1f},{y:.1f}" for x, y in pts)
            + f" L {pts[-1][0]:.1f},{base:.1f} Z")
    p.append(f'<path d="{area}" fill="{color}" fill-opacity="0.16"/>')
    p.append('<path d="M ' + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
             + f'" fill="none" stroke="{color}" stroke-width="2" '
             f'stroke-linejoin="round"/>')
    # x ticks
    step = max(1, nbins // 10)
    for i in range(0, nbins + 1, step):
        xx = pad_l + i * bw
        p.append(f'<text x="{xx:.1f}" y="{height-pad_b+15:.1f}" font-size="9" '
                 f'fill="#888" text-anchor="middle">{fmt(lo + i * bin_size)}</text>')
    p.append(f'<text x="{pad_l+plot_w:.1f}" y="{height-pad_b+15:.1f}" '
             f'font-size="9" fill="#888" text-anchor="middle">'
             f'{fmt(hi)}{"+" if cap is not None else ""}</text>')
    # threshold line (the blunder line)
    if thresh is not None and lo <= thresh <= hi:
        tx = px(thresh)
        p.append(f'<line x1="{tx:.1f}" y1="{pad_t:.1f}" x2="{tx:.1f}" '
                 f'y2="{pad_t+plot_h:.1f}" stroke="#e03131" stroke-width="1.4" '
                 f'stroke-dasharray="4 3"/>')
        if thresh_label:
            p.append(f'<text x="{tx+4:.1f}" y="{pad_t+24:.1f}" font-size="10" '
                     f'fill="#e03131" font-weight="700">{esc(thresh_label)}</text>')
    # mean line
    mx = px(mean)
    p.append(f'<line x1="{mx:.1f}" y1="{pad_t:.1f}" x2="{mx:.1f}" '
             f'y2="{pad_t+plot_h:.1f}" stroke="#e8590c" stroke-width="1.6" '
             f'stroke-dasharray="5 4"/>')
    p.append(f'<text x="{mx+4:.1f}" y="{pad_t+12:.1f}" font-size="10" '
             f'fill="#e8590c" font-weight="700">mean {fmt(mean)}</text>')
    p.append(f'<text x="{pad_l}" y="{height-8}" font-size="10" fill="#888">'
             f'{esc(x_note)}</text>')
    p.append("</svg>")
    return "".join(p)


def _date_filter_js(chron):
    """The global GR module: shared date-range state, synced date bars, and a
    full client-side recompute of the overview cards / 4 trend charts /
    histogram for the selected range (JS ports of trend_chart & moves_hist)."""
    data = _games_data_js(chron)
    meta = json.dumps({
        "phases": PHASES,
        "labels": [PHASE_LABEL[p] for p in PHASES],
        "colors": [PHASE_COLOR[p] for p in PHASES],
    }, ensure_ascii=False, separators=(",", ":"))
    js = r"""
<script>
(function(){
  var GAMES = __GAMES__;       // oldest -> newest
  var META  = __META__;
  var GR = window.GR = window.GR || {};
  GR.games = GAMES;
  GR.range = {from:null, to:null};

  function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');}

  GR.inRange = function(d){
    if(!d) return !(GR.range.from || GR.range.to);   // undated: only when "All"
    if(GR.range.from && d < GR.range.from) return false;
    if(GR.range.to   && d > GR.range.to)   return false;
    return true;
  };
  function syncInputs(){
    document.querySelectorAll('.dffrom').forEach(function(e){
      e.value = GR.range.from || '';});
    document.querySelectorAll('.dfto').forEach(function(e){
      e.value = GR.range.to || '';});
  }
  function markPreset(days){
    document.querySelectorAll('.dfp').forEach(function(b){
      b.classList.toggle('on', b.getAttribute('data-days') === days);});
  }
  function fire(){ document.dispatchEvent(new CustomEvent('grdate')); }

  GR.setRange = function(f,t){
    GR.range.from = f || null; GR.range.to = t || null;
    syncInputs(); fire();
  };
  GR.manual = function(el){
    var bar = el.closest('.datebar');
    var f = bar.querySelector('.dffrom').value;
    var t = bar.querySelector('.dfto').value;
    GR.range.from = f || null; GR.range.to = t || null;
    syncInputs();
    markPreset(null);                       // manual edit clears preset highlight
    fire();
  };
  GR.preset = function(days, btn){
    if(days === null){ GR.range.from = null; GR.range.to = null; markPreset('all'); }
    else {
      var to = new Date();
      var from = new Date(); from.setDate(from.getDate() - days);
      function iso(x){ return x.toISOString().slice(0,10); }
      GR.range.from = iso(from); GR.range.to = iso(to);
      markPreset(String(days));
    }
    syncInputs(); fire();
  };
  GR.filtered = function(){
    return GAMES.filter(function(g){ return GR.inRange(g.d); });
  };

  // ---- overview recompute (cards + charts + histogram) ---------------------
  function pooled(fg){
    var st = {}; META.phases.forEach(function(p){
      st[p] = {cnt:0, loss:0, nbp:0, nbw:0, nbe:0}; });
    fg.forEach(function(g){
      META.phases.forEach(function(p){
        var a = g.p[p]; st[p].cnt += a[0]; st[p].loss += a[1];
        st[p].nbp += a[2]; st[p].nbw += a[3]; st[p].nbe += (a[4]||0);
      });
    });
    return st;
  }
  function renderCards(fg){
    var el = document.getElementById('homeCards'); if(!el) return;
    var wins=0, losses=0;
    fg.forEach(function(g){ if(g.w===1) wins++; else if(g.w===0) losses++; });
    var o = pooled(fg).overall;
    var apl = o.cnt ? (o.loss/o.cnt) : 0;
    var brate = o.cnt ? (o.nbe/o.cnt*100) : 0;
    var mvSum=0, mvCnt=0;
    fg.forEach(function(g){ mvSum += g.mv; mvCnt++; });
    var amoves = mvCnt ? Math.round(mvSum/mvCnt) : 0;
    var rows = [
      [wins+'\u2013'+losses, 'Win \u2013 Loss'],
      [apl.toFixed(2), 'Avg points lost per move'],
      [brate.toFixed(1)+'%', 'Blunder rate (\u22656 pts or WR \u221215%)'],
      [String(o.nbe), 'Total blunders'],
      [String(amoves), 'Avg moves per game'],
    ];
    el.innerHTML = rows.map(function(r){
      return "<div class='card'><div class='v'>"+esc(r[0])+
             "</div><div class='l'>"+esc(r[1])+"</div></div>"; }).join('');
  }

  function trendChartSVG(title, labels, series, ylabel, tips, avgOv){
    var W=760, H=250, pl=46, pr=14, pt=54, pb=50;
    var n=labels.length;
    var allv=[]; series.forEach(function(s){ s[2].forEach(function(v){
      if(v!==null && v!==undefined) allv.push(v); }); });
    var mx = allv.length ? Math.max.apply(null, allv) : 0;
    var ymax = (allv.length && mx>0) ? mx*1.18 : 1.0;
    function px(i){ return n<=1 ? (pl+W-pr)/2 : pl + i*(W-pl-pr)/(n-1); }
    function py(v){ return pt + (1 - v/ymax)*(H-pt-pb); }
    var p=['<svg viewBox="0 0 '+W+' '+H+'" width="100%" '+
      'preserveAspectRatio="xMidYMid meet" '+
      'style="background:#fff;border:1px solid #e3e3e3;border-radius:8px">'];
    p.push('<text x="'+pl+'" y="20" font-size="14" font-weight="700" '+
      'fill="#1a202c">'+esc(title)+'</text>');
    // phase-mean row (top-right)
    var entryW=74, rowW=44+entryW*series.length;
    var ax=Math.max(pl, W-pr-rowW), ay=20;
    p.push('<text x="'+ax.toFixed(1)+'" y="'+ay+'" font-size="9.5" fill="#aaa" '+
      'font-weight="600">phase mean</text>');
    ax+=44;
    series.forEach(function(s,si){
      p.push('<circle cx="'+(ax+3).toFixed(1)+'" cy="'+(ay-3).toFixed(1)+
        '" r="3" fill="'+s[1]+'"/>');
      p.push('<text x="'+(ax+11).toFixed(1)+'" y="'+ay+'" font-size="10" '+
        'fill="#444">'+esc(s[0])+' '+esc(avgOv[si])+'</text>');
      ax+=entryW;
    });
    for(var k=0;k<5;k++){
      var yval=ymax*k/4, y=py(yval);
      p.push('<line x1="'+pl+'" y1="'+y.toFixed(1)+'" x2="'+(W-pr)+'" y2="'+
        y.toFixed(1)+'" stroke="#eee"/>');
      p.push('<text x="'+(pl-6)+'" y="'+(y+3).toFixed(1)+'" font-size="10" '+
        'text-anchor="end" fill="#888">'+yval.toFixed(1)+'</text>');
    }
    p.push('<text x="12" y="'+(pt-30)+'" font-size="10" fill="#888">'+
      esc(ylabel)+'</text>');
    var step=Math.max(1, Math.floor(n/12));
    for(var i=0;i<n;i+=step){
      p.push('<text x="'+px(i).toFixed(1)+'" y="'+(H-pb+16).toFixed(1)+
        '" font-size="10" fill="#888" text-anchor="middle">'+esc(labels[i])+
        '</text>');
    }
    series.forEach(function(s,si){
      p.push('<g class="tser" data-si="'+si+'">');
      var seg=[];
      function flush(){ if(seg.length>=2){
        p.push('<polyline fill="none" stroke="'+s[1]+'" stroke-width="2" '+
          'points="'+seg.map(function(q){return q[0].toFixed(1)+','+
          q[1].toFixed(1);}).join(' ')+'"/>'); } seg=[]; }
      s[2].forEach(function(v,ii){
        if(v===null||v===undefined){ flush(); } else { seg.push([px(ii),py(v)]); }
      });
      flush();
      s[2].forEach(function(v,ii){
        if(v===null||v===undefined) return;
        p.push('<circle cx="'+px(ii).toFixed(1)+'" cy="'+py(v).toFixed(1)+
          '" r="2.6" fill="'+s[1]+'"/>');
        var tip=s[0]+' \u00b7 '+tips[ii]+': '+v;
        p.push('<circle class="pt" cx="'+px(ii).toFixed(1)+'" cy="'+
          py(v).toFixed(1)+'" r="9" fill="transparent" data-tip="'+esc(tip)+
          '"></circle>');
      });
      p.push('</g>');
    });
    var lx=pl, ly=H-8;
    series.forEach(function(s,si){
      var w=20+s[0].length*6.6;
      p.push('<g class="tleg" data-si="'+si+'" onclick="toggleSeries(this)" '+
        'style="cursor:pointer">');
      p.push('<rect x="'+(lx-2).toFixed(1)+'" y="'+(ly-11).toFixed(1)+
        '" width="'+w.toFixed(1)+'" height="16" fill="transparent"/>');
      p.push('<line x1="'+lx+'" y1="'+(ly-4)+'" x2="'+(lx+16)+'" y2="'+(ly-4)+
        '" stroke="'+s[1]+'" stroke-width="2.5"/>');
      p.push('<text x="'+(lx+20)+'" y="'+ly+'" font-size="10" fill="#444">'+
        esc(s[0])+'</text>');
      p.push('</g>');
      lx += 26 + s[0].length*6.4;
    });
    p.push('</svg>');
    return p.join('');
  }

  function movesHistSVG(counts){
    counts = counts.filter(function(c){ return c && c>0; });
    if(!counts.length) return '';
    var W=760,H=260,bin=20,pl=46,pr=14,pt=40,pb=46;
    var mn=Math.min.apply(null,counts), mxc=Math.max.apply(null,counts);
    var lo=Math.floor(mn/bin)*bin, hi=(Math.floor(mxc/bin)+1)*bin;
    var nbins=Math.max(1,Math.floor((hi-lo)/bin));
    var bins=[]; for(var b=0;b<nbins;b++) bins.push(0);
    counts.forEach(function(c){
      var idx=Math.min(nbins-1, Math.floor((c-lo)/bin)); bins[idx]++; });
    var ymax=Math.max.apply(null,bins)||1, yscale=(ymax*1.18)||1;
    var avg=counts.reduce(function(a,b){return a+b;},0)/counts.length;
    var plotW=W-pl-pr, plotH=H-pt-pb, bw=plotW/nbins;
    function py(v){ return pt + (1 - v/yscale)*plotH; }
    var p=['<svg viewBox="0 0 '+W+' '+H+'" width="100%" '+
      'preserveAspectRatio="xMidYMid meet" '+
      'style="background:#fff;border:1px solid #e3e3e3;border-radius:8px">'];
    p.push('<text x="'+pl+'" y="20" font-size="14" font-weight="700" '+
      'fill="#1a202c">Game length distribution</text>');
    for(var k=0;k<5;k++){
      var yval=yscale*k/4, y=py(yval);
      p.push('<line x1="'+pl+'" y1="'+y.toFixed(1)+'" x2="'+(W-pr)+'" y2="'+
        y.toFixed(1)+'" stroke="#eee"/>');
      p.push('<text x="'+(pl-6)+'" y="'+(y+3).toFixed(1)+'" font-size="10" '+
        'text-anchor="end" fill="#888">'+yval.toFixed(0)+'</text>');
    }
    p.push('<text x="12" y="'+(pt-18)+'" font-size="10" fill="#888">games</text>');
    bins.forEach(function(c,i){
      var x=pl+i*bw, y=py(c), h=(pt+plotH)-y, b0=lo+i*bin, b1=b0+bin;
      var tip=b0+'\u2013'+b1+' moves: '+c+' game(s)';
      p.push('<rect x="'+(x+1.5).toFixed(1)+'" y="'+y.toFixed(1)+'" width="'+
        (bw-3).toFixed(1)+'" height="'+Math.max(0,h).toFixed(1)+
        '" fill="#4c6ef5" fill-opacity="0.82" rx="2" data-tip="'+esc(tip)+
        '"></rect>');
      if(c>0) p.push('<text x="'+(x+bw/2).toFixed(1)+'" y="'+(y-4).toFixed(1)+
        '" font-size="10" fill="#444" text-anchor="middle">'+c+'</text>');
      p.push('<text x="'+x.toFixed(1)+'" y="'+(H-pb+15).toFixed(1)+
        '" font-size="9.5" fill="#888" text-anchor="middle">'+b0+'</text>');
    });
    p.push('<text x="'+(pl+plotW).toFixed(1)+'" y="'+(H-pb+15).toFixed(1)+
      '" font-size="9.5" fill="#888" text-anchor="middle">'+hi+'</text>');
    var axp=pl+((avg-lo)/(hi-lo))*plotW;
    axp=Math.max(pl, Math.min(pl+plotW, axp));
    p.push('<line x1="'+axp.toFixed(1)+'" y1="'+pt.toFixed(1)+'" x2="'+
      axp.toFixed(1)+'" y2="'+(pt+plotH).toFixed(1)+
      '" stroke="#e8590c" stroke-width="1.6" stroke-dasharray="5 4"/>');
    p.push('<text x="'+(axp+4).toFixed(1)+'" y="'+(pt+12).toFixed(1)+
      '" font-size="10" fill="#e8590c" font-weight="700">mean '+
      avg.toFixed(0)+'</text>');
    p.push('<text x="'+pl+'" y="'+(H-8)+'" font-size="10" fill="#888">'+
      'x-axis: total moves per game ('+
      bin+' moves per bin)</text>');
    p.push('</svg>');
    return p.join('');
  }

  function distHistSVG(values, title, bin, xNote, thresh, threshLabel, cap, pct, color){
    var vals=values.filter(function(v){return v!==null&&v!==undefined;});
    if(!vals.length) return '';
    var mean=vals.reduce(function(a,b){return a+b;},0)/vals.length;
    var hi;
    if(cap!=null){ vals=vals.map(function(v){return Math.min(v,cap);}); hi=cap; }
    else { hi=(Math.floor(Math.max.apply(null,vals)/bin)+1)*bin; }
    var lo=0, nbins=Math.max(1, Math.round((hi-lo)/bin));
    var bins=[]; for(var b=0;b<nbins;b++) bins.push(0);
    vals.forEach(function(v){ var idx=Math.floor((v-lo)/bin);
      if(idx<0)idx=0; if(idx>=nbins)idx=nbins-1; bins[idx]++; });
    var ymax=Math.max.apply(null,bins)||1, yscale=ymax*1.18||1;
    var W=760,H=260,pl=46,pr=14,pt=40,pb=46;
    var plotW=W-pl-pr, plotH=H-pt-pb, bw=plotW/nbins;
    function fmt(v){ var s=(Math.abs(v-Math.round(v))<1e-9)?v.toFixed(0):v.toFixed(1);
      return s+(pct?'%':''); }
    function py(v){ return pt+(1-v/yscale)*plotH; }
    function px(v){ var x=pl+((v-lo)/(hi-lo))*plotW; return Math.max(pl,Math.min(pl+plotW,x)); }
    var p=['<svg viewBox="0 0 '+W+' '+H+'" width="100%" '+
      'preserveAspectRatio="xMidYMid meet" '+
      'style="background:#fff;border:1px solid #e3e3e3;border-radius:8px">'];
    p.push('<text x="'+pl+'" y="20" font-size="14" font-weight="700" '+
      'fill="#1a202c">'+esc(title)+'</text>');
    for(var k=0;k<5;k++){ var yv=yscale*k/4, y=py(yv);
      p.push('<line x1="'+pl+'" y1="'+y.toFixed(1)+'" x2="'+(W-pr)+'" y2="'+
        y.toFixed(1)+'" stroke="#eee"/>');
      p.push('<text x="'+(pl-6)+'" y="'+(y+3).toFixed(1)+'" font-size="10" '+
        'text-anchor="end" fill="#888">'+yv.toFixed(0)+'</text>'); }
    p.push('<text x="12" y="'+(pt-18)+'" font-size="10" fill="#888">moves</text>');
    var base=pt+plotH;
    var pts=bins.map(function(c,i){ return [pl+(i+0.5)*bw, py(c)]; });
    var area='M '+pts[0][0].toFixed(1)+','+base.toFixed(1)+' '+
      pts.map(function(q){return 'L '+q[0].toFixed(1)+','+q[1].toFixed(1);}).join(' ')+
      ' L '+pts[pts.length-1][0].toFixed(1)+','+base.toFixed(1)+' Z';
    p.push('<path d="'+area+'" fill="'+color+'" fill-opacity="0.16"/>');
    p.push('<path d="M '+pts.map(function(q){return q[0].toFixed(1)+','+q[1].toFixed(1);}).join(' L ')+
      '" fill="none" stroke="'+color+'" stroke-width="2" stroke-linejoin="round"/>');
    var step=Math.max(1, Math.floor(nbins/10));
    for(var t=0;t<=nbins;t+=step){
      p.push('<text x="'+(pl+t*bw).toFixed(1)+'" y="'+(H-pb+15).toFixed(1)+
        '" font-size="9" fill="#888" text-anchor="middle">'+fmt(lo+t*bin)+'</text>'); }
    p.push('<text x="'+(pl+plotW).toFixed(1)+'" y="'+(H-pb+15).toFixed(1)+
      '" font-size="9" fill="#888" text-anchor="middle">'+fmt(hi)+((cap!=null)?'+':'')+'</text>');
    if(thresh!=null && thresh>=lo && thresh<=hi){ var tx=px(thresh);
      p.push('<line x1="'+tx.toFixed(1)+'" y1="'+pt.toFixed(1)+'" x2="'+tx.toFixed(1)+
        '" y2="'+(pt+plotH).toFixed(1)+'" stroke="#e03131" stroke-width="1.4" stroke-dasharray="4 3"/>');
      if(threshLabel) p.push('<text x="'+(tx+4).toFixed(1)+'" y="'+(pt+24).toFixed(1)+
        '" font-size="10" fill="#e03131" font-weight="700">'+esc(threshLabel)+'</text>'); }
    var mx=px(mean);
    p.push('<line x1="'+mx.toFixed(1)+'" y1="'+pt.toFixed(1)+'" x2="'+mx.toFixed(1)+
      '" y2="'+(pt+plotH).toFixed(1)+'" stroke="#e8590c" stroke-width="1.6" stroke-dasharray="5 4"/>');
    p.push('<text x="'+(mx+4).toFixed(1)+'" y="'+(pt+12).toFixed(1)+
      '" font-size="10" fill="#e8590c" font-weight="700">mean '+fmt(mean)+'</text>');
    p.push('<text x="'+pl+'" y="'+(H-8)+'" font-size="10" fill="#888">'+esc(xNote)+'</text>');
    p.push('</svg>');
    return p.join('');
  }

  function renderCharts(fg){
    var box=document.getElementById('homeCharts');
    if(box){
      if(!fg.length){
        box.innerHTML="<p class='sub'>No games in this date range.</p>";
      } else {
        var seq=fg.map(function(_,i){return String(i+1);});
        var tips=fg.map(function(g,i){
          return 'Game '+(i+1)+'  '+(g.d?g.d.slice(5):'?'); });
        function seriesFor(key){
          return META.phases.map(function(p,pi){
            return [META.labels[pi], META.colors[pi],
              fg.map(function(g){
                var a=g.p[p], nn=a[0];
                if(key==='apl')    return nn? (a[1]/nn) : null;
                if(key==='br_pts') return nn? (a[2]/nn*100) : null;
                if(key==='br_wr')  return nn? (a[3]/nn*100) : null;
                if(key==='blunders') return (a[4]||0);
                return null;
              })];
          });
        }
        var st=pooled(fg), ng=Math.max(1,fg.length);
        function ov(metric){
          return META.phases.map(function(p){
            var s=st[p], c=s.cnt;
            if(metric==='apl')    return c? (s.loss/c).toFixed(2) : '—';
            if(metric==='br_pts') return c? (s.nbp/c*100).toFixed(1)+'%' : '—';
            if(metric==='br_wr')  return c? (s.nbw/c*100).toFixed(1)+'%' : '—';
            if(metric==='blunders') return (s.nbe/ng).toFixed(1);
            return '';
          });
        }
        var charts=[
          trendChartSVG('Average points lost per move',
            seq, seriesFor('apl'), 'pts/move', tips, ov('apl')),
          trendChartSVG('Blunder rate \u2014 lost \u2265 6 pts',
            seq, seriesFor('br_pts'), 'share %', tips, ov('br_pts')),
          trendChartSVG('Blunder rate \u2014 win-rate drop \u2265 15%',
            seq, seriesFor('br_wr'), 'share %', tips, ov('br_wr')),
          trendChartSVG('Blunders per game (\u22656 pts or WR \u221215%)',
            seq, seriesFor('blunders'), 'count', tips, ov('blunders')),
        ];
        box.innerHTML=charts.map(function(c){
          return "<div class='chart'>"+c+"</div>"; }).join('');
      }
    }
    var emptyMsg="<p class='sub'>No games to summarise in this date range.</p>";
    // move-level distributions (points lost / winrate drop across every move)
    var plAll=[], wlAll=[];
    fg.forEach(function(g){ (g.pm||[]).forEach(function(m){
      plAll.push(m[0]); wlAll.push(m[1]); }); });
    var hboxA=document.getElementById('homeHistApl');
    if(hboxA) hboxA.innerHTML = distHistSVG(plAll,'Points lost per move (distribution)',0.5,
      'x-axis: points lost on a single move (0.5-pt bins, 15+ pooled); the red dashed line is the 6-pt blunder line',
      6,'blunder line 6 pts',15,false,'#4c6ef5') || emptyMsg;
    var hboxW=document.getElementById('homeHistWr');
    if(hboxW) hboxW.innerHTML = distHistSVG(wlAll,'Win-rate lost per move (distribution)',2.5,
      'x-axis: win-rate drop on a single move (2.5% bins, 50%+ pooled); the red dashed line is the 15% blunder line',
      15,'blunder line 15%',50,true,'#7048e8') || emptyMsg;
    var hbox=document.getElementById('homeHist');
    if(hbox){
      var hist=movesHistSVG(fg.map(function(g){return g.mv;}));
      hbox.innerHTML = hist || emptyMsg;
    }
  }

  // ---- improvement banner recompute (avg points lost per move, recent vs earlier) ----
  function windowApl(games){
    var loss=0, cnt=0;
    games.forEach(function(g){ var o=g.p.overall; cnt+=o[0]; loss+=o[1]; });
    return cnt ? (loss/cnt) : null;
  }
  function renderImprove(fg){
    var el=document.getElementById('homeImprove'); if(!el) return;
    var G=fg.length, m=null;
    if(G>=6){
      var n=Math.min(10, Math.floor(G/2));
      var recent=fg.slice(G-n), earlier=fg.slice(G-2*n, G-n);
      var r=windowApl(recent), e=windowApl(earlier);
      if(r!==null && e!==null && e!==0){
        var delta=r-e, pct=delta/e*100, verdict;
        if(pct<=-10) verdict='good'; else if(pct>=10) verdict='bad';
        else verdict='flat';
        m={n:n, recent:r, earlier:e, delta:delta, pct:pct, verdict:verdict};
      }
    }
    if(!m){
      el.className='improve imp-na';
      el.innerHTML="<div class='impl'>Improvement trend</div>"+
        "<div class='impv'>Too few games to judge yet</div>"+
        "<div class='impd'>Once you have 6 or more games, this compares the average "+
        "points lost per move in your recent games against the batch before them, "+
        "and calls it improving / flat / slipping.</div>";
      return;
    }
    var clsMap={good:'imp-good',bad:'imp-bad',flat:'imp-flat'};
    var titleMap={good:'Improving',bad:'Slipping',flat:'Roughly flat'};
    var arMap={good:'▼',bad:'▲',flat:'→'};
    var direction = m.delta<0 ? 'down' : (m.delta>0 ? 'up' : 'flat');
    var lessMore = m.delta<0 ? 'losing' : 'losing an extra';
    var pcttxt = Math.abs(m.pct).toFixed(0)+'%';
    var desc = 'Your last '+m.n+' games lose <b>'+m.recent.toFixed(2)+'</b> pts per move, '+
      direction+' '+pcttxt+' from <b>'+m.earlier.toFixed(2)+'</b> pts in the '+m.n+
      ' games before them ('+lessMore+' '+Math.abs(m.delta).toFixed(2)+
      ' pts/move). The lower the loss per move, the steadier your play.';
    el.className='improve '+clsMap[m.verdict];
    el.innerHTML="<div class='impl'>Improvement trend \u00B7 avg points lost per move</div>"+
      "<div class='impv'><span class='ar'>"+arMap[m.verdict]+"</span>"+
      titleMap[m.verdict]+"<span class='pct'>"+pcttxt+"</span></div>"+
      "<div class='impd'>"+desc+"</div>";
  }

  // Drop the "worst game" -- the one with the highest avg points lost per move --
  // so a single collapse does not drag the averages up.
  function gApl(g){ var o=g.p.overall; return o[0] ? (o[1]/o[0]) : 0; }
  function dropWorst(fg){
    if(fg.length<=1) return {list:fg, dropped:null};
    var wi=0, wv=-1;
    fg.forEach(function(g,i){ var a=gApl(g); if(a>wv){ wv=a; wi=i; } });
    var kept=fg.slice(0,wi).concat(fg.slice(wi+1));
    return {list:kept, dropped:fg[wi], apl:wv};
  }
  GR.renderHome = function(){
    var fg=GR.filtered();
    var ex=document.getElementById('exWorst');
    var note=document.getElementById('exWorstNote');
    if(ex && ex.checked){
      var d=dropWorst(fg); fg=d.list;
      if(note) note.textContent = d.dropped
        ? ('Worst game excluded: '+(d.dropped.d||'?')+' ('+d.apl.toFixed(2)+' pts lost per move)')
        : '(Too few games -- nothing excluded.)';
    } else if(note){ note.textContent=''; }
    renderCards(fg);
    renderCharts(fg);
  };
  document.addEventListener('grdate', GR.renderHome);
  (function attachEx(){
    var ex=document.getElementById('exWorst');
    if(ex){ ex.addEventListener('change', GR.renderHome); }
    else { document.addEventListener('DOMContentLoaded', attachEx); }
  })();
})();
</script>
"""
    return js.replace("__GAMES__", data).replace("__META__", meta)


def _traj_spark(w, won, width=200, height=54):
    """Small win-rate sparkline (user perspective, 0..1) with a 50% guide."""
    if not w:
        return ""
    pl, pr, pt, pb = 4, 4, 6, 6
    pw, ph = width - pl - pr, height - pt - pb
    n = len(w)
    col = "#2f855a" if won else "#c53030"

    def px(i):
        return pl + (i / (n - 1) * pw if n > 1 else pw / 2)

    def py(v):
        return pt + (1 - v) * ph
    pts = [(px(i), py(v)) for i, v in enumerate(w)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = (f"M {pts[0][0]:.1f},{pt+ph:.1f} "
            + " ".join(f"L {x:.1f},{y:.1f}" for x, y in pts)
            + f" L {pts[-1][0]:.1f},{pt+ph:.1f} Z")
    mid = py(0.5)
    p = [f'<svg viewBox="0 0 {width} {height}" width="100%" '
         f'preserveAspectRatio="none" style="display:block">']
    p.append(f'<rect x="0" y="{pt:.1f}" width="{width}" height="{ph/2:.1f}" '
             f'fill="#2f855a" fill-opacity="0.05"/>')
    p.append(f'<rect x="0" y="{mid:.1f}" width="{width}" height="{ph/2:.1f}" '
             f'fill="#c53030" fill-opacity="0.05"/>')
    p.append(f'<line x1="0" y1="{mid:.1f}" x2="{width}" y2="{mid:.1f}" '
             f'stroke="#b7a98f" stroke-width="1" stroke-dasharray="3 3"/>')
    p.append(f'<path d="{area}" fill="{col}" fill-opacity="0.10"/>')
    p.append(f'<polyline fill="none" stroke="{col}" stroke-width="1.8" '
             f'points="{line}"/>')
    p.append(f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="2.6" '
             f'fill="{col}"/>')
    p.append("</svg>")
    return "".join(p)
