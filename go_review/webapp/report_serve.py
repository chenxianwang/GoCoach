"""Serving one report's review_report.html with the shared nav bar."""

import os

from .listing import list_reports, report_dir_from_rel
from .htmlutil import _esc


def _report_nav_html(current_rel):
    reports = list_reports()
    opts = []
    for r in reports:
        sel = " selected" if r["rel"] == current_rel else ""
        opts.append(f'<option value="{_esc(r["rel"])}"{sel}>'
                    f'{_esc(r["label"])}</option>')
    options = "".join(opts) or '<option value="">(No reports yet)</option>'
    return ("<style>body{padding-top:48px!important}"
            "#ymnav{position:fixed;top:0;left:0;right:0;height:48px;z-index:99999;"
            "background:var(--espresso,#2a241f);color:#fff;display:flex;"
            "align-items:center;gap:14px;"
            "padding:0 16px;font-family:-apple-system,'PingFang SC',sans-serif;"
            "box-shadow:0 1px 6px rgba(42,36,31,.3)}"
            "#ymnav a{color:#fff;text-decoration:none;font-weight:600;font-size:14px}"
            "#ymnav a:hover{opacity:.8}#ymnav .sep{opacity:.35}"
            "#ymnav select{margin-left:auto;padding:6px 8px;border-radius:7px;"
            "border:none;font-size:13px;max-width:52vw}</style>"
            "<div id='ymnav'><a href='/'>&larr; Dashboard</a><span class='sep'>|</span>"
            "<a href='/analyze'>+ Analyse / import</a>"
            f"<select id='ymnav-rep' title='Switch report'>{options}</select></div>"
            "<script>document.getElementById('ymnav-rep').onchange=function(){"
            "if(this.value) location.href='/r/'+encodeURIComponent(this.value);};"
            "</script>")


def render_report(rel, embed=False):
    """Read a report's HTML; inject the slim top nav bar unless embedded in the
    dashboard shell (the sidebar already provides navigation)."""
    rdir = report_dir_from_rel(rel)
    if not rdir:
        return None
    html_path = os.path.join(rdir, "review_report.html")
    if not os.path.exists(html_path):
        return None
    with open(html_path, encoding="utf-8") as f:
        doc = f.read()
    if embed:
        return doc
    nav = _report_nav_html(rel)
    lower = doc.lower()
    idx = lower.find("<body")
    if idx != -1:
        end = doc.find(">", idx)
        if end != -1:
            return doc[:end + 1] + nav + doc[end + 1:]
    if "</head>" in doc:
        return doc.replace("</head>", "</head>" + nav, 1)
    return nav + doc
