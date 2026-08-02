"""Project backup: manifest, zip build, and report deletion."""

import io
import os
import zipfile
import shutil
import datetime

import import_lizzie   # noqa: E402

from .paths import HERE
from .listing import _SUMMARY_CACHE, list_reports, report_dir_from_rel
from .static_export import write_static_index
from .summary_engine import SUMMARY_DIR


# ---------------------------------------------------------------------------
# Backup: zip the project itself plus the notes you cannot regenerate.
#
# Deliberately left out: review_report.html and index.html (generated on every
# rebuild), the per-game *.sgf.json (derived from the analysed SGFs you import),
# and config.json (plaintext ikatago password + DeepSeek key — a backup should
# be safe to drop in cloud storage).  That takes ~85 MB down to well under one.
# ---------------------------------------------------------------------------

BACKUP_SKIP_DIRS = {"__pycache__", ".ipynb_checkpoints", ".git", "node_modules"}


BACKUP_SKIP_FILES = {".DS_Store", "config.json", "index.html",
                     "review_report.html"}


# Inside a report folder these are yours; everything else there is derived.

BACKUP_REPORT_FILES = {"review_voice.md", "review_summary.md",
                       "practice_hidden.json", "notes.json"}


BACKUP_README = """Mirror of Go — project backup
=============================

Made {when} from {root}

WHAT IS IN HERE
  <repo>/*.command                the double-click launcher
  <repo>/My games/                the Fox downloader module that pipeline.py
    fox_full_downloader.py        imports (no downloaded games, just the code)
  <repo>/go_review/*.py           the application
  <repo>/go_review/*.md,          docs and the original skill prompts
    prompts/, tests/, avatar/
  <repo>/go_review/               settings template
    config.example.json
  <repo>/go_review/<report>/      per project:
      *.sgf.json                    the per-game KataGo analysis - this is
                                    what rebuilds the reports (step 2)
      review_voice.md               your spoken-review transcripts
      review_summary.md             the latest DeepSeek diagnosis
      summaries/*.md                every archived summary version
      practice_hidden.json          which blunders you deleted/mastered
      notes.json                    legacy per-position notes, if any
  <repo>/tsumego/               the 101weiqi Skill Test diagnostics: source,
    *.py, README.md, tests/     plus data/ (the crawl cache - kept because it
    data/runs/, data/diagrams/  is thousands of throttled requests to rebuild)

WHAT IS DELIBERATELY LEFT OUT
  config.json          holds your ikatago password and DeepSeek API key in
                       plain text (and, under tsumego/, your 101weiqi session
                       cookie). Excluded so this zip is safe to store or
                       share. See step 3 below.
  config.txt (Lizzie)  also stores the ikatago password.
  review_report.html   regenerated in seconds from the JSON above:
  index.html             python3 go_review/web_app.py --rebuild-reports
  My games/<games>      your downloaded/analysed SGFs (~114 MB) - back these
                       up separately if you want them.
  ikatago / KataGo      the engine binaries and network weights.
  Voice recordings (.webm) live in your English Coach library, not here.

TO RESTORE ON ANOTHER MAC
  1. Unzip.
  2. Rebuild the reports from the analysis JSON (a few seconds, no engine and
     no internet needed):
         python3 go_review/web_app.py --rebuild-reports
  3. Start it - double-click the .command file, or:
         python3 go_review/web_app.py
     It runs WITHOUT config.json, falling back to config.example.json, so
     everything you can read is available straight away.
     If double-clicking does nothing, the executable bit was lost in the zip:
         chmod +x *.command
     On first launch macOS may block it: right-click > Open, or allow it in
     System Settings > Privacy & Security.

  That is all that is needed to READ everything. The rest is only for making
  NEW reviews on that machine:
  4. Copy config.example.json to config.json and refill: ikatago_command,
     deepseek_api_key, games_dirs, output_dir, user_names, whisper_model,
     voice_audio_dir, lizzie_jar.
  5. Install what is machine-specific:
         pip install faster-whisper      (voice transcription)
         a faster-whisper model at the path in whisper_model
         the ikatago client + your Fox login (cloud KataGo)
         LizzieYZY + Java, if you import analysed SGFs that way

WHAT WORKS AFTER STEPS 1-3, WITH NOTHING INSTALLED
  - every report: overview, trajectory, blunder diagrams, game by game
  - your voice transcripts, and every archived review summary + export
  - the Go terms dictionary, compare reports, the offline index.html
  Only recording, transcribing, analysing and generating NEW summaries
  need steps 4-5.
"""


