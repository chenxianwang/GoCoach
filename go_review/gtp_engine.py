"""Drive ikatago (a remote KataGo proxy) as a GTP engine for analysis.

ikatago behaves exactly like a local KataGo GTP engine -- it just relays to a
cloud GPU. That means it understands standard GTP plus KataGo's `kata-analyze`
extension, which is what Lizzie uses. We launch it as a subprocess, wait for the
cloud login to finish, then issue commands.

Because `kata-analyze` ponders indefinitely, we read its streaming `info` lines
for a bounded time / visit budget, keep the richest line, then stop the search
by sending a cheap follow-up command.
"""

import subprocess
import threading
import queue
import time
import shlex
import re


class GtpError(RuntimeError):
    pass


class IkatagoEngine:
    def __init__(self, command, ready_timeout=90, verbose=True):
        """command: full shell command string used to launch ikatago.
        ready_timeout: seconds to wait for the cloud engine to become responsive.
        """
        self.command = command
        self.ready_timeout = ready_timeout
        self.verbose = verbose
        self.proc = None
        self._stdout_q = queue.Queue()
        self._reader = None

    # ---- process lifecycle -------------------------------------------------
    def start(self):
        args = shlex.split(self.command)
        if self.verbose:
            print(f"[engine] launching: {self.command}")
        self.proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,
            universal_newlines=True,
        )
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()
        # Drain stderr in the background so the pipe never blocks; surface login
        # progress to the user.
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        self._wait_until_ready()

    def _read_stdout(self):
        for line in self.proc.stdout:
            self._stdout_q.put(line.rstrip("\n"))
        self._stdout_q.put(None)  # sentinel: stream closed

    def _drain_stderr(self):
        for line in self.proc.stderr:
            line = line.rstrip("\n")
            if self.verbose and line:
                # ikatago prints connection / queue status here.
                print(f"[ikatago] {line}")

    def _wait_until_ready(self):
        """Poll `name` until the engine answers, meaning the cloud is connected."""
        deadline = time.time() + self.ready_timeout
        last_err = None
        while time.time() < deadline:
            try:
                resp = self.send("name", timeout=10)
                if resp:  # non-empty payload means the engine actually answered
                    if self.verbose:
                        print(f"[engine] ready ({resp})")
                    return
            except GtpError as e:
                last_err = e
            time.sleep(2)
        raise GtpError(f"engine did not become ready in {self.ready_timeout}s "
                       f"(last error: {last_err})")

    def close(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.send("quit", timeout=5)
            except Exception:
                pass
            try:
                self.proc.terminate()
            except Exception:
                pass

    # ---- GTP plumbing ------------------------------------------------------
    def _drain_pending(self):
        while True:
            try:
                self._stdout_q.get_nowait()
            except queue.Empty:
                return

    def send(self, command, timeout=30):
        """Send a plain GTP command and return its response payload (str).

        Raises GtpError on a '?' response or timeout.
        """
        if self.proc is None or self.proc.poll() is not None:
            raise GtpError("engine process is not running")
        self._drain_pending()
        self.proc.stdin.write(command + "\n")
        self.proc.stdin.flush()

        lines = []
        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                line = self._stdout_q.get(timeout=remaining)
            except queue.Empty:
                break
            if line is None:
                raise GtpError("engine stdout closed unexpectedly")
            if line == "" and lines:
                # blank line terminates a GTP response
                break
            if line.startswith("=") or line.startswith("?"):
                status_ok = line.startswith("=")
                payload = line[1:].strip()
                # response id may precede; strip a leading number
                if payload[:1].isdigit():
                    parts = payload.split(None, 1)
                    payload = parts[1] if len(parts) > 1 else ""
                lines.append(payload)
                if not status_ok:
                    raise GtpError(f"GTP error for '{command}': {payload}")
                # peek: some responses are single line; the terminating blank
                # line will break the loop on next iteration.
                # Continue reading until blank line / timeout for multi-line.
                # We rely on the blank-line break above.
            elif lines:
                lines.append(line)
        return "\n".join(lines).strip()

    # ---- analysis ----------------------------------------------------------
    def analyze(self, max_visits=300, max_time=12.0, interval_cs=30):
        """Run kata-analyze at the current position and return parsed candidates.

        Returns a list of dicts (best first):
          {move, visits, winrate, scoreLead, order, prior}
        winrate/scoreLead are from the perspective of the side to move.
        """
        if self.proc is None or self.proc.poll() is not None:
            raise GtpError("engine process is not running")
        self._drain_pending()
        cmd = f"kata-analyze interval {interval_cs}"
        self.proc.stdin.write(cmd + "\n")
        self.proc.stdin.flush()

        best_line_infos = []
        best_top_visits = -1
        deadline = time.time() + max_time
        got_equals = False
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                line = self._stdout_q.get(timeout=remaining)
            except queue.Empty:
                break
            if line is None:
                raise GtpError("engine stdout closed during analysis")
            if line.startswith("="):
                got_equals = True
                continue
            if line.startswith("info "):
                infos = _parse_analyze_line(line)
                if infos:
                    top_visits = infos[0].get("visits", 0)
                    if top_visits > best_top_visits:
                        best_top_visits = top_visits
                        best_line_infos = infos
                    if top_visits >= max_visits:
                        break
        # Stop the (possibly still-running) analysis with a cheap command.
        try:
            self.send("name", timeout=10)
        except GtpError:
            pass
        return best_line_infos


    def analyze_with_ownership(self, max_visits=500, max_time=15.0,
                               interval_cs=30):
        """Like analyze(), but also asks KataGo for the per-point ownership map.

        Returns (infos, ownership):
          infos     -- same candidate dicts as analyze() (best first)
          ownership -- list of floats, length board_size**2, row-major from the
                       TOP-LEFT corner, in the *side-to-move* perspective
                       (positive = the side to move is expected to own it).
                       None if KataGo did not report ownership.
        """
        if self.proc is None or self.proc.poll() is not None:
            raise GtpError("engine process is not running")
        self._drain_pending()
        cmd = f"kata-analyze interval {interval_cs} ownership true"
        self.proc.stdin.write(cmd + "\n")
        self.proc.stdin.flush()

        best_infos, best_own, best_visits = [], None, -1
        deadline = time.time() + max_time
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                line = self._stdout_q.get(timeout=remaining)
            except queue.Empty:
                break
            if line is None:
                raise GtpError("engine stdout closed during analysis")
            if line.startswith("="):
                continue
            if line.startswith("?"):
                # Engine rejected the command (e.g. it doesn't support the
                # ownership keyword). Stop waiting; caller can fall back.
                if self.verbose:
                    print(f"[engine] kata-analyze rejected: {line}")
                break
            if line.startswith("info "):
                infos = _parse_analyze_line(line)
                if infos:
                    tv = infos[0].get("visits", 0)
                    if tv > best_visits:
                        best_visits = tv
                        best_infos = infos
                        own = _parse_ownership(line)
                        if own is not None:
                            best_own = own
                    if tv >= max_visits:
                        break
        try:
            self.send("name", timeout=10)
        except GtpError:
            pass
        return best_infos, best_own


def _parse_ownership(line):
    """Pull the ownership float list out of a kata-analyze line.

    The `ownership ...` block is appended at the end of the line after all the
    `info` chunks, so we take every float following the keyword.
    """
    idx = line.find(" ownership ")
    if idx < 0:
        return None
    vals = []
    for tok in line[idx + len(" ownership "):].split():
        try:
            vals.append(float(tok))
        except ValueError:
            break
    return vals or None


def _parse_analyze_line(line):
    """Parse one kata-analyze 'info ...' line into a list of candidate dicts.

    Example tokens:
      info move Q16 visits 120 winrate 0.5213 scoreMean 1.1 scoreStdev 12.0
           scoreLead 1.1 prior 0.08 order 0 pv Q16 D4 ... info move ...
    """
    candidates = []
    # Split into separate 'info ...' chunks (kata reports many moves per line).
    chunks = re.split(r"(?=\binfo\b)", line)
    for chunk in chunks:
        toks = chunk.split()
        if not toks or toks[0] != "info":
            continue
        d = {}
        i = 1
        while i < len(toks):
            key = toks[i]
            if key == "pv":
                # rest is the principal variation; stop here
                d["pv"] = toks[i + 1:]
                break
            if i + 1 >= len(toks):
                break
            val = toks[i + 1]
            if key == "move":
                d["move"] = val
            elif key in ("visits", "order"):
                try:
                    d[key] = int(val)
                except ValueError:
                    d[key] = 0
            elif key in ("winrate", "scoreLead", "scoreMean",
                         "scoreStdev", "prior", "lcb", "utility",
                         "utilityLcb", "weight"):
                try:
                    d[key] = float(val)
                except ValueError:
                    pass
            i += 2
        if "move" in d:
            candidates.append(d)
    candidates.sort(key=lambda c: c.get("order", 999))
    return candidates
