"""The Working Desktop server.

Security, since this endpoint starts processes:

* It binds to 127.0.0.1 only -- nothing off this machine can reach it.
* **The browser never sends a command.** It sends an app id, and the id is
  looked up in apps.json. There is no code path that executes a string from a
  request, so the worst a malicious page could do is start an app you had
  already listed yourself.
* Launch/stop are POST and are rejected when the request carries a foreign
  Origin, so a random website you visit cannot quietly poke this port.
"""

import os
import sys
import json
import errno
import argparse
import threading
import webbrowser
import urllib.request
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from workdesk import page, procs          # noqa: E402
from workdesk.procs import load_apps      # noqa: E402


class Handler(BaseHTTPRequestHandler):
    server_version = "WorkingDesktop"

    # -- plumbing ---------------------------------------------------------
    def log_message(self, fmt, *args):
        pass                              # keep the terminal readable

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass                          # the tab went away; not an error

    def _json(self, code, obj):
        self._send(code, json.dumps(obj), "application/json; charset=utf-8")

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, OSError):
            return {}

    def _same_origin(self):
        """Reject cross-site POSTs. A page you visit can send a POST to
        localhost; it cannot forge an Origin header."""
        origin = self.headers.get("Origin")
        if not origin:
            return True                   # curl / same-origin form posts
        host = self.headers.get("Host") or ""
        return urlparse(origin).netloc == host

    def _app(self, app_id):
        _, apps = load_apps(self.server.config_path)
        return next((a for a in apps if a["id"] == app_id), None)

    # -- routes -----------------------------------------------------------
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            cfg, apps = load_apps(self.server.config_path)
            self._send(200, page.build_html(apps, self.server.config_path))
            return
        if u.path == "/api/status":
            _, apps = load_apps(self.server.config_path)
            self._json(200, {"apps": [procs.status(a) for a in apps]})
            return
        if u.path == "/api/log":
            app_id = (parse_qs(u.query).get("id", [""])[0] or "").strip()
            if not self._app(app_id):
                self._json(404, {"error": "unknown app"})
                return
            self._json(200, {"text": procs.tail_log(app_id)})
            return
        self._send(404, "not found", "text/plain; charset=utf-8")

    def do_POST(self):
        u = urlparse(self.path)
        if u.path not in ("/api/launch", "/api/stop", "/api/run"):
            self._send(404, "not found", "text/plain; charset=utf-8")
            return
        if not self._same_origin():
            self._json(403, {"ok": False, "message": "Cross-origin request refused."})
            return
        app_id = str(self._body().get("id") or "").strip()
        app = self._app(app_id)           # <- the only source of commands
        if not app:
            self._json(404, {"ok": False, "message": "Unknown app."})
            return

        # Actions and apps are not interchangeable: starting an action detached
        # would throw away the result, and stopping one has nothing to aim at.
        action = procs.is_action(app)
        if u.path == "/api/run":
            if not action:
                self._json(400, {"ok": False, "message": "Not an action."})
                return
            fn = procs.run_action
        elif action:
            self._json(400, {"ok": False, "message": "This is an action -- use Run."})
            return
        else:
            fn = procs.start if u.path == "/api/launch" else procs.stop

        ok, message = fn(app)
        self._json(200, {"ok": ok, "message": message})


def _is_workdesk(url, timeout=1.5):
    """Is the thing already holding our port another Working Desktop?

    Checked before pointing a browser at it, so a stray unrelated server does
    not get presented to you as your launcher.
    """
    try:
        with urllib.request.urlopen(url + "api/status", timeout=timeout) as r:
            return isinstance(json.loads(r.read().decode()).get("apps"), list)
    except Exception:                      # noqa: BLE001 -- any failure means "no"
        return False


class QuietServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Working Desktop - launch your apps")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--config", default=os.path.join(HERE, "apps.json"))
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)

    try:
        cfg, apps = load_apps(args.config)
    except FileNotFoundError:
        raise SystemExit(f"No config at {args.config}")
    except ValueError as e:
        raise SystemExit(f"{args.config} is not valid JSON: {e}")

    port = args.port or int(cfg.get("port") or 8600)
    url = f"http://{args.host}:{port}/"

    try:
        httpd = QuietServer((args.host, port), Handler)
    except OSError as e:
        if e.errno != errno.EADDRINUSE:
            raise
        # Almost always a launcher from an earlier session that outlived its
        # Terminal window. Reuse it rather than dying with a traceback.
        if _is_workdesk(url):
            print(f"Working Desktop is already running at {url} -- opening it.")
            if not args.no_browser:
                webbrowser.open(url)
            return 0
        raise SystemExit(
            f"Port {port} is busy, but it is not the Working Desktop.\n"
            f"Something else is using it. Free that port, or start on another:\n"
            f"    python3 -m workdesk --port {port + 1}")

    httpd.config_path = args.config

    print(f"Working Desktop: {url}")
    print(f"{len(apps)} apps from {args.config}")
    print("Close this window to stop the launcher "
          "(apps you started keep running).")
    if not args.no_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        httpd.shutdown()


if __name__ == "__main__":
    main()
