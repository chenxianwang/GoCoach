"""Checks that Working Desktop can stop an app it did not start."""
import os, sys, time, socket, subprocess

sys.path.insert(0, os.path.expanduser("~/Desktop/ClaudeCode-Go"))
from workdesk import procs

PORT = 8799
APP = {"id": "dummy", "command": f"python3 -m http.server {PORT} --bind 127.0.0.1",
       "cwd": "~", "probe": {"type": "port", "port": PORT}}

results = []
def check(name, ok, detail=""):
    results.append(ok)
    print(("  PASS  " if ok else "  FAIL  ") + name + ("   -> " + detail if detail else ""))

def up(timeout=0.3):
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=timeout):
            return True
    except OSError:
        return False

def wait_for(want, secs=6):
    end = time.time() + secs
    while time.time() < end:
        if up() == want:
            return True
        time.sleep(0.15)
    return up() == want

# --- 1. an app started OUTSIDE the launcher (the reported bug) --------------
outsider = subprocess.Popen(APP["command"], shell=True, start_new_session=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
check("external app came up", wait_for(True))
check("status says running but not started_here",
      procs.status(APP)["running"] and not procs.status(APP)["started_here"])

ok, msg = procs.stop(APP)
check("stop() reports success on an externally started app", ok, msg)
check("port is actually free afterwards", wait_for(False))
outsider.wait(timeout=5)

# --- 2. the normal path: started by the launcher ----------------------------
ok, msg = procs.start(APP)
check("start() works", ok, msg)
check("app came up", wait_for(True))
check("status says started_here", procs.status(APP)["started_here"])
ok, msg = procs.stop(APP)
check("stop() works on our own app", ok, msg)
check("port free afterwards", wait_for(False))

# --- 3. stopping something that is not running ------------------------------
ok, msg = procs.stop(APP)
check("stop() on a stopped app reports 'Not running'", (not ok) and "Not running" in msg, msg)

# --- 4. safety: never target the launcher, its group, or its ancestors ------
me = os.getpid()
broad = {"id": "broad", "probe": {"type": "process", "match": "python"}}
targets = procs._pids_from_probe(broad)
check("a broad process match never selects this process", me not in targets,
      f"{len(targets)} pids selected, ours ({me}) " + ("present!" if me in targets else "absent"))
anc = procs._ancestors()
check("no ancestor of this process is ever selected", not (set(targets) & anc),
      f"ancestors={sorted(anc)}")
check("pid 1 is never selected", 1 not in targets)

print()
bad = results.count(False)
print(f"{bad} FAILING" if bad else f"all {len(results)} checks passed")
sys.exit(1 if bad else 0)
