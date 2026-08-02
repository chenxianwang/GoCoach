"""Which problems you have marked as understood.

Kept server-side in data/hidden.json rather than in the browser, so the mark
survives a rebuild, a different browser, and shows up in a backup -- the same
reasoning as go_review's practice_hidden.json.

Keyed by qid (the site's stable question id), not by attempt: understanding a
problem applies to every time you have met it, and you will meet it again.
"""

import os
import json
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "data", "hidden.json")


def load():
    """{qid: iso-timestamp} for problems marked understood."""
    if not os.path.exists(PATH):
        return {}
    try:
        with open(PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (ValueError, OSError):
        return {}
    got = data.get("hidden", data)
    if not isinstance(got, dict):        # tolerate an older plain list
        got = {str(q): "" for q in (got or [])}
    return {str(k): v for k, v in got.items()}


def save(mapping):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"hidden": mapping}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PATH)                # never leave a half-written file


def set_hidden(qid, hidden=True):
    """Mark one problem understood (or put it back). Returns the new count."""
    m = load()
    key = str(qid)
    if hidden:
        m.setdefault(key, datetime.datetime.now().isoformat(timespec="seconds"))
    else:
        m.pop(key, None)
    save(m)
    return len(m)


def clear():
    save({})
