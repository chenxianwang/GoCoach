"""Discovering and summarising report folders on disk."""

import os
import json
from urllib.parse import unquote

import pipeline       # noqa: E402
import import_lizzie  # noqa: E402
import report         # noqa: E402

from .paths import HERE


# ---------------------------------------------------------------------------
# Discovering, summarising and resolving report folders
# ---------------------------------------------------------------------------

_SUMMARY_CACHE = {}   # rdir -> (dir_mtime, summary dict)


def report_summary(rdir):
    """Cheap per-report summary for dashboard cards: game count, win/loss,
    last game date, source label. Cached and invalidated on dir mtime."""
    import glob as _glob
    try:
        dmt = os.path.getmtime(rdir)
    except OSError:
        dmt = 0
    cached = _SUMMARY_CACHE.get(rdir)
    if cached and cached[0] == dmt:
        return cached[1]
    games = wins = losses = 0
    last_date = ""
    for p in _glob.glob(os.path.join(rdir, "*.json")):
        if os.path.basename(p) in ("index.json", "notes.json", "practice_hidden.json"):
            continue
        games += 1
        try:
            with open(p, encoding="utf-8") as f:
                g = json.load(f)
        except Exception:
            continue
        w = g.get("won")
        if w is True:
            wins += 1
        elif w is False:
            losses += 1
        d = g.get("date") or ""
        if d > last_date:
            last_date = d
    try:
        source = report.source_label_from_path(rdir)
    except Exception:
        source = ""
    summ = {"games": games, "wins": wins, "losses": losses,
            "last_date": last_date, "source": source}
    _SUMMARY_CACHE[rdir] = (dmt, summ)
    return summ


def list_reports():
    """[{rel, label, mtime, has_html, summary}] -- existing reports, newest first."""
    out = []
    for d in import_lizzie.list_report_dirs(HERE):
        rel = os.path.relpath(d, HERE)
        html_path = os.path.join(d, "review_report.html")
        has_html = os.path.exists(html_path)
        try:
            mt = os.path.getmtime(html_path if has_html else d)
        except OSError:
            mt = 0
        out.append({"rel": rel, "label": rel, "mtime": mt,
                    "has_html": has_html, "summary": report_summary(d)})
    # newest game date first (fall back to file mtime for ties / undated)
    out.sort(key=lambda r: (r["summary"].get("last_date") or "", r["mtime"]),
             reverse=True)
    return out


def list_games_dirs():
    """Subfolders under "My games" that contain SGF files (depth <= 2), as
    relative paths — used to populate the download-folder picker."""
    base = pipeline.DOWNLOADER_DIR
    out = []
    if not os.path.isdir(base):
        return out
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs
                   if not d.startswith(".") and d != "__pycache__"]
        rel = os.path.relpath(root, base)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth >= 2:
            dirs[:] = []          # don't descend deeper than 2 levels
        if root == base:
            continue
        nsgf = sum(1 for f in files if f.lower().endswith(".sgf"))
        if nsgf:
            out.append({"rel": rel, "sgf": nsgf})
    out.sort(key=lambda r: r["rel"])
    return out


def report_dir_from_rel(rel):
    """Resolve a report rel-path safely under HERE. None if outside / missing."""
    rel = unquote(rel).strip("/")
    target = os.path.normpath(os.path.join(HERE, rel))
    if os.path.commonpath([target, HERE]) != HERE:
        return None
    if target == HERE or not os.path.isdir(target):
        return None
    return target
