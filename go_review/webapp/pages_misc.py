"""The Review-summary and Go-terms pages."""

import re
from urllib.parse import quote

import go_terms        # noqa: E402

from .listing import list_reports
from .assets import SUMMARY_CSS, SUMMARY_JS, TERMS_CSS, TERMS_JS
from .shell import _page
from .htmlutil import _esc
from .summary_engine import _md_to_html, load_summary, summary_history_html


def summary_page(rel=None, embed=False):
    reps = list_reports()
    if not rel and reps:
        rel = reps[0]["rel"]
    opts = "".join(
        f"<option value='{_esc(r['rel'])}'{' selected' if r['rel']==rel else ''}>"
        f"{_esc(r['label'])}</option>" for r in reps)
    cached = load_summary(rel) if rel else ""
    inner = (_md_to_html(cached) if cached else
             "<p class='empty'>Nothing generated yet. Press <b>Generate / refresh</b> "
             "above to send this report's review notes (including the voice "
             "transcript) to DeepSeek, which derives your own weakness categories "
             "and training priorities.</p>")
    head = ("" if embed else
            "<div class='hero'><a class='back' href='/'>&larr; Back to dashboard</a>"
            "<h1>Review summary &middot; diagnostic profile</h1>"
            "<p class='sub'>Collapses scattered mistakes into root-cause categories and training priorities.</p></div>")
    body = (
        head + "<main>"
        "<section class='card'><div class='card-h'><h2>Diagnostic profile</h2></div>"
        f"<div class='cmpbar'>Report <select id='sumRep' class='cmpsel'>{opts}</select>"
        "<button class='sumgen' id='sumGen'>&#10227; Generate / refresh summary</button>"
        f"<a class='sumexp' id='sumExp' download "
        f"href='/api/summary_export?report={quote(rel or '')}'>&#8681; Export all "
        f"versions</a>"
        "<span id='sumStat' class='nstat'></span></div>"
        "<p class='hint'>Built from the reviews you spoke into the recorder in the "
        "blunder set, plus this report's lead conversion and comeback rate. DeepSeek "
        "derives your own weakness categories straight from your notes and diagnoses "
        "them. The result is saved into that report folder, so next time it loads "
        "instantly without recomputing.</p></section>"
        f"<section class='card'><div id='sumBody' class='smdbox'>{inner}</div>"
        f"<div id='sumHist'>{summary_history_html(rel) if rel else ''}</div>"
        "</section>"
        "</main>" + SUMMARY_JS)
    return _page("Review summary &middot; Mirror of Go", body, SUMMARY_CSS)


# ---------------------------------------------------------------------------
# Go terminology dictionary (/terms) — English names for the Chinese terms
# ---------------------------------------------------------------------------

def terms_page(embed=False):
    """Searchable English/Chinese Go glossary.  Data lives in go_terms.py; the
    filtering is pure client-side JS so the page also works from a saved copy."""
    groups = go_terms.by_category()
    total = sum(len(rows) for _, _, rows in groups)

    chips = ["<button class='navbtn on' data-fc='all'>All "
             f"<i>{total}</i></button>"]
    for cid, label, rows in groups:
        chips.append(f"<button class='navbtn' data-fc='{cid}'>{label} "
                     f"<i>{len(rows)}</i></button>")

    secs = []
    for cid, label, rows in groups:
        trs = []
        for _c, en, zh, py, say, meaning in rows:
            # Everything searchable goes into one lowercase haystack: the English
            # term, the Chinese, its pinyin, and the definition text.  Markup is
            # stripped first, or a search for "b" would hit every <b> tag.
            plain = re.sub(r"<[^>]+>", "", meaning)
            hay = _esc(" ".join((en, zh, py, plain)).lower())
            say_html = (f"<span class='tsay'>{_esc(say)}</span>" if say else "")
            trs.append(
                f"<tr class='trow' data-c='{cid}' data-s=\"{hay}\">"
                f"<td class='ten'><b>{_esc(en)}</b>{say_html}</td>"
                f"<td class='tzh'>{_esc(zh)}<span class='tpy'>{_esc(py)}</span></td>"
                f"<td class='tdef'>{meaning}</td></tr>")
        secs.append(
            f"<section class='card tsec' data-c='{cid}'>"
            f"<div class='card-h'><h2>{label}</h2>"
            f"<span class='nstat'>{len(rows)} terms</span></div>"
            "<table class='tterm'><thead><tr>"
            "<th>English</th><th>Chinese</th><th>What it means</th>"
            "</tr></thead><tbody>"
            + "".join(trs) + "</tbody></table></section>")

    head = ("" if embed else
            "<div class='hero'><a class='back' href='/'>&larr; Back to dashboard</a>"
            "<h1>Go terms &middot; Chinese to English</h1>"
            "<p class='sub'>The English name for every move, shape and idea you "
            "already know in Chinese.</p></div>")
    body = (
        head + "<main>"
        "<section class='card'>"
        "<div class='card-h'><h2>Terminology dictionary</h2>"
        f"<span class='nstat'>{total} terms</span></div>"
        "<p class='hint' style='margin:0 0 10px'>Most English Go vocabulary is "
        "borrowed from Japanese, which is why the spelling rarely matches the "
        "sound &mdash; so each term shows how to say it. Search in "
        "<b>English</b>, <b>Chinese</b> or <b>pinyin</b> (no IME needed: type "
        "<code>shoujin</code> to find 手筋).</p>"
        "<input type='text' id='tq' class='tsearch' autocomplete='off' "
        "placeholder='Search terms, e.g. tesuji / 手筋 / shoujin / liberty'>"
        "<div class='navbar' style='margin-top:10px'>"
        "<div class='navrow'><span class='navlbl'>Category</span>"
        + "".join(chips) + "</div></div>"
        "<div class='flcount' id='tcount' style='margin:10px 0 0'></div>"
        "</section>"
        + "".join(secs) +
        "<section class='card' id='tnone' style='display:none'>"
        "<p class='empty'>Nothing matches that search.</p></section>"
        "</main>" + TERMS_JS)
    return _page("Go terms &middot; Mirror of Go", body, TERMS_CSS)
