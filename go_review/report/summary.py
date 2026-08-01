"""The Review Summary section container."""

from .assets import SUMMARY_SECT_JS


def summary_section():
    return (
        "<h2>Review summary &middot; diagnostic profile</h2>"
        "<p class='sub'>Built from the reviews you <b>spoke into the recorder</b> in "
        "the blunder set, plus this report's lead conversion, comeback rate and "
        "blunder distribution. DeepSeek <b>derives your own weakness categories "
        "straight from your notes</b> (not a fixed checklist) and diagnoses the root "
        "causes -- conclusions and training priorities only, no move-by-move list. "
        "The result is saved into this report, so next time it loads instantly.</p>"
        "<div class='vcrow' style='margin:12px 0'>"
        "<button type='button' class='vcbtn' id='rsBtn' onclick='rsGenerate()'>"
        "&#8635; Generate / refresh review summary</button>"
        "<a class='sumexp' id='rsExp' download href='#' "
        "title='Every version of this project&#39;s summary in one Markdown file'>"
        "&#8681; Export all versions</a>"
        "<span class='vcstat sub' id='rsStat'></span></div>"
        "<div id='rsBody' class='smdbox'>"
        "<p class='sub'>Nothing generated yet. Record a spoken review in the blunder "
        "set first, then press the button above.</p>"
        "</div>"
        "<div id='rsHist'></div>"
        + SUMMARY_SECT_JS)
