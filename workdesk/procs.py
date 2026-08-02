"""Starting, stopping and status-checking the apps listed in apps.json.

Two things here are less obvious than they look:

* `shell=True` means Popen's pid is the *shell*, not the app. Killing that pid
  leaves the real process orphaned and still running, so everything is started
  in its own session (`start_new_session=True`) and stopped by signalling the
  whole process group.

* An app can be running without this launcher having started it -- you may have
  launched it from Terminal, or restarted the launcher since. So status is not
  "did I start it": it is probed for real, by connecting to its port or looking
  for its process. That is what makes the page trustworthy after a restart.
"""

import os
import json
import time
import signal
import socket
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
LOGS = os.path.join(HERE, "logs")

#: id -> Popen, for apps this process started
_started = {}


def _expand(p):
    return os.path.expanduser(os.path.expandvars(p)) if p else None


def log_path(app_id):
    return os.path.join(LOGS, f"{app_id}.log")


# -- status ---------------------------------------------------------------
def port_open(port, host="127.0.0.1", timeout=0.35):
    """True if something is listening. Used instead of trusting our own PID
    table, so an app started from Terminal still shows as running."""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def process_running(match):
    """True if a process matching `match` exists (pgrep -f)."""
    try:
        r = subprocess.run(["pgrep", "-f", match],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return r.returncode == 0
    except OSError:
        return False


def probe(app):
    """Is this app up? None when it declares no probe."""
    p = app.get("probe") or {}
    if p.get("type") == "port":
        return port_open(p.get("port"), p.get("host", "127.0.0.1"))
    if p.get("type") == "process":
        return process_running(p.get("match", app["id"]))
    return None


def status(app):
    """One app's state, as the page renders it."""
    app_id = app["id"]
    proc = _started.get(app_id)
    ours = bool(proc and proc.poll() is None)
    up = probe(app)
    if up is None:                 # nothing to probe with -- fall back to ours
        up = ours
    exit_code = None
    if proc is not None and proc.poll() is not None:
        exit_code = proc.returncode
    return {
        "id": app_id,
        "running": bool(up),
        "started_here": ours,
        "exit_code": exit_code,
        "log": os.path.exists(log_path(app_id)),
    }


# -- lifecycle ------------------------------------------------------------
def start(app):
    """Launch an app detached, with output captured to logs/<id>.log.

    Returns (ok, message). Refuses to double-start something already up.
    """
    app_id = app["id"]
    if status(app)["running"]:
        return False, "Already running."

    os.makedirs(LOGS, exist_ok=True)
    cwd = _expand(app.get("cwd")) or os.path.expanduser("~")
    if not os.path.isdir(cwd):
        return False, f"Working directory does not exist: {cwd}"

    logf = open(log_path(app_id), "w", encoding="utf-8", errors="replace")
    logf.write(f"$ {app['command']}\n"
               f"# cwd: {cwd}\n"
               f"# started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    logf.flush()
    try:
        proc = subprocess.Popen(
            app["command"], shell=True, cwd=cwd,
            stdout=logf, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,      # own process group -> stoppable
        )
    except Exception as e:               # noqa: BLE001
        logf.close()
        return False, f"{type(e).__name__}: {e}"
    _started[app_id] = proc

    # A command that is going to fail usually does so immediately; surface that
    # now rather than leaving the card claiming success.
    time.sleep(0.6)
    if proc.poll() is not None and proc.returncode != 0:
        return False, (f"Exited immediately with code {proc.returncode} -- "
                       f"see the log.")
    return True, "Launched."


def stop(app):
    """Stop an app we started: TERM the process group, KILL if it lingers."""
    app_id = app["id"]
    proc = _started.get(app_id)
    if not proc or proc.poll() is not None:
        if probe(app):
            return False, ("Running, but not started from here -- stop it "
                           "where you launched it.")
        return False, "Not running."
    try:
        pgid = os.getpgid(proc.pid)
    except OSError:
        return False, "Process already gone."
    for sig, wait in ((signal.SIGTERM, 3.0), (signal.SIGKILL, 1.5)):
        try:
            os.killpg(pgid, sig)
        except OSError:
            break
        deadline = time.time() + wait
        while time.time() < deadline:
            if proc.poll() is not None:
                return True, "Stopped."
            time.sleep(0.1)
    return True, "Stopped (forced)."


def tail_log(app_id, lines=200):
    path = log_path(app_id)
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return "".join(f.readlines()[-lines:])


# -- config ---------------------------------------------------------------
def load_apps(path=None):
    p = path or os.path.join(HERE, "apps.json")
    with open(p, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    apps = [a for a in cfg.get("apps", []) if a.get("id") and a.get("command")]
    return cfg, apps
