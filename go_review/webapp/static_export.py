"""Building the offline index.html viewer."""

import os
import datetime
from urllib.parse import quote

from .paths import HERE
from .listing import list_reports
from .assets import STATIC_CSS
from .htmlutil import _esc


def _static_card_html(r):
    s = r["summary"]
    rec = f"{s['wins']}W &middot; {s['losses']}L" if (s["wins"] or s["losses"]) else ""
    date = f"latest {s['last_date']}" if s["last_date"] else ""
    tag = f"<div class='tag'>{_esc(s['source'])}</div>" if s["source"] else ""
    href = quote(r["rel"]) + "/review_report.html"
    return (f"<a class='rep' href='{href}'>"
            f"<div class='nm'>{_esc(r['label'])}</div>{tag}"
            f"<div class='meta'><span><span class='big'>{s['games']}</span> games</span>"
            f"<span>{_esc(date)}</span></div>"
            f"<div class='rec'>{_esc(rec)}</div></a>")


def build_static_index():
    """A standalone dashboard that opens via file:// (no server).  Report cards
    link directly to each folder's review_report.html.  Analysis/import is not
    available here — it needs the local program running."""
    reps = [r for r in list_reports() if r["has_html"]]
    cards = "".join(_static_card_html(r) for r in reps) or \
        "<div class='empty'>No reports yet. Start the app and run an analysis.</div>"
    today = datetime.date.today().isoformat()
    body = (
        "<div class='hero'><h1>Mirror of Go &middot; KataGo Review</h1>"
        f"<p class='sub'>Offline viewer &middot; {len(reps)} reports &middot; {today}</p></div>"
        "<main>"
        "<div class='note'>This is the <b>offline viewer</b> -- it opens even after "
        "you close the terminal. To <b>download, analyse or import new games</b>, "
        "double-click <code>Mirror of Go.command</code> to start the app (which opens "
        "the full interface).</div>"
        f"<div class='sec'>Analysed reports ({len(reps)})</div>"
        f"<div class='grid'>{cards}</div>"
        "</main>")
    return ("<!doctype html><html lang=\"zh\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>Mirror of Go &middot; KataGo Review</title>"
            f"<style>{STATIC_CSS}</style></head><body>{body}</body></html>")


def write_static_index():
    """Write/refresh index.html next to the report folders.  Best-effort."""
    try:
        path = os.path.join(HERE, "index.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(build_static_index())
        return path
    except Exception:
        return None
