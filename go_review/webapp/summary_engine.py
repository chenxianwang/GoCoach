"""The DeepSeek-powered review summary: prompt building, the API call, and the summary archive."""

import os
import json
import html
import datetime

import report           # noqa: E402

from .paths import HERE
from .listing import report_dir_from_rel
from .htmlutil import _esc
from .config_jobs import _safe_cfg
from .state import load_notes, load_voice


# ---------------------------------------------------------------------------
# Review summary: hand the notes to DeepSeek and get a diagnostic profile back
# ---------------------------------------------------------------------------

def _prompt_file(name):
    try:
        with open(os.path.join(HERE, "prompts", name), "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


#: Where an edited system prompt is stored. The built-in text below stays the
#: default: the file is an *override*, so deleting it restores the shipped
#: prompt and an edit is never silently lost to a code change.
SYSTEM_PROMPT_FILE = "review_summary_system.md"


def system_prompt_path():
    return os.path.join(HERE, "prompts", SYSTEM_PROMPT_FILE)


def load_summary_system():
    """The system prompt in force: the saved override, else the built-in default."""
    return _prompt_file(SYSTEM_PROMPT_FILE).strip() or DEFAULT_SUMMARY_SYSTEM


def save_summary_system(text):
    """Persist an edited prompt. Blank text deletes the override (back to default).

    Returns (is_custom, error).
    """
    path = system_prompt_path()
    text = (text or "").strip()
    try:
        if not text:
            if os.path.exists(path):
                os.remove(path)
            return False, None
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        os.replace(tmp, path)          # never leave a half-written prompt
        return True, None
    except OSError as e:
        return os.path.exists(path), f"{type(e).__name__}: {e}"


def summary_system_is_custom():
    return bool(_prompt_file(SYSTEM_PROMPT_FILE).strip())


DEFAULT_SUMMARY_SYSTEM = (
        "You are a Go review coach. You will be given the aggregate data for a "
        "batch of one player's games, plus that player's own review commentary "
        "(mostly a transcript of them talking out loud, so expect slips, repetition "
        "and misheard Go terms). The commentary may be in Chinese, English or a mix; "
        "read whatever language it is in.\n\n"
        "Group the scattered mistakes into the few weakness categories that "
        "EMERGE FROM THESE NOTES. The categories are not from a preset list -- you "
        "name them yourself, based on what actually recurs (usually 3-6 of them, "
        "more or fewer as the data warrants).\n\n"
        "Requirements:\n"
        "- Diagnose root causes, not symptoms. The player usually already knows "
        "*what* went wrong; your job is *why* it went wrong that way, and whether "
        "the same flaw keeps reappearing.\n"
        "- Separate ability problems (they could not read it out, so they need "
        "targeted training) from habit problems (they saw it and did not do it, so "
        "it can be fixed immediately and pays off faster). Label each category as "
        "one or the other.\n"
        "- Reconstruct misheard Go terms from context (ladder, cap, ko fight, "
        "sabaki and similar are often transcribed wrong; in Chinese audio, "
        "zhengzi / feizhao / jiezheng / tengnuo). Do not make the player clean up "
        "the text first.\n"
        "- Be honest about the numbers. If the sample is small, say the difference "
        "is not significant rather than forcing a story of improvement or decline. "
        "Where lead conversion and comeback rate are given, if holding a lead is "
        "clearly weaker than coming back, make 'simplify once ahead / close the "
        "game out' a top priority.\n\n"
        "Output in ENGLISH markdown. Be concise. Do NOT list every move one by one, "
        "and do not use words like batch, cumulative, cross-batch or comparison -- "
        "this is one overall summary of all their notes, and newly added notes are "
        "simply more of the same material.\n"
        "1. An opening overall judgement (3-5 sentences) naming the 1-2 root causes "
        "most worth fixing.\n"
        "2. \"Your weakness profile\" -- a short paragraph per emerging category: "
        "the category name (yours), its essence / root cause, at most 1-2 "
        "representative moves, whether it is ability or habit, and what to train. "
        "A compact table is welcome (weakness | roughly how often | ability/habit).\n"
        "3. \"What you keep telling yourself\" -- the principles and maxims distilled "
        "from their spoken review.\n"
        "4. \"Training priorities\" -- ordered by what matters most, each with one "
        "concrete drill.\n"
        "Output the markdown only, with no pleasantries.")


def _summary_system():
    return load_summary_system()


def _summary_path(rel):
    rdir = report_dir_from_rel(rel or "")
    return os.path.join(rdir, "review_summary.md") if rdir else None


def load_summary(rel):
    p = _summary_path(rel)
    if p and os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""
    return ""


# ---------------------------------------------------------------------------
# Summary history: every generation is kept, so regenerating never destroys the
# previous diagnosis.  One file per version in <report>/summaries/, named for
# when it was made; review_summary.md stays as "the latest" so anything that
# already reads it keeps working.
# ---------------------------------------------------------------------------

SUMMARY_DIR = "summaries"


_STAMP_FMT = "%Y-%m-%d_%H%M%S"


def _summary_dir(rel, create=False):
    rdir = report_dir_from_rel(rel or "")
    if not rdir:
        return None
    d = os.path.join(rdir, SUMMARY_DIR)
    if create:
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            return None
    return d


def _adopt_legacy_summary(rel):
    """Older reports only ever had review_summary.md.  Fold it into the archive
    the first time we look, dated by its mtime, so no past diagnosis is lost."""
    d = _summary_dir(rel)
    p = _summary_path(rel)
    if not d or not p or not os.path.exists(p):
        return
    if os.path.isdir(d) and any(f.endswith(".md") for f in os.listdir(d)):
        return                                   # archive already started
    try:
        stamp = datetime.datetime.fromtimestamp(os.path.getmtime(p))
        os.makedirs(d, exist_ok=True)
        with open(p, encoding="utf-8") as f:
            text = f.read()
        with open(os.path.join(d, stamp.strftime(_STAMP_FMT) + ".md"),
                  "w", encoding="utf-8") as f:
            f.write(text)
    except OSError as e:                          # noqa: BLE001
        print(f"  ! could not archive the existing summary for {rel}: {e}")


def archive_summary(rel, text):
    """Store one generated summary as its own dated file."""
    d = _summary_dir(rel, create=True)
    if not d:
        return None
    path = os.path.join(d, datetime.datetime.now().strftime(_STAMP_FMT) + ".md")
    n = 2
    while os.path.exists(path):                   # same second, twice
        path = os.path.join(d, datetime.datetime.now().strftime(_STAMP_FMT)
                            + f"-{n}.md")
        n += 1
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path
    except OSError as e:                          # noqa: BLE001
        print(f"  ! could not archive the summary: {e}")
        return None


def list_summaries(rel):
    """[(datetime_or_None, path)] for every archived version, newest first."""
    _adopt_legacy_summary(rel)
    d = _summary_dir(rel)
    if not d or not os.path.isdir(d):
        return []
    out = []
    for fn in os.listdir(d):
        if not fn.endswith(".md"):
            continue
        try:
            when = datetime.datetime.strptime(fn[:17], _STAMP_FMT)
        except ValueError:
            when = None
        out.append((when, os.path.join(d, fn)))
    out.sort(key=lambda t: (t[0] or datetime.datetime.min), reverse=True)
    return out


def _pretty_stamp(when, path):
    if when:
        return when.strftime("%d %b %Y, %H:%M")
    return os.path.basename(path)[:-3]


def summary_history_html(rel, skip_latest=True):
    """Collapsible <details> for the older versions (the newest is already
    rendered in full above)."""
    rows = list_summaries(rel)
    if skip_latest:
        rows = rows[1:]
    if not rows:
        return ""
    out = ["<div class='sumhist'><div class='sumhist-h'>Previous summaries "
           f"<span class='nstat'>{len(rows)}</span></div>"]
    for when, path in rows:
        try:
            with open(path, encoding="utf-8") as f:
                md = f.read()
        except OSError:
            continue
        out.append("<details class='sumver'><summary>"
                   f"{_esc(_pretty_stamp(when, path))}</summary>"
                   f"<div class='smdbox'>{_md_to_html(md)}</div></details>")
    out.append("</div>")
    return "".join(out)


def export_summaries_md(rel):
    """Every version of this project's summaries in one Markdown document,
    oldest first, for handing to an AI at the end of a project."""
    rows = list(reversed(list_summaries(rel)))
    label = os.path.basename(str(report_dir_from_rel(rel) or rel).rstrip("/\\"))
    today = datetime.date.today().isoformat()
    parts = [f"# Review summaries — project {label}",
             "",
             f"{len(rows)} summary version(s), oldest first. Exported {today}.",
             ""]
    for i, (when, path) in enumerate(rows, 1):
        try:
            with open(path, encoding="utf-8") as f:
                md = f.read().strip()
        except OSError:
            continue
        parts.append(f"\n---\n\n## Version {i} — {_pretty_stamp(when, path)}\n")
        parts.append(md)
        parts.append("")
    return "\n".join(parts) + "\n"


def _summary_input(rel, notes):
    """Assemble the player's notes + aggregate stats as the DeepSeek user turn."""
    rdir = report_dir_from_rel(rel)
    cfg = _safe_cfg()
    games = report.load_games(rdir, cfg.get("games_dirs", []))
    agg = report.aggregate(games)

    lm = lmw = le = lew = bm = bmw = be = bew = 0
    from collections import Counter
    shapes = Counter()
    for g in games:
        c = report.classify_trajectory(g)
        if not c:
            continue
        shapes[report.TRAJ_LABEL.get(c["type"], c["type"])] += 1
        md_, ed_ = report._lead_flags(c["curve"])
        bd_, bed_ = report._behind_flags(c["curve"])
        if md_:
            lm += 1
            lmw += 1 if c["won"] else 0
        if ed_:
            le += 1
            lew += 1 if c["won"] else 0
        if bd_:
            bm += 1
            bmw += 1 if c["won"] else 0
        if bed_:
            be += 1
            bew += 1 if c["won"] else 0

    def pc(a, b):
        return f"{round(a / b * 100)}% ({a}/{b})" if b else "sample too small"

    L = []
    L.append("I am the player in this report. Below is the review material for all "
             "of my games -- please give me one overall summary of my weaknesses and "
             "my training priorities.")
    L.append("")
    L.append("## 1. Aggregate report stats")
    L.append(f"- {agg['n']} games: {agg['wins']}W {agg['losses']}L; "
             f"{agg['n_user_moves']} of my moves analysed.")
    L.append(f"- {agg['avg_points_lost']} points lost per move on average; "
             f"blunder rate {agg['blunder_rate']}%; "
             f"{agg['n_blunders']} blunders in total.")
    pa = agg.get("phase_avg", {})
    L.append(f"- Points lost per move by phase: fuseki {pa.get('opening','-')}, "
             f"middlegame {pa.get('middlegame','-')}, "
             f"yose {pa.get('endgame','-')}.")
    L.append(f"- Lead conversion (entered the phase >=90% winning and still won): "
             f"middlegame {pc(lmw, lm)}, yose {pc(lew, le)}.")
    L.append(f"- Comeback rate (entered the phase <=10% winning and still won): "
             f"middlegame {pc(bmw, bm)}, yose {pc(bew, be)}.")
    if shapes:
        L.append("- Game trajectory classes: " + ", ".join(f"{k} x{v}"
                                          for k, v in shapes.most_common()) + ".")
    L.append("")
    L.append("## 2. My spoken review (voice transcript -- expect slips, repetition "
             "and misheard terms; one passage often covers several moves in a row, so "
             "split it into individual mistakes)")
    voice = (load_voice(rel) or "").strip()
    L.append("")
    L.append(voice or "(No voice transcript for this report yet.)")
    L.append("")

    # Extra structured notes, if any still exist from the old per-position flow.
    if notes:
        L.append("## 3. Additional structured notes (where they duplicate the "
                 "spoken review, prefer the spoken version)")
        L.append("")
        ordered = sorted(notes.values(),
                         key=lambda x: (x.get("points_lost", 0) or 0), reverse=True)
        for i, note in enumerate(ordered, 1):
            wr = note.get("winrate_lost", 0) or 0
            txt = (note.get("note") or "").strip()
            bits = []
            if note.get("cause"):
                bits.append("cause: " + ", ".join(note["cause"]))
            if note.get("maxims"):
                bits.append("maxims: " + "; ".join(note["maxims"]))
            if txt:
                bits.append("comment: " + txt)
            L.append(f"- {note.get('game','')} move {note.get('move','?')}: "
                     f"I played {note.get('played','?')} (AI: {note.get('best','?')}), "
                     f"losing {note.get('points_lost',0)} pts / win rate -{round(wr)}%"
                     + ("; " + "; ".join(bits) if bits else ""))
        L.append("")

    # A reference list of the report's worst blunders so the model can map my
    # spoken references ("that C12 mistake...") to concrete moves.
    tb = agg.get("top_blunders", [])[:20]
    if tb:
        L.append("## Appendix: main blunders in this report (so you can map the "
                 "moves I mention out loud to concrete plays)")
        L.append("")
        L.append("| Game | Move | I played | KataGo | Pts lost | WR drop | Phase |")
        L.append("|---|---|---|---|---|---|---|")
        ph_lab = {"opening": "fuseki", "middlegame": "middlegame", "endgame": "yose"}
        for m in tb:
            wr = round((m.get("winrate_lost", 0) or 0) * 100)
            L.append(f"| {m.get('game','')} | {m.get('move_number','?')} | "
                     f"{m.get('played','?')} | {m.get('best','?')} | "
                     f"{m.get('points_lost',0)} | {wr}% | "
                     f"{ph_lab.get(m.get('phase',''), m.get('phase',''))} |")
        L.append("")

    L.append("")
    L.append("Group all of my review commentary above into the few weakness "
             "categories that emerge from it (name them yourself; do not use a preset "
             "list). Give me an overall judgement, a weakness profile (with "
             "representative moves, and whether each is ability or habit), the "
             "principles and maxims I keep repeating to myself, and concrete drills "
             "in priority order. Answer in English. Do not list every move one by "
             "one, and do not compare batches or reports.")
    return "\n".join(L)


def _call_deepseek(system, user, cfg):
    import urllib.request
    import urllib.error
    key = (cfg.get("deepseek_api_key") or "").strip()
    if not key:
        return None, ("DeepSeek is not configured yet. Add deepseek_api_key to "
                      "config.json and try again (that file is gitignored, so it is "
                      "never committed).")
    base = (cfg.get("deepseek_base_url") or "https://api.deepseek.com").rstrip("/")
    model = cfg.get("deepseek_model") or "deepseek-chat"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0.3,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        base + "/chat/completions", data=payload,
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=240) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"], None
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001
            pass
        return None, f"DeepSeek returned {e.code}: {body}"
    except Exception as e:  # noqa: BLE001
        return None, f"DeepSeek call failed: {e}"


