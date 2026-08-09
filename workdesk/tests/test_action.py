"""Checks one-shot actions: they run to completion, report, and stay separate
from apps (an action must never be launched detached or aimed at by Stop)."""
import os, sys

sys.path.insert(0, os.path.expanduser("~/Desktop/ClaudeCode-Go"))
from workdesk import procs

results = []
def check(name, ok, detail=""):
    results.append(ok)
    print(("  PASS  " if ok else "  FAIL  ") + name + ("   -> " + detail if detail else ""))

OK   = {"id": "zz-act-ok",   "type": "action", "cwd": "~",
        "command": "echo hello-from-the-action"}
FAIL = {"id": "zz-act-fail", "type": "action", "cwd": "~",
        "command": "echo 'Could not connect to the daemon' >&2; exit 3"}
SLOW = {"id": "zz-act-slow", "type": "action", "cwd": "~",
        "command": "sleep 5", "timeout": 1}
APP  = {"id": "zz-act-app",  "command": "sleep 30", "cwd": "~"}

# --- 1. recognising an action ----------------------------------------------
check("type:action is an action", procs.is_action(OK))
check("an entry without a type is not", not procs.is_action(APP))

# --- 2. status before anything has run --------------------------------------
s = procs.status(OK)
check("an action is never 'running'", s["action"] and not s["running"])
check("no result until it has been run", s["last"] is None)

# --- 3. a successful run ----------------------------------------------------
ok, msg = procs.run_action(OK)
check("run_action succeeds", ok, msg)
check("the message says when it ran", msg.startswith("Ran at "), msg)
check("status now carries the result", procs.status(OK)["last"]["ok"])
log = procs.tail_log(OK["id"])
check("the command's output reached the log", "hello-from-the-action" in log)
check("the log records the exit code", "# exit code: 0" in log)

# --- 4. a failing run -------------------------------------------------------
ok, msg = procs.run_action(FAIL)
check("run_action reports failure", not ok, msg)
check("the failure message quotes the command, not a generic error",
      "Could not connect to the daemon" in msg, msg)
check("status carries the failure", procs.status(FAIL)["last"]["ok"] is False)

# --- 5. a run that never finishes -------------------------------------------
# The real action can sit on a macOS password dialog forever; it must give up
# rather than hold the request open for the rest of the session.
ok, msg = procs.run_action(SLOW)
check("a hung action times out instead of hanging", not ok, msg)
check("the timeout says so plainly", "Gave up after 1s" in msg, msg)

# --- 6. a missing working directory is refused, not run ---------------------
ok, msg = procs.run_action({**OK, "id": "zz-act-nowhere", "cwd": "/no/such/dir"})
check("a bad cwd fails cleanly", (not ok) and "does not exist" in msg, msg)

# --- 7. actions and apps do not share machinery -----------------------------
check("an app's status has no 'action' key", "action" not in procs.status(APP))

for app_id in ("zz-act-ok", "zz-act-fail", "zz-act-slow"):
    try:
        os.remove(procs.log_path(app_id))
    except OSError:
        pass

print()
bad = results.count(False)
print(f"{bad} FAILING" if bad else f"all {len(results)} checks passed")
sys.exit(1 if bad else 0)
