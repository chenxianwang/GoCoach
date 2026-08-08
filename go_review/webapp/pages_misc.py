"""The Review-summary and Go-terms pages."""

import re
from urllib.parse import quote

import go_terms        # noqa: E402

from .listing import list_reports
from .assets import (PROMPT_CSS, PROMPT_JS, SUMMARY_CSS, SUMMARY_JS,
                     TERMS_CSS, TERMS_JS)
from .shell import _page
from .htmlutil import _esc
from .config_jobs import _safe_cfg
from .state import load_notes
from .summary_engine import (DEFAULT_SUMMARY_SYSTEM, _md_to_html, _summary_input,
                             load_summary, load_summary_system,
                             summary_history_html, summary_system_is_custom,
                             system_prompt_path)


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
# Review prompt setting (/prompt) — see and edit what DeepSeek is actually told
# ---------------------------------------------------------------------------

def prompt_page(rel=None, embed=False):
    """The system prompt, editable, next to the data half it gets sent with.

    Two halves go to DeepSeek and only one of them is a setting. The system
    prompt is fixed text and is what you tune; the user message is assembled
    from the chosen report every time it runs, so it is shown read-only. Editing
    the first without seeing the second is guesswork, which is why both are here.
    """
    reps = list_reports()
    if not rel and reps:
        rel = reps[0]["rel"]
    opts = "".join(
        f"<option value='{_esc(r['rel'])}'{' selected' if r['rel'] == rel else ''}>"
        f"{_esc(r['label'])}</option>" for r in reps)

    current = load_summary_system()
    custom = summary_system_is_custom()
    badge = ("<span class='pstate custom' id='pBadge'>Customised</span>" if custom
             else "<span class='pstate def' id='pBadge'>Using the built-in "
                  "default</span>")

    try:
        preview = _summary_input(rel, load_notes(rel)) if rel else ""
    except Exception as e:  # noqa: BLE001
        # The preview reads and aggregates the whole report; a half-imported
        # folder should grey out one panel, not take the editor down with it.
        preview = f"(could not build the preview for this report: {e})"

    cfg = _safe_cfg()
    model = cfg.get("deepseek_model") or "deepseek-chat"
    head = ("" if embed else
            "<div class='hero'><a class='back' href='/'>&larr; Back to dashboard</a>"
            "<h1>Review prompt setting</h1>"
            "<p class='sub'>What DeepSeek is told before it reads your notes.</p></div>")
    body = (
        head + "<main>"
        "<section class='card'>"
        f"<div class='card-h'><h2>System prompt</h2>{badge}</div>"
        "<p class='hint'>These are the standing instructions sent with every "
        "<b>Generate / refresh review summary</b>. Edit them to change how the "
        "diagnosis is written &mdash; ask for shorter output, a different set of "
        "sections, harsher grading, or Chinese instead of English. Saving affects "
        "the <b>next</b> summary you generate; the ones already on disk are not "
        "rewritten.</p>"
        f"<textarea class='pta' id='pTa' spellcheck='false'>{_esc(current)}</textarea>"
        "<div class='pbar'>"
        "<button class='pbtn' id='pSave'>Save prompt</button>"
        "<button class='pbtn ghost' id='pReset'>Restore built-in default</button>"
        "<span id='pStat' class='pnote'></span><span class='grow'></span>"
        "</div>"
        f"<p class='pmeta' style='margin-top:12px'>Saved to "
        f"<code>{_esc(system_prompt_path())}</code> &middot; sent to model "
        f"<code>{_esc(model)}</code>. Delete that file, or press restore, to go "
        f"back to the shipped prompt.</p>"
        "</section>"
        "<section class='card'>"
        "<div class='card-h'><h2>The data it is sent with</h2></div>"
        "<p class='hint'>The second half of every request, rebuilt from the report "
        "each time &mdash; your spoken review notes plus the aggregate stats. It is "
        "generated, not a setting, so it is read-only here; this is exactly what "
        "the model sees.</p>"
        f"<div class='cmpbar' style='margin-bottom:12px'>Report "
        f"<select id='pRep' class='cmpsel'>{opts}</select></div>"
        f"<pre class='ppre'>{_esc(preview)}</pre>"
        "</section>"
        f"<pre id='pDefault' hidden>{_esc(DEFAULT_SUMMARY_SYSTEM)}</pre>"
        "</main>" + PROMPT_JS)
    return _page("Review prompt setting &middot; Mirror of Go", body, PROMPT_CSS)


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