def build_review_summary(rel):
    """Generate the diagnostic archive via DeepSeek; cache to review_summary.md."""
    rdir = report_dir_from_rel(rel or "")
    if not rdir:
        return None, "Report not found."
    notes = load_notes(rel)
    voice = (load_voice(rel) or "").strip()
    if not voice and not notes:
        return None, ("This report has no review material yet. Go to the blunder set, "
                      "press \"Start voice review\", talk through the blunders as you "
                      "look at them, and stop -- your take is transcribed, then come "
                      "back here to generate the summary.")
    text, err = _call_deepseek(_summary_system(),
                               _summary_input(rel, notes), _safe_cfg())
    if err:
        return None, err
    if not (text and text.strip()):
        return None, "DeepSeek returned nothing -- please try again shortly."
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    text = text.strip() + (f"\n\n---\n> Generated by DeepSeek from all of your review "
                           f"notes &middot; {stamp}\n")
    # Fold any pre-archive summary in first, so regenerating never silently
    # drops the one that was already on disk.
    _adopt_legacy_summary(rel)
    archive_summary(rel, text)
    try:
        with open(os.path.join(rdir, "review_summary.md"), "w",
                  encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass
    return text, None


def _md_to_html(md):
    """Minimal, dependency-free markdown -> HTML (headings/tables/lists/quote)."""
    import re as _re
    lines = (md or "").replace("\r\n", "\n").split("\n")
    n = len(lines)
    out = []
    i = 0

    def inline(s):
        s = html.escape(s)
        s = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        s = _re.sub(r"`(.+?)`", r"<code>\1</code>", s)
        return s

    row_re = _re.compile(r"^\s*\|.*\|\s*$")
    sep_re = _re.compile(r"^\s*\|[\s:\-|]+\|\s*$")
    while i < n:
        ln = lines[i]
        if row_re.match(ln) and i + 1 < n and sep_re.match(lines[i + 1]):
            hdr = [c.strip() for c in ln.strip().strip("|").split("|")]
            i += 2
            body = []
            while i < n and row_re.match(lines[i]):
                body.append([c.strip() for c in
                             lines[i].strip().strip("|").split("|")])
                i += 1
            t = ["<table class='smd'><thead><tr>"]
            t += ["<th>" + inline(c) + "</th>" for c in hdr]
            t.append("</tr></thead><tbody>")
            for r in body:
                t.append("<tr>" + "".join("<td>" + inline(c) + "</td>"
                                          for c in r) + "</tr>")
            t.append("</tbody></table>")
            out.append("".join(t))
            continue
        m = _re.match(r"^(#{1,4})\s+(.*)$", ln)
        if m:
            lv = len(m.group(1))
            out.append(f"<h{lv}>" + inline(m.group(2)) + f"</h{lv}>")
            i += 1
            continue
        if _re.match(r"^\s*(-{3,}|\*{3,})\s*$", ln):
            out.append("<hr>")
            i += 1
            continue
        if _re.match(r"^\s*>\s?", ln):
            buf = []
            while i < n and _re.match(r"^\s*>\s?", lines[i]):
                buf.append(inline(_re.sub(r"^\s*>\s?", "", lines[i])))
                i += 1
            out.append("<blockquote>" + "<br>".join(buf) + "</blockquote>")
            continue
        if _re.match(r"^\s*[-*+]\s+", ln):
            buf = []
            while i < n and _re.match(r"^\s*[-*+]\s+", lines[i]):
                buf.append("<li>" + inline(_re.sub(r"^\s*[-*+]\s+", "",
                                                   lines[i])) + "</li>")
                i += 1
            out.append("<ul>" + "".join(buf) + "</ul>")
            continue
        if _re.match(r"^\s*\d+\.\s+", ln):
            buf = []
            while i < n and _re.match(r"^\s*\d+\.\s+", lines[i]):
                buf.append("<li>" + inline(_re.sub(r"^\s*\d+\.\s+", "",
                                                   lines[i])) + "</li>")
                i += 1
            out.append("<ol>" + "".join(buf) + "</ol>")
            continue
        if ln.strip() == "":
            i += 1
            continue
        out.append("<p>" + inline(ln) + "</p>")
        i += 1
    return "\n".join(out)
