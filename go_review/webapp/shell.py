"""The sidebar shell, dashboard and standalone Analyse/Import page."""

import json

from .listing import list_reports
from .assets import ANALYSIS_MODULE, PAGE_CSS, SHELL_CSS, SHELL_JS
from .config_jobs import _safe_cfg
from .htmlutil import _esc


def _target_options_html():
    reps = list_reports()
    try:
        default = str(_safe_cfg().get("default_import_target") or "")
    except Exception:
        default = ""
    have_default = any(r["rel"] == default for r in reps)
    opts = []
    for i, r in enumerate(reps):
        sel = " selected" if (r["rel"] == default if have_default else i == 0) else ""
        opts.append(f'<option value="{_esc(r["rel"])}"{sel}>'
                    f'{_esc(r["label"])}</option>')
    opts.append('<option value="__new__">+ New report...</option>')
    return "".join(opts)


def _analyze_target_options_html():
    """For tab 1: default "auto", then existing reports to append into."""
    opts = ['<option value="__auto__" selected>(Auto: create or reuse a report of the same name)'
            '</option>']
    for r in list_reports():
        opts.append(f'<option value="{_esc(r["rel"])}">'
                    f'Add to: {_esc(r["label"])}</option>')
    return "".join(opts)


def _analysis_module_html():
    """The reusable (1) download+analyse / (2) import module (markup + script).  Inline; no
    overlay.  Used by both the dashboard and the standalone /analyze page."""
    default_uid = default_subdir = ""
    try:
        cfg = _safe_cfg()
        default_uid = str(cfg.get("default_fox_uid") or "")
        default_subdir = str(cfg.get("default_games_subdir") or "")
    except Exception:
        pass
    return (ANALYSIS_MODULE
            .replace("__DEFAULT_UID__", _esc(default_uid))
            .replace("__DEFAULT_SUBDIR__", json.dumps(default_subdir))
            .replace("__TARGET_OPTIONS__", _target_options_html())
            .replace("__ANALYZE_TARGET_OPTIONS__",
                     _analyze_target_options_html()))


def _page(title, body, extra_css=""):
    return (f"<!doctype html><html lang=\"zh\"><head><meta charset=\"utf-8\">"
            f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{_esc(title)}</title><style>{PAGE_CSS}{extra_css}</style>"
            f"</head><body>{body}</body></html>")


def dashboard_page():
    body = (
        "<div class='app'>"
        "<aside class='side'>"
        "<div class='brand'><span>Mirror of Go &middot; KataGo Review</span>"
        "<button class='collapse' id='btn-collapse' title='Collapse the sidebar'>&laquo;</button></div>"
        "<button class='newbtn' id='btn-analyze'>+ Analyse / import games</button>"
        "<button class='newbtn2' id='btn-compare'>&#8646; Compare reports &middot; track progress</button>"
        "<button class='newbtn2' id='btn-summary'>&#128211; Review summary &middot; diagnostic profile</button>"
        "<button class='newbtn2' id='btn-tsumego'>&#129504; Skill Test &middot; 101weiqi diagnostics</button>"
        "<button class='newbtn2' id='btn-terms'>&#128214; Go terms &middot; Chinese to English</button>"
        "<div class='lh' id='lh'>Analysed reports</div>"
        "<div class='list' id='replist'></div>"
        "</aside>"
        "<button id='side-reopen' title='Expand the sidebar'>&raquo;</button>"
        "<div class='main'><iframe id='frame' src='about:blank'></iframe></div>"
        "</div>" + SHELL_JS)
    return _page("Mirror of Go &middot; KataGo Review", body, SHELL_CSS)


def analyze_page(embed=False):
    if embed:
        body = ("<main style='margin-top:14px'><section class='card'>"
                "<div class='card-h'><h2>Analyse / import games</h2></div>"
                f"{_analysis_module_html()}</section></main>")
    else:
        body = (
            "<div class='hero'><a class='back' href='/'>&larr; Back to dashboard</a>"
            "<h1>Analyse / import games</h1>"
            "<p class='sub'>Download and analyse your Fox games, or import an already-analysed SGF.</p></div>"
            f"<main><section class='card'>{_analysis_module_html()}</section></main>")
    return _page("Analyse / import &middot; Mirror of Go", body)
