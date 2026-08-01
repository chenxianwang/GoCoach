"""Top-level report assembly (build_html) and the CLI entry point (main)."""

import os
import datetime

from .assets import CSS, NAV_JS, TOOLTIP_JS
from .data import aggregate, date_key, esc, load_config, load_games, load_hidden, practice_cleared, recommendations, source_label_from_path
from .charts import _date_filter_bar, _date_filter_js
from .trends import trends_section
from .trajectory import trajectory_section
from .practice import practice_section
from .summary import summary_section
from .pages import _games_page, _home_page, _moves_hist_section


def build_html(games, agg, recs, report_dir=None):
    chron = sorted(games, key=date_key)  # oldest -> newest for trends
    hidden = load_hidden(report_dir)

    # The project (report folder) name is the report's identity — show it as the
    # player/source label on the overview.
    if report_dir:
        agg["source_label"] = os.path.basename(str(report_dir).rstrip("/\\"))

    # Each module is one page. (id, sidebar label, html). Empty modules are
    # dropped so their nav entry doesn't appear.
    candidates = [
        ("home", "Overview",
         _home_page(agg, chron) + trends_section(chron)
         + _moves_hist_section(agg, games)),
        ("trajectory", "Trajectory", trajectory_section(games)),
        ("practice", "Blunders",
         practice_section(games, hidden, practice_cleared(report_dir))),
        ("summary", "Review summary", summary_section()),
        ("games", "Game by game", _games_page(games)),
    ]
    pages = [(pid, label, h) for pid, label, h in candidates if h]

    nav = ["<aside class='sidebar'>",
           "<div class='brand'>Mirror of Go<span>KATAGO REVIEW</span></div>",
           "<nav>"]
    sections = []
    for i, (pid, label, h) in enumerate(pages):
        active = " active" if i == 0 else ""
        nav.append(f"<button class='navlink{active}' data-page='{pid}'>"
                   f"<span class='dot'></span>{esc(label)}</button>")
        sections.append(f"<section class='page{active}' id='page-{pid}'>"
                        f"{_date_filter_bar()}{h}</section>")
    nav.append("</nav>")
    nav.append(f"<div class='meta'>Generated "
               f"{esc(datetime.date.today().isoformat())}<br>"
               f"{agg['n']} games &middot; {agg['n_user_moves']} moves analysed</div>")
    nav.append("</aside>")

    p = [f"<!doctype html><html lang='zh'><head><meta charset='utf-8'>"
         f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>Mirror of Go &middot; KataGo Review</title>"
         f"<style>{CSS}</style></head><body>",
         "<div class='layout'>",
         "".join(nav),
         "<main class='content'>",
         "".join(sections),
         "</main></div>",
         TOOLTIP_JS,
         NAV_JS,
         _date_filter_js(chron),
         "</body></html>"]
    return "".join(p)


def main(argv):
    cfg = load_config()
    out_dir = os.path.expanduser(cfg["output_dir"])
    games = load_games(out_dir, cfg.get("games_dirs", []))
    if not games:
        print(f"No analysed games found in {out_dir}; run analyze.py first.")
        return 1
    agg = aggregate(games)
    agg["source_label"] = source_label_from_path(out_dir)
    recs = recommendations(agg)
    report_path = os.path.join(out_dir, "review_report.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(build_html(games, agg, recs, report_dir=out_dir))
    print(f"Review report written: {report_path}")
    return 0
