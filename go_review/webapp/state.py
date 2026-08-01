"""Per-report state: notes, voice transcript, hidden-blunder keys."""

import os
import json
import datetime

import report           # noqa: E402

from .listing import report_dir_from_rel
from .config_jobs import _safe_cfg


def _notes_path(rel):
    rdir = report_dir_from_rel(rel or "")
    return os.path.join(rdir, "notes.json") if rdir else None


def load_notes(rel):
    p = _notes_path(rel)
    if p and os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _voice_path(rel):
    rdir = report_dir_from_rel(rel or "")
    return os.path.join(rdir, "review_voice.md") if rdir else None


def load_voice(rel):
    p = _voice_path(rel)
    if p and os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""
    return ""


def save_voice(rel, text):
    p = _voice_path(rel)
    if not p:
        return False, "Report not found."
    try:
        with open(p, "w", encoding="utf-8") as f:
            f.write(text or "")
    except OSError as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"
    return True, None


def _hidden_path(rel):
    rdir = report_dir_from_rel(rel or "")
    return os.path.join(rdir, "practice_hidden.json") if rdir else None


def load_practice_hidden(rel):
    p = _hidden_path(rel)
    if p and os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return list(json.load(f))
        except Exception:
            return []
    return []


def _all_blunder_keys(rel):
    """Every blunder key (`filename#move`) that exists in this report *today*."""
    rdir = report_dir_from_rel(rel or "")
    if not rdir:
        return []
    games = report.load_games(rdir, _safe_cfg().get("games_dirs", []))
    keys = []
    for g in games:
        for m in g.get("all_user_moves", []):
            if ((m.get("points_lost", 0) or 0) >= report.PTS_BLUNDER
                    or (m.get("winrate_lost", 0) or 0) >= report.WR_BLUNDER):
                keys.append(f"{g.get('filename','')}#{m.get('move_number')}")
    return keys


def set_all_hidden(rel, hide):
    """Delete-all / restore-all.

    Deleting writes out the keys that exist *right now* rather than setting a
    blanket flag — that was the old `practice_cleared` marker, and it kept
    suppressing the section for games imported afterwards.  With explicit keys,
    a new game's blunders are simply keys nobody deleted, so they show up.

    Returns the number of hidden keys afterwards."""
    p = _hidden_path(rel)
    if not p:
        raise ValueError("Report not found.")
    keys = sorted(set(_all_blunder_keys(rel))) if hide else []
    with open(p, "w", encoding="utf-8") as f:
        json.dump(keys, f, ensure_ascii=False, indent=1)
    # Retire the legacy marker if this folder still has one, so it can never
    # hide a freshly analysed game again.
    rdir = report_dir_from_rel(rel or "")
    mp = os.path.join(rdir, "practice_cleared") if rdir else None
    if mp and os.path.exists(mp):
        try:
            os.remove(mp)
        except OSError as e:                      # noqa: BLE001
            print(f"  ! could not remove the legacy practice_cleared marker: {e}")
    return len(keys)


def add_practice_hidden(rel, nid):
    p = _hidden_path(rel)
    if not p:
        return False, "Report not found."
    if not nid:
        return False, "No blunder id given to delete."
    hidden = set(load_practice_hidden(rel))
    hidden.add(nid)
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(sorted(hidden), f, ensure_ascii=False, indent=1)
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"
    return True, None


def save_note(rel, nid, data):
    """Write/merge/delete a single blunder note in <report>/notes.json.
    data=None deletes.  Returns (ok, error)."""
    p = _notes_path(rel)
    if not p:
        return False, "Report not found."
    if not nid:
        return False, "No note id given."
    notes = load_notes(rel)
    if data is None:
        notes.pop(nid, None)
    else:
        data = dict(data)
        data["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
        notes[nid] = data
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=1)
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"
    return True, None
