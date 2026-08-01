"""Quiet error handling for dropped connections, and the CLI entry point."""

import os
import sys
import threading
import argparse
import webbrowser
from http.server import ThreadingHTTPServer

import import_lizzie    # noqa: E402

from .paths import HERE
from .static_export import write_static_index
from .config_jobs import _safe_cfg
from .handler import Handler


class QuietServer(ThreadingHTTPServer):
    """A browser that navigates away mid-request leaves the socket dead.  That
    is normal, not a fault, so keep the 25-line traceback out of the terminal;
    anything else still gets reported in full."""

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


def main():
    ap = argparse.ArgumentParser(description="Mirror of Go - local web app")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--export-static", action="store_true",
                    help="Write the offline viewer index.html and exit; do not start the server.")
    ap.add_argument("--rebuild-reports", action="store_true",
                    help="Regenerate every review_report.html from the per-game "
                         "JSON, then exit. Use this after restoring a backup.")
    args = ap.parse_args()

    if args.rebuild_reports:
        gd = _safe_cfg().get("games_dirs", [])
        dirs = import_lizzie.list_report_dirs(HERE)
        if not dirs:
            print("No report folders found next to web_app.py.")
            return
        for d in dirs:
            rel = os.path.relpath(d, HERE)
            try:
                out = import_lizzie.rebuild_report(d, gd)
                print(f"  rebuilt {rel}" if out else f"  {rel}: no games, skipped")
            except Exception as e:                # noqa: BLE001
                print(f"  {rel}: FAILED — {type(e).__name__}: {e}")
        path = write_static_index()
        print(f"Offline viewer written: {path}" if path else "")
        print("Done. Start the app with: python3 go_review/web_app.py")
        return

    if args.export_static:
        path = write_static_index()
        print(f"Offline viewer written: {path}" if path else "Failed to write it.")
        return

    # Refresh the offline viewer on every start, so index.html still works after
    # the terminal is closed.
    static_path = write_static_index()

    httpd = QuietServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Mirror of Go is running: {url}")
    if static_path:
        print(f"Offline viewer (works after you close the terminal): {static_path}")
    print("Close this window to stop the server.")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        httpd.shutdown()
