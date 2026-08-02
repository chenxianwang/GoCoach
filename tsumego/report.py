"""Render the analysis as a single self-contained HTML dashboard.

Same house style as go_review: no dependencies, no build step, charts are
hand-written SVG, everything inlined so the file can be opened offline or
mailed to someone.
"""

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
.kindbox{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.kindbox .k{border:1px solid #e4e7ec;border-radius:10px;padding:14px 16px;background:#fff}
.kindbox .k .n{font-size:23px;font-weight:650}
.kindbox .k p{font-size:12.5px;color:#667085;margin:6px 0 0}
.note{background:#fffbea;border:1px solid #f5e6a8;border-radius:8px;padding:12px 14px;font-size:13.5px;margin-top:10px}
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

    out.append("<h2>How you get them wrong</h2>")
    out.append("<p class='sub'>Every wrong answer, matched against the crowd move "
               "tree. These three want different training, which is the whole "
               "point of separating them.</p>")
    pending = k.get("unclassified", 0)
    known = max(1, total_fail - pending)
    out.append("<div class='kindbox'>")
    shown = ["trap", "depth", "off_book"]
    if k.get("timeout"):
        shown.append("timeout")
    for kind in shown:
        n = k.get(kind, 0)
        out.append(
            f"<div class='k'><span class='tag' style='background:{KIND_COLOR[kind]}'>"
            f"{esc(KIND_LABEL[kind])}</span>"
            f"<div class='n'>{n:,} <span style='font-size:14px;color:#667085'>"
            f"({n / known * 100:.0f}% of classified misses)</span></div>"
            f"<p>{esc(KIND_BLURB[kind])}</p></div>")
    out.append("</div>")
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


def build_html(agg, need=8, total=10):
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
    ]
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Skill Test diagnostics</title>"
            f"<style>{CSS}</style></head><body>{''.join(body)}</body></html>")