def _backup_top():
    """Name of the top folder inside the zip — the repo folder, so unzipping
    reproduces `<repo>/一目弈镜.command` next to `<repo>/go_review/`."""
    return os.path.basename(os.path.dirname(HERE)) or "ClaudeCode-Go"


def backup_manifest():
    """[(absolute_path, name_inside_the_zip)] for everything worth keeping.

    The zip is rooted at the *repo* folder, not go_review, because the launcher
    (`一目弈镜.command`) and the Fox downloader that `pipeline` imports both live
    one level up.  Unzipping therefore gives a tree you can actually run.
    Only named files are taken from outside go_review — never the 114 MB of
    downloaded games, the ikatago/KataGo binaries, or Lizzie's config.txt
    (which also stores the ikatago password)."""
    root = HERE
    repo = os.path.dirname(root)
    top = _backup_top()
    try:
        reports = {os.path.abspath(d) for d in import_lizzie.list_report_dirs(root)}
    except Exception:                             # noqa: BLE001
        reports = set()
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in BACKUP_SKIP_DIRS and not d.startswith(".")]
        absdir = os.path.abspath(dirpath)
        owner = next((r for r in reports
                      if absdir == r or absdir.startswith(r + os.sep)), None)
        for fn in sorted(filenames):
            if fn in BACKUP_SKIP_FILES or fn.startswith("."):
                continue
            if owner:
                inside = os.path.relpath(absdir, owner)
                if inside == os.curdir:
                    # Your notes, plus the per-game analysis JSON — that is what
                    # lets `--rebuild-reports` bring the reports back on another
                    # machine without re-importing the SGFs.  Only the generated
                    # review_report.html is skipped (see BACKUP_SKIP_FILES).
                    if not (fn in BACKUP_REPORT_FILES or fn.endswith(".json")):
                        continue
                elif inside == SUMMARY_DIR:
                    if not fn.endswith(".md"):
                        continue
                else:
                    continue                  # nothing else in a report folder
            p = os.path.join(absdir, fn)
            out.append((p, "/".join([top, "go_review",
                                     os.path.relpath(p, root)])))

    # The sibling tsumego package: its source, and its crawl cache. The cache is
    # included on purpose -- it is thousands of throttled requests against a
    # small site, so it is exactly the "expensive to regenerate" category the
    # per-game analysis JSON is in. config.json (the 101weiqi session cookie) is
    # skipped by BACKUP_SKIP_FILES like every other config.json; dashboard.html
    # is regenerated on every view.
    tz = os.path.join(repo, "tsumego")
    for dirpath, dirnames, filenames in os.walk(tz):
        dirnames[:] = [d for d in dirnames
                       if d not in BACKUP_SKIP_DIRS and not d.startswith(".")]
        for fn in sorted(filenames):
            if (fn in BACKUP_SKIP_FILES or fn.startswith(".")
                    or fn == "dashboard.html"):
                continue
            p = os.path.join(dirpath, fn)
            out.append((p, "/".join([top, os.path.relpath(p, repo)])))

    # The few things outside go_review that the app genuinely needs to run.
    extras = [os.path.join(repo, "My games", "fox_full_downloader.py")]
    try:
        for fn in sorted(os.listdir(repo)):
            if fn.endswith(".command") or fn in ("README.md", "LICENSE",
                                                 ".gitignore"):
                extras.append(os.path.join(repo, fn))
    except OSError:
        pass
    for p in extras:
        if os.path.isfile(p):
            out.append((p, "/".join([top, os.path.relpath(p, repo)])))
    return sorted(out, key=lambda t: t[1])


def build_backup_zip():
    """Return (zip_bytes, file_count, uncompressed_bytes)."""
    files = backup_manifest()
    buf = io.BytesIO()
    total = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr(_backup_top() + "/BACKUP_README.txt", BACKUP_README.format(
            when=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), root=HERE))
        for path, arc in files:
            try:
                z.write(path, arc)
                total += os.path.getsize(path)
            except OSError as e:                  # noqa: BLE001
                print(f"  ! skipped {arc}: {e}")
    return buf.getvalue(), len(files), total


def delete_report(rel):
    """Delete a report folder. Only known report dirs strictly under HERE may be
    removed. Returns (ok, error_message)."""
    if not rel or not str(rel).strip():
        return False, "No report given to delete."
    rdir = report_dir_from_rel(rel)
    if not rdir:
        return False, "Report not found (or the path is invalid)."
    known = {r["rel"] for r in list_reports()}
    if os.path.relpath(rdir, HERE) not in known:
        return False, "That folder is not an analysed report -- refusing to delete it."
    try:
        shutil.rmtree(rdir)
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"
    _SUMMARY_CACHE.pop(rdir, None)
    write_static_index()
    return True, None
