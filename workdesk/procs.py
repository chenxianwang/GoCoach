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

* Stopping follows the same rule. `_started` only survives as long as this
  process, so refusing to stop anything missing from it made Stop dead on
  arrival every time the launcher window was reopened. Instead the app is
  located the same way it is probed -- by port or process name -- and that is
  what gets signalled. `_signal_targets` is deliberately careful about what it
  will aim at: never this launcher, never its process group, never one of its
  ancestors (that would take the Terminal down with it).

* Not everything worth a button is an app. An entry marked `"type": "action"`
  is a one-shot command -- it has no lifetime to probe and nothing to stop, so
  it is *waited on* rather than detached, and the card reports how it went.
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

#: id -> {"ok", "message", "at"} for the last run of each one-shot action
_ran = {}

#: How long to wait on an action before giving up. Generous on purpose: an
#: action may be wrapped in `osascript ... with administrator privileges`, and
#: that password dialog sits there until somebody answers it.
ACTION_TIMEOUT = 180


def _expand(p):
    return os.path.expanduser(os.path.expandvars(p)) if p else None


def log_path(app_id):
    return os.path.join(LOGS, f"{app_id}.log")


def is_action(app):
    """A one-shot command rather than an app with a lifetime.

    Marked `"type": "action"` in apps.json. The card shows a single Run button
    and the result of the last run -- there is nothing to probe or stop.
    """
    return (app.get("type") or "").lower() == "action"


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
    if is_action(app):
        # Nothing to probe -- an action is over as soon as it has run. What the
        # card wants is the result, which only lives here in memory, so it
        # resets to "Ready" when the launcher restarts. The log survives.
        return {
            "id": app_id,
            "action": True,
            "running": False,
            "last": _ran.get(app_id),
            "log": os.path.exists(log_path(app_id)),
        }
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


def run_action(app):
    """Run a one-shot command to completion and report how it went.

    The opposite of `start` in every way that matters: this waits, because the
    result *is* the point, and it captures output rather than detaching. The
    output still goes to `logs/<id>.log`, so `log` on the card shows the
    command's own words when the summary is not enough.
    """
    app_id = app["id"]
    os.makedirs(LOGS, exist_ok=True)
    cwd = _expand(app.get("cwd")) or os.path.expanduser("~")
    if not os.path.isdir(cwd):
        return False, f"Working directory does not exist: {cwd}"

    limit = app.get("timeout") or ACTION_TIMEOUT
    out, code, note = "", None, None
    try:
        r = subprocess.run(app["command"], shell=True, cwd=cwd,
                           stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, errors="replace", timeout=limit)
        out, code = (r.stdout or "") + (r.stderr or ""), r.returncode
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") + (e.stderr or "") if e.stdout or e.stderr else ""
        note = f"Gave up after {limit}s -- it never finished."
    except Exception as e:                   # noqa: BLE001
        note = f"{type(e).__name__}: {e}"

    at = time.strftime("%H:%M:%S")
    with open(log_path(app_id), "w", encoding="utf-8", errors="replace") as f:
        f.write(f"$ {app['command']}\n"
                f"# cwd: {cwd}\n"
                f"# ran: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(out or "(no output)\n")
        f.write(f"\n# exit code: {'-' if code is None else code}\n")

    ok = (code == 0)
    if note:
        message = note
    elif ok:
        message = f"Ran at {at}"
    elif "User canceled" in out:
        # osascript's own words when the password dialog is dismissed. Worth
        # naming, because it is the ordinary way to back out, not a failure.
        message = "Cancelled -- no password given."
    else:
        first = next((ln.strip() for ln in out.splitlines() if ln.strip()), "")
        message = first[:160] if first else f"Failed with exit code {code}."
    _ran[app_id] = {"ok": ok, "message": message, "at": at}
    return ok, message


def _ancestors():
    """Our own pid plus every parent up to init -- never signal these."""
    out = set()
    pid = os.getpid()
    for _ in range(24):                  # cycles are impossible, but be finite
        out.add(pid)
        if pid <= 1:
            break
        try:
            r = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)],
                               capture_output=True, text=True)
            pid = int(r.stdout.strip())
        except (OSError, ValueError):
            break
    return out


def _pids_from_probe(app):
    """PIDs currently backing this app, found the same way it is probed."""
    p = app.get("probe") or {}
    pids = []
    try:
        if p.get("type") == "port":
            r = subprocess.run(
                ["lsof", "-t", "-nP", f"-iTCP:{int(p['port'])}", "-sTCP:LISTEN"],
                capture_output=True, text=True)
            pids = [int(x) for x in r.stdout.split()]
        elif p.get("type") == "process":
            r = subprocess.run(["pgrep", "-f", p.get("match", app["id"])],
                               capture_output=True, text=True)
            pids = [int(x) for x in r.stdout.split()]
    except (OSError, ValueError, KeyError):
        return []

    # A `process` probe is just a substring match, so it can easily sweep in
    # this launcher or the shell that started it. Those must never be targets.
    unsafe = _ancestors()
    return [pid for pid in pids if pid > 1 and pid not in unsafe]


def _signal_targets(pids, sig):
    """Signal each pid's whole process group, falling back to the pid itself.

    Group-wide because `shell=True` leaves the real app as a child of a shell;
    signalling only the leader would orphan it. But an app can share a process
    group with this launcher (both started from one non-interactive shell), and
    killpg on our own group would take us down with it -- so in that case the
    pid alone is signalled.
    """
    unsafe = _ancestors()
    try:
        my_group = os.getpgid(os.getpid())
    except OSError:
        my_group = None

    sent = False
    groups = set()
    for pid in pids:
        try:
            pgid = os.getpgid(pid)
        except OSError:
            continue
        group_is_safe = (pgid > 1 and pgid != my_group and pgid not in unsafe)
        if group_is_safe and pgid not in groups:
            groups.add(pgid)
            try:
                os.killpg(pgid, sig)
                sent = True
                continue
            except OSError:
                pass
        try:
            os.kill(pid, sig)
            sent = True
        except OSError:
            pass
    return sent


def _gone(app, proc):
    """Has the app actually stopped? Prefer the live probe over our own PID."""
    up = probe(app)
    if up is None:
        return proc is None or proc.poll() is not None
    return not up


def stop(app):
    """Stop an app: TERM the process group, KILL if it lingers.

    Works whether or not this launcher started it -- see the module docstring.
    """
    app_id = app["id"]
    proc = _started.get(app_id)
    ours = bool(proc and proc.poll() is None)

    if ours:
        pids = [proc.pid]
    else:
        proc = None
        if not probe(app):
            return False, "Not running."
        pids = _pids_from_probe(app)
        if not pids:
            return False, ("Running, but its process could not be found. It may "
                           "belong to another user, or be reachable on that port "
                           "from somewhere else on the machine.")

    for sig, wait in ((signal.SIGTERM, 3.0), (signal.SIGKILL, 1.5)):
        if not _signal_targets(pids, sig):
            break
        deadline = time.time() + wait
        while time.time() < deadline:
            if _gone(app, proc):
                _started.pop(app_id, None)
                return True, "Stopped." if sig == signal.SIGTERM else "Stopped (forced)."
            time.sleep(0.1)

    if _gone(app, proc):
        _started.pop(app_id, None)
        return True, "Stopped (forced)."
    return False, "Could not stop it -- it is still running."


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
