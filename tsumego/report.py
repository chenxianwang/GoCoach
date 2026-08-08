"""Render the analysis as a single self-contained HTML dashboard.

Same house style as go_review: no dependencies, no build step, charts are
hand-written SVG, everything inlined so the file can be opened offline or
mailed to someone.
"""

import json
import html
import datetime

from .analyze import pass_probability

KIND_LABEL = {
    "trap": "Trap",
    "off_book": "Off-book",
    "depth": "Ran out of reading",
    "timeout": "Ran out of clock",
    "correct": "Solved",
}
KIND_COLOR = {
    "trap": "#e8590c",
    "off_book": "#c92a2a",
    "depth": "#1c7ed6",
    "timeout": "#7048e8",
    "correct": "#2f9e44",
}
KIND_BLURB = {
    "trap": ("You played a move the answer tree marks as losing -- and so do "
             "plenty of other players. A shared misconception: learn the shape "
             "once and every problem of that family stops costing you points."),
    "off_book": ("You played a move that is not in the answer tree at all, and "
                 "almost nobody else plays it. That is an idiosyncratic misread "
                 "or a guess -- usually a sign of moving before reading."),
    "depth": ("You started down the correct line and left it partway. The idea "
              "was right; the reading ran out. This is the one that responds "
              "directly to \"read to the end, including the opponent's best "
              "resistance, before you play\"."),
    "timeout": ("The clock expired before you played anything at all. Not a "
                "misread -- there is no move to diagnose. Look at where these "
                "sit in the run: time spent early is what leaves none here."),
}

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#f6f7f9;color:#1a202c;
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,"PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:32px 20px 72px}
h1{font-size:26px;margin:0 0 4px}
h2{font-size:19px;margin:38px 0 6px}
.sub{color:#667085;font-size:13.5px;margin:0 0 14px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:20px 0 4px}
.card{background:#fff;border:1px solid #e4e7ec;border-radius:10px;padding:14px 16px}
.card .v{font-size:25px;font-weight:650;letter-spacing:-.4px}
.card .l{color:#667085;font-size:12.5px;margin-top:2px}
.panel{background:#fff;border:1px solid #e4e7ec;border-radius:10px;padding:18px 20px;margin-top:12px}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid #eef0f3}
th{color:#667085;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.4px}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.tag{display:inline-block;padding:1px 8px;border-radius:99px;font-size:11.5px;font-weight:600;color:#fff}
.mv{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-weight:600}
.good{color:#2f9e44}.bad{color:#c92a2a}
.h2row{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin:38px 0 6px}
.h2row h2{margin:0}
.filt{display:inline-flex;background:#eef0f3;border-radius:8px;padding:3px;gap:2px}
.filt button{background:none;border:0;border-radius:6px;padding:4px 10px;font:inherit;
  font-size:12.5px;color:#475467;cursor:pointer;white-space:nowrap}
.filt button:hover{color:#1a202c}
.filt button.on{background:#fff;color:#1a202c;font-weight:600;box-shadow:0 1px 3px #0f172a1f}
.kindbox{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.kindbox .k{border:1px solid #e4e7ec;border-radius:10px;padding:14px 16px;background:#fff}
.kindbox .k .n{font-size:23px;font-weight:650}
.kindbox .k p{font-size:12.5px;color:#667085;margin:6px 0 0}
.note{background:#fffbea;border:1px solid #f5e6a8;border-radius:8px;padding:12px 14px;font-size:13.5px;margin-top:10px}
.kindbox .k.open{cursor:pointer;transition:border-color .12s,box-shadow .12s}
.kindbox .k.open:hover{border-color:#98a2b3;box-shadow:0 2px 10px #0f172a12}
.kindbox .k.on{border-color:#1a202c;box-shadow:0 0 0 1px #1a202c}
.kfoot{margin-top:10px;padding-top:9px;border-top:1px solid #eef0f3;
  font-size:12.5px;color:#475467;font-weight:600;display:flex;
  justify-content:space-between;align-items:center}
.chev{color:#98a2b3;font-size:17px;line-height:1}
.drill{margin-top:14px}
.drill .hd{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}
.drill .hd h3{margin:0;font-size:16px}
.drill .hd .cnt{color:#667085;font-size:13px}
.drill .x{margin-left:auto;background:none;border:1px solid #e4e7ec;border-radius:7px;
  padding:5px 11px;font:inherit;font-size:12.5px;color:#475467;cursor:pointer}
.drill .x:hover{background:#f2f4f7}
tr.done td{opacity:.45}
button.ok{background:#2f9e44;color:#fff;border:0;border-radius:7px;padding:5px 11px;
  font:inherit;font-size:12.5px;cursor:pointer;white-space:nowrap}
button.ok:hover{background:#37b24d}
button.undo{background:#fff;color:#475467;border:1px solid #d0d5dd;border-radius:7px;
  padding:5px 11px;font:inherit;font-size:12.5px;cursor:pointer;white-space:nowrap}
button.undo:hover{background:#f2f4f7}
button.ok[disabled],button.undo[disabled]{opacity:.5;cursor:default}
.foot{color:#98a2b3;font-size:12px;margin-top:40px;text-align:center}
svg{display:block;max-width:100%}
"""


def esc(x):
    return html.escape(str(x if x is not None else ""))


def pct(x, digits=0):
    return "--" if x is None else f"{x * 100:.{digits}f}%"


# -- chart primitives ----------------------------------------------------
def bar_chart(rows, width=680, row_h=30, label_w=150, fmt=pct, color="#1c7ed6",
              max_val=None, cap_w=None):
    """Horizontal bars: rows = [(label, value_0_to_1, right_caption)].

    `cap_w` reserves room for the right-hand caption; it defaults to whatever
    the longest caption actually needs, because a fixed width silently clips
    the longer ones ("46% (400 q, 40 runs)" is a lot wider than "46%").
    """
    rows = [r for r in rows if r[1] is not None]
    if not rows:
        return "<p class='sub'>Not enough data yet.</p>"
    top = max_val or max(r[1] for r in rows) or 1
    h = row_h * len(rows) + 8
    if cap_w is None:
        longest = max((len(str(r[2])) for r in rows), default=0)
        cap_w = max(60, int(longest * 6.6) + 14)   # ~6.6px per char at 12px
    bar_w = max(60, width - label_w - cap_w)
    out = [f"<svg viewBox='0 0 {width} {h}' width='{width}' height='{h}'>"]
    for i, (label, val, cap) in enumerate(rows):
        y = i * row_h + 4
        w = max(1, bar_w * (val / top)) if top else 1
        c = color(val) if callable(color) else color
        out.append(
            f"<text x='0' y='{y + 15}' font-size='12.5' fill='#344054'>{esc(label)}</text>"
            f"<rect x='{label_w}' y='{y + 4}' width='{bar_w}' height='16' rx='3' fill='#eef0f3'/>"
            f"<rect x='{label_w}' y='{y + 4}' width='{w:.1f}' height='16' rx='3' fill='{c}'/>"
            f"<text x='{label_w + bar_w + 8}' y='{y + 16}' font-size='12' "
            f"fill='#667085' font-variant-numeric='tabular-nums'>{esc(cap)}</text>")
    out.append("</svg>")
    return "".join(out)


def line_chart(points, width=680, height=190, color="#1c7ed6", ylabel=""):
    """points = [(x_label, y_0_to_1)] -- a simple accuracy-over-time line."""
    pts = [p for p in points if p[1] is not None]
    if len(pts) < 2:
        return "<p class='sub'>Not enough data yet for a trend.</p>"
    pad_l, pad_b, pad_t = 40, 26, 10
    w = width - pad_l - 12
    h = height - pad_b - pad_t
    lo, hi = 0.0, max(0.6, max(p[1] for p in pts) * 1.15)
    def X(i):
        return pad_l + w * i / max(1, len(pts) - 1)
    def Y(v):
        return pad_t + h * (1 - (v - lo) / (hi - lo))
    out = [f"<svg viewBox='0 0 {width} {height}' width='{width}' height='{height}'>"]
    for g in range(5):
        v = lo + (hi - lo) * g / 4
        y = Y(v)
        out.append(f"<line x1='{pad_l}' y1='{y:.1f}' x2='{width - 12}' y2='{y:.1f}' "
                   f"stroke='#eef0f3'/>"
                   f"<text x='0' y='{y + 4:.1f}' font-size='11' fill='#98a2b3'>{v * 100:.0f}%</text>")
    d = " ".join(("M" if i == 0 else "L") + f"{X(i):.1f},{Y(p[1]):.1f}"
                 for i, p in enumerate(pts))
    out.append(f"<path d='{d}' fill='none' stroke='{color}' stroke-width='2'/>")
    for lbl, i in ((pts[0][0], 0), (pts[-1][0], len(pts) - 1)):
        anchor = "start" if i == 0 else "end"
        out.append(f"<text x='{X(i):.1f}' y='{height - 6}' font-size='11' "
                   f"fill='#98a2b3' text-anchor='{anchor}'>{esc(lbl)}</text>")
    if ylabel:
        out.append(f"<text x='{pad_l}' y='{pad_t - 1}' font-size='11' fill='#98a2b3'>{esc(ylabel)}</text>")
    out.append("</svg>")
    return "".join(out)


def acc_color(v):
    if v is None:
        return "#98a2b3"
    return "#c92a2a" if v < 0.4 else ("#e8590c" if v < 0.6 else
                                      ("#f59f00" if v < 0.75 else "#2f9e44"))


# -- sections ------------------------------------------------------------
def _headline(agg):
    k = agg["kinds"]
    total_fail = sum(k.values()) or 1
    cards = [
        (f"{agg['n']:,}", "Questions attempted"),
        (pct(agg["accuracy"], 1), "Overall accuracy"),
        (f"{agg['n_runs']:,}", "Test runs"),
        (f"{agg['median_time'] or 0:.0f}s", "Median time / question"),
    ]
    out = ["<div class='cards'>"]
    for v, l in cards:
        out.append(f"<div class='card'><div class='v'>{esc(v)}</div>"
                   f"<div class='l'>{esc(l)}</div></div>")
    out.append("</div>")

    # The filter lives next to the heading rather than inside each list: it is a
    # property of how you are working right now ("show me what is left" vs "let
    # me revisit what I ticked off"), not of any one category, and keeping it in
    # one place means it does not reset every time you open a different card.
    out.append("<div class='h2row'><h2>How you get them wrong</h2>"
               "<div class='filt' title='Applies to every category list below'>"
               "<button id='f-todo' class='on' onclick=\"setDrillFilter('todo')\">"
               "To work through</button>"
               "<button id='f-done' onclick=\"setDrillFilter('done')\">"
               "Understood</button>"
               "<button id='f-all' onclick=\"setDrillFilter('all')\">All</button>"
               "</div></div>")
    out.append("<p class='sub'>Every wrong answer, matched against the crowd move "
               "tree. These three want different training, which is the whole "
               "point of separating them.</p>")
    pending = k.get("unclassified", 0)
    known = max(1, total_fail - pending)
    by_kind = agg.get("by_kind") or {}
    out.append("<div class='kindbox'>")
    shown = ["trap", "depth", "off_book"]
    if k.get("timeout"):
        shown.append("timeout")
    for kind in shown:
        n = k.get(kind, 0)
        rows = by_kind.get(kind) or []
        left = sum(1 for r in rows if not r["hidden"])
        done = len(rows) - left
        done_note = (f" &middot; {done} understood" if done else "")
        out.append(
            f"<div class='k open' id='kind-{kind}' onclick=\"showKind('{kind}')\" "
            f"title='Click to list these problems'>"
            f"<span class='tag' style='background:{KIND_COLOR[kind]}'>"
            f"{esc(KIND_LABEL[kind])}</span>"
            f"<div class='n'>{n:,} <span style='font-size:14px;color:#667085'>"
            f"({n / known * 100:.0f}% of classified misses)</span></div>"
            f"<p>{esc(KIND_BLURB[kind])}</p>"
            f"<div class='kfoot'>{left} problem{'' if left == 1 else 's'} to "
            f"work through{done_note} <span class='chev'>&rsaquo;</span></div>"
            f"</div>")
    out.append("</div>")
    out.append("<div class='drill' id='drill'></div>")
    if pending:
        out.append(
            f"<div class='note'><b>{pending:,} of your {total_fail:,} misses are "
            f"not classified yet.</b> The crowd move tree for those questions "
            f"has not been fetched — the site throttles that endpoint much "
            f"harder than the rest, so it lands last. They are excluded from "
            f"the three counts above rather than guessed at; run the fetch "
            f"again to fill them in.</div>")
    return "".join(out)


def _timing(agg):
    rows = [(t["label"], t["accuracy"], f"{t['accuracy'] * 100:.0f}%  (n={t['count']})")
            for t in agg["times"] if t["count"] >= 5 and t["accuracy"] is not None]
    mc, mw = agg["median_time_correct"], agg["median_time_wrong"]
    note = ""
    if mc and mw:
        # Compare before rounding, and treat a small gap as "no difference" --
        # otherwise two medians that both print as "28s" get a confident story
        # attached to a fraction of a second.
        gap = mw - mc
        if abs(gap) < max(2.0, 0.1 * mc):
            verdict = ("You spend about the same time either way, so the clock "
                       "is not what separates your hits from your misses -- "
                       "look at the failure split above instead.")
        elif gap < 0:
            verdict = ("Your misses are the <i>fast</i> ones -- you are "
                       "answering before the reading is finished, which is the "
                       "cheapest thing on this page to fix.")
        else:
            verdict = ("Your misses are the slow ones, so these are genuine "
                       "reading-depth problems rather than rushing.")
        note = (f"<div class='note'><b>Median time on ones you solved: {mc:.0f}s. "
                f"On ones you missed: {mw:.0f}s.</b> {verdict}</div>")
    return ("<h2>Time spent vs. accuracy</h2>"
            "<p class='sub'>Seconds on the clock for that question, against how "
            "often you got it right.</p>"
            f"<div class='panel'>{bar_chart(rows, color=acc_color, max_val=1.0)}</div>"
            + note)


def _levels(agg):
    rows = [(l["label"], l["accuracy"],
             f"{l['accuracy'] * 100:.0f}%  ({l['n']} q, {l['runs']} runs)")
            for l in agg["levels"] if l["n"] >= 3]
    return ("<h2>Accuracy by test level</h2>"
            "<p class='sub'>Per-question accuracy, not pass rate -- this is the "
            "number that actually moves your pass rate.</p>"
            f"<div class='panel'>{bar_chart(rows, color=acc_color, max_val=1.0)}</div>")


def _types(agg):
    rows = [(t["name"], t["accuracy"], f"{t['accuracy'] * 100:.0f}%  (n={t['n']})")
            for t in agg["types"] if t["n"] >= 5]
    return ("<h2>Accuracy by problem type</h2>"
            "<p class='sub'>Where the points actually leak.</p>"
            f"<div class='panel'>{bar_chart(rows, color=acc_color, max_val=1.0)}</div>")


def _position(agg):
    rows = [(f"Question {p['n']}", p["accuracy"],
             f"{p['accuracy'] * 100:.0f}%  ({p['median_time'] or 0:.0f}s, n={p['count']})")
            for p in agg["positions"] if p["count"] >= 5]
    return ("<h2>Accuracy through a run</h2>"
            "<p class='sub'>If this slopes down, the problem is stamina or the "
            "clock rather than strength.</p>"
            f"<div class='panel'>{bar_chart(rows, color=acc_color, max_val=1.0)}</div>")


def _difficulty(agg):
    rows = [(f"{d['label']} of players solve it", d["accuracy"],
             f"{d['accuracy'] * 100:.0f}%  (n={d['count']})")
            for d in agg["difficulty"] if d["count"] >= 5]
    return ("<h2>Are you missing the easy ones?</h2>"
            "<p class='sub'>Grouped by how often <i>everyone else</i> solves the "
            "problem. Misses in the right-hand rows are the expensive ones.</p>"
            f"<div class='panel'>{bar_chart(rows, color=acc_color, max_val=1.0, label_w=215)}</div>")


def _traps(agg, limit=15):
    traps = agg["traps"][:limit]
    if not traps:
        return ""
    rows = ["<h2>Traps worth studying first</h2>",
            "<p class='sub'>Losing moves you played that a large share of other "
            "players also pick. Highest leverage on this page: one shape learned "
            "kills a whole family of mistakes.</p>",
            "<div class='panel'><table><tr><th>Problem</th><th>Type</th>"
            "<th class='num'>Fell for it</th>"
            "<th>You played</th><th>Correct</th>"
            "<th class='num'>Others playing yours</th>"
            "<th class='num'>Solve rate</th></tr>"]
    for a in traps:
        times = a["times"]
        rows.append(
            f"<tr><td><a href='https://www.101weiqi.com/q/{esc(a['publicid'])}/' "
            f"target='_blank' rel='noopener'>Q-{esc(a['publicid'])}</a></td>"
            f"<td>{esc(a['qtypename'])}</td>"
            f"<td class='num'>{times}&times;</td>"
            f"<td class='mv bad'>{esc(a['my_first'])}</td>"
            f"<td class='mv good'>{esc(a['best_move'])}</td>"
            f"<td class='num'>{pct(a['my_first_share'])}</td>"
            f"<td class='num'>{pct(a['crowd_rate'])}</td></tr>")
    rows.append("</table></div>")
    return "".join(rows)


def _repeats(agg, limit=15):
    reps = [r for r in agg["repeats"] if r["failed"] >= 2][:limit]
    if not reps:
        return ""
    rows = ["<h2>Problems that keep beating you</h2>",
            "<p class='sub'>Seen more than once and missed at least twice. These "
            "belong in the error book until they are automatic.</p>",
            "<div class='panel'><table><tr><th>Problem</th><th>Type</th>"
            "<th class='num'>Seen</th><th class='num'>Missed</th>"
            "<th>Last try</th><th>Correct</th><th>Failure</th></tr>"]
    for r in reps:
        rows.append(
            f"<tr><td><a href='https://www.101weiqi.com/q/{esc(r['publicid'])}/' "
            f"target='_blank' rel='noopener'>Q-{esc(r['publicid'])}</a></td>"
            f"<td>{esc(r['type'])}</td>"
            f"<td class='num'>{r['seen']}</td><td class='num'>{r['failed']}</td>"
            f"<td class='mv bad'>{esc(r['my_first'])}</td>"
            f"<td class='mv good'>{esc(r['best_move'])}</td>"
            f"<td><span class='tag' style='background:{KIND_COLOR.get(r['kind'], '#98a2b3')}'>"
            f"{esc(KIND_LABEL.get(r['kind'], r['kind']))}</span></td></tr>")
    rows.append("</table></div>")
    return "".join(rows)


def _projection(agg, need=8, total=10):
    """What per-question accuracy would actually mean for your pass rate."""
    cur = agg["accuracy"]
    rows = []
    for p in (0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90):
        prob = pass_probability(p, need, total)
        rows.append((f"{p * 100:.0f}% accuracy", min(1.0, prob),
                     f"{prob * 100:.1f}% of runs"))
    here = ""
    if cur is not None:
        pr = pass_probability(cur, need, total)
        here = (f"<div class='note'>At your current <b>{cur * 100:.0f}%</b> "
                f"per-question accuracy you would clear roughly "
                f"<b>{pr * 100:.1f}%</b> of runs needing {need}/{total}. "
                f"The curve is steep on purpose -- this is why grinding retries "
                f"does nothing and raising accuracy does everything.</div>")
    return ("<h2>What accuracy buys you</h2>"
            f"<p class='sub'>Chance of clearing a run that needs {need} of "
            f"{total} correct, at a given per-question accuracy.</p>"
            f"<div class='panel'>{bar_chart(rows, color='#7048e8', max_val=1.0)}</div>"
            + here)


def _trend(agg):
    pts = [(datetime.datetime.fromtimestamp(p["t"]).strftime("%Y-%m-%d")
            if p["t"] else "", p["accuracy"]) for p in agg["trend"]]
    return ("<h2>Rolling accuracy</h2>"
            "<p class='sub'>40-question rolling average, oldest to newest.</p>"
            f"<div class='panel'>{line_chart(pts, ylabel='accuracy')}</div>")


DRILL_JS = r"""
<script>
var KINDS = __KINDS__;
var INTERACTIVE = __INTERACTIVE__;
var openKind = null;
var drillFilter = 'todo';

function esc(s){ return String(s==null?'':s)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function detail(r){
  if(r.kind==='trap')
    return 'you played <b class="mv bad">'+esc(r.my_first)+'</b>, correct is '
      + '<b class="mv good">'+esc(r.best_move)+'</b> · '
      + Math.round(r.my_first_share*100)+'% of players pick yours';
  if(r.kind==='depth')
    return 'right idea, left the correct line at your move '
      + ((r.diverge_at==null?0:r.diverge_at)+1)
      + ' · correct start <b class="mv good">'+esc(r.best_move)+'</b>';
  if(r.kind==='off_book')
    return 'you played <b class="mv bad">'+esc(r.my_first)+'</b>, which is not in '
      + 'the answer tree · correct is <b class="mv good">'+esc(r.best_move)+'</b>';
  if(r.kind==='timeout')
    return 'clock expired after '+(r.costtime||0)+'s, no move played · '
      + 'correct is <b class="mv good">'+esc(r.best_move)+'</b>';
  return '';
}

// Which rows the open list shows. The category counts are deliberately NOT
// filtered -- 158 traps happened whether or not you have understood them since,
// so the card and the header keep reporting what the history says.
function filterRows(rows){
  if(drillFilter==='done') return rows.filter(function(r){ return r.hidden; });
  if(drillFilter==='all')  return rows.slice();
  return rows.filter(function(r){ return !r.hidden; });
}

function setDrillFilter(f){
  drillFilter=f;
  ['todo','done','all'].forEach(function(x){
    var b=document.getElementById('f-'+x);
    if(b) b.classList.toggle('on', x===f); });
  if(openKind){ var k=openKind; openKind=null; showKind(k); }   // re-render, stay open
}

function showKind(kind){
  var box=document.getElementById('drill');
  document.querySelectorAll('.kindbox .k').forEach(function(el){
    el.classList.toggle('on', el.id==='kind-'+kind && openKind!==kind); });
  if(openKind===kind){ openKind=null; box.innerHTML=''; return; }
  openKind=kind;
  var rows=(KINDS[kind]||[]);
  var left=rows.filter(function(r){return !r.hidden;});
  var done=rows.length-left.length;
  var h='<div class="hd"><h3>'+esc(kind==='trap'?'Traps':
        kind==='depth'?'Ran out of reading':
        kind==='off_book'?'Off-book':'Ran out of clock')+'</h3>'
      +'<span class="cnt">'+left.length+' to work through'
      +(done? ' · '+done+' understood':'')+'</span>'
      +'<button class="x" onclick="showKind(\''+kind+'\')">close</button></div>';
  var view=filterRows(rows);
  if(!view.length){
    var msg = !rows.length ? 'Nothing here — nice.'
            : drillFilter==='done'
              ? 'Nothing in this category is marked understood yet.'
              : 'Everything in this category is marked understood.';
    box.innerHTML=h+'<div class="panel"><p class="sub" style="margin:0">'+msg+'</p></div>';
    return;
  }
  h+='<div class="panel"><table><tr><th>Problem</th><th>Type</th>'
    +'<th class="num">Met</th><th>What happened</th><th class="num">Solve rate</th>'
    +(INTERACTIVE?'<th></th>':'')+'</tr>';
  view.forEach(function(r){
    h+='<tr id="row-'+r.qid+'" class="'+(r.hidden?'done':'')+'">'
      +'<td><a href="https://www.101weiqi.com/q/'+r.publicid+'/" target="_blank" '
      +'rel="noopener">Q-'+r.publicid+'</a></td>'
      +'<td>'+esc(r.qtypename)+'</td>'
      +'<td class="num">'+r.times+'×</td>'
      +'<td>'+detail(r)+'</td>'
      +'<td class="num">'+(r.crowd_rate==null?'--':Math.round(r.crowd_rate*100)+'%')+'</td>'
      +(INTERACTIVE?'<td class="num"><button class="'+(r.hidden?'undo':'ok')+'" '
        +'id="btn-'+r.qid+'" onclick="mark('+r.qid+','+(r.hidden?'false':'true')+')">'
        +(r.hidden?'Bring back':'Understood')+'</button></td>':'')
      +'</tr>';
  });
  box.innerHTML=h+'</table></div>';
  box.scrollIntoView({behavior:'smooth', block:'nearest'});
}

function refreshFoot(k){
  var card=document.getElementById('kind-'+k);
  if(!card) return;
  var f=card.querySelector('.kfoot');
  if(!f) return;
  var rows=KINDS[k]||[], left=rows.filter(function(r){return !r.hidden;}).length;
  var done=rows.length-left;
  f.innerHTML=left+' problem'+(left===1?'':'s')+' to work through'
    +(done?' &middot; '+done+' understood':'')+' <span class="chev">&rsaquo;</span>';
}

function mark(qid, hide){
  var btn=document.getElementById('btn-'+qid);
  if(btn){ btn.disabled=true; btn.textContent='Saving…'; }
  fetch('/api/tsumego_hide',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({qid:qid, hidden:hide})})
    .then(function(r){ return r.json(); })
    .then(function(d){
      if(!d.ok) throw new Error(d.message||'failed');
      // hidden.json is keyed by qid, and one problem can be filed under two
      // categories (failed as a trap once, as a misread another time), so the
      // mark has to land on every copy -- otherwise one card silently disagrees
      // with the server until the next reload.
      Object.keys(KINDS).forEach(function(k){
        (KINDS[k]||[]).forEach(function(r){ if(r.qid===qid) r.hidden=hide; });
        refreshFoot(k);
      });
      var k=openKind; openKind=null; showKind(k);   // re-render, stay open
    })
    .catch(function(e){
      if(btn){ btn.disabled=false; btn.textContent='Could not save'; }
    });
}
</script>
"""


def _drill_js(agg, interactive):
    """The per-category lists, embedded as data so the page stays one file."""
    payload = {k: v for k, v in (agg.get("by_kind") or {}).items()
               if k != "unclassified"}
    return (DRILL_JS
            .replace("__KINDS__", json.dumps(payload, ensure_ascii=False))
            .replace("__INTERACTIVE__", "true" if interactive else "false"))

def build_html(agg, need=8, total=10, interactive=False):
    body = [
        "<div class='wrap'>",
        "<h1>Skill Test diagnostics</h1>",
        f"<p class='sub'>{agg['n']:,} questions across {agg['n_runs']:,} runs "
        f"&middot; generated {datetime.date.today().isoformat()}</p>",
        _headline(agg),
        _projection(agg, need, total),
        _timing(agg),
        _levels(agg),
        _types(agg),
        _position(agg),
        _difficulty(agg),
        _traps(agg),
        _repeats(agg),
        _trend(agg),
        "<p class='foot'>Built from your own 101weiqi Skill Test records.</p>",
        "</div>",
        _drill_js(agg, interactive),
    ]
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Skill Test diagnostics</title>"
            f"<style>{CSS}</style></head><body>{''.join(body)}</body></html>")
