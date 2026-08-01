"""Background job bookkeeping for the one-at-a-time analyse/import task."""

import sys
import threading
import traceback


# ---------------------------------------------------------------------------
# Background jobs: only one at a time (analysis is heavy and shares config).
# Log output is collected in chunks and polled by the front end.
# ---------------------------------------------------------------------------

class Job:
    def __init__(self, jid):
        self.id = jid
        self.chunks = []          # list[str] -- captured print output
        self.done = False
        self.ok = False
        self.report = None        # report to jump to when done (path relative to HERE)
        self.lock = threading.Lock()

    def write(self, s):
        if not s:
            return
        with self.lock:
            self.chunks.append(s)

    def flush(self):
        pass

    def snapshot(self, since):
        with self.lock:
            n = len(self.chunks)
            text = "".join(self.chunks[since:]) if since < n else ""
            return text, n, self.done, self.ok, self.report


class JobManager:
    def __init__(self):
        self._jobs = {}
        self._busy = False
        self._lock = threading.Lock()
        self._seq = 0

    def busy(self):
        with self._lock:
            return self._busy

    def get(self, jid):
        return self._jobs.get(jid)

    def start(self, fn):
        """fn(job) runs in a worker thread with stdout/stderr redirected to it.
        Returns (job_id, None) or (None, reason) if another job is running."""
        with self._lock:
            if self._busy:
                return None, "A job is already running -- please wait for it to finish."
            self._busy = True
            self._seq += 1
            jid = f"job{self._seq}"
            job = Job(jid)
            self._jobs[jid] = job

        def worker():
            old_out, old_err = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = job
            try:
                fn(job)
                job.ok = True
            except Exception as e:  # noqa: BLE001
                job.write(f"\n[error] {type(e).__name__}: {e}\n")
                job.write(traceback.format_exc())
                job.ok = False
            finally:
                sys.stdout, sys.stderr = old_out, old_err
                job.done = True
                with self._lock:
                    self._busy = False

        threading.Thread(target=worker, daemon=True).start()
        return jid, None


JOBS = JobManager()
