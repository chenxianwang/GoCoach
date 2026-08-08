"""The HTTP request handler: routes every GET/POST to the functions above."""

import os
import json
import datetime
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler

import import_lizzie    # noqa: E402

from .jobs import JOBS
from .listing import list_games_dirs, list_reports, report_dir_from_rel
from .shell import analyze_page, dashboard_page
from .compare import compare_page
from .pages_misc import prompt_page, summary_page, terms_page
from .tsumego_page import do_tsumego_hide, do_tsumego_refresh, tsumego_page
from .report_serve import render_report
from .config_jobs import _safe_cfg, do_analyze, do_import, set_default_config
from .board_api import render_board_svg
from .voice import _PROGRESS, browse_dirs, set_voice_audio_dir, transcribe_audio
from .state import add_practice_hidden, load_notes, load_practice_hidden, load_voice, save_note, save_voice, set_all_hidden
from .summary_engine import (_md_to_html, build_review_summary, export_summaries_md,
                             load_summary, load_summary_system, save_summary_system,
                             summary_history_html, summary_system_is_custom)
from .backup import build_backup_zip, delete_report


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "YimuyijingWeb/2.0"

    def log_message(self, *a):
        pass  # stay quiet

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        # The whole write is guarded, headers included: a slow request (the
        # DeepSeek summary takes 20-60s) can outlive the tab that asked for it,
        # and then even flushing the status line raises BrokenPipeError.  The
        # work itself is already done and saved by this point, so a vanished
        # client is nothing to report.
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            # Never let the browser serve a stale dashboard/report/API response
            # — the data changes whenever a game is analysed, imported, deleted.
            self.send_header("Cache-Control", "no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            print("  (client closed the connection before the reply was sent "
                  "— the work was still completed and saved)")

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False),
                   "application/json; charset=utf-8")

    def _read_json(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n <= 0:
            return {}
        raw = self.rfile.read(n)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        u = urlparse(self.path)
        path = u.path
        if path == "/":
            self._send(200, dashboard_page())
            return
        embed = (parse_qs(u.query).get("embed", ["0"])[0] == "1")
        if path == "/analyze":
            self._send(200, analyze_page(embed=embed))
            return
        if path == "/compare":
            q = parse_qs(u.query)
            a = (q.get("a", [""])[0] or "").strip()
            b = (q.get("b", [""])[0] or "").strip()
            self._send(200, compare_page(a or None, b or None, embed=embed))
            return
        if path == "/summary":
            rel = (parse_qs(u.query).get("report", [""])[0] or "").strip()
            self._send(200, summary_page(rel or None, embed=embed))
            return
        if path == "/prompt":
            rel = (parse_qs(u.query).get("report", [""])[0] or "").strip()
            self._send(200, prompt_page(rel or None, embed=embed))
            return
        if path == "/terms":
            self._send(200, terms_page(embed=embed))
            return
        if path == "/tsumego":
            self._send(200, tsumego_page(embed=embed))
            return
        if path.startswith("/r/"):
            rel = path[len("/r/"):]
            doc = render_report(rel, embed=embed)
            if doc is None:
                self._send(404, "<h1>Report not found</h1>"
                                "<p><a href='/'>&larr; Back to dashboard</a></p>")
            else:
                self._send(200, doc)
            return
        if path == "/api/reports":
            self._json(200, {"reports": list_reports()})
            return
        if path == "/api/games_dirs":
            self._json(200, {"dirs": list_games_dirs()})
            return
        if path == "/api/notes":
            rel = (parse_qs(u.query).get("report", [""])[0] or "").strip()
            self._json(200, {"notes": load_notes(rel)})
            return
        if path == "/api/practice_hidden":
            rel = (parse_qs(u.query).get("report", [""])[0] or "").strip()
            self._json(200, {"hidden": load_practice_hidden(rel)})
            return
        if path == "/api/voice":
            rel = (parse_qs(u.query).get("report", [""])[0] or "").strip()
            self._json(200, {"text": load_voice(rel)})
            return
        if path == "/api/prompt":
            self._json(200, {"prompt": load_summary_system(),
                             "custom": summary_system_is_custom()})
            return
        if path == "/api/voice_dir":
            self._json(200, browse_dirs(
                (parse_qs(u.query).get("path", [""])[0] or "").strip()))
            return
        if path == "/api/transcribe_progress":
            self._json(200, dict(_PROGRESS))
            return
        if path == "/api/backup":
            data, n, raw = build_backup_zip()
            name = f"go-review-backup-{datetime.date.today().isoformat()}.zip"
            print(f"Backup: {n} files, {raw/1024:.0f} KB -> "
                  f"{len(data)/1024:.0f} KB zipped ({name})", flush=True)
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition",
                                 f'attachment; filename="{name}"')
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        if path == "/api/summary":
            rel = (parse_qs(u.query).get("report", [""])[0] or "").strip()
            md = load_summary(rel)
            self._json(200, {"exists": bool(md), "md": md,
                             "html": _md_to_html(md) if md else "",
                             "history": summary_history_html(rel)})
            return
        if path == "/api/summary_export":
            rel = (parse_qs(u.query).get("report", [""])[0] or "").strip()
            if not report_dir_from_rel(rel):
                self._send(404, "report not found", "text/plain; charset=utf-8")
                return
            label = os.path.basename(rel.rstrip("/\\")) or "report"
            name = f"review-summaries-{label}-{datetime.date.today().isoformat()}.md"
            body = export_summaries_md(rel).encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/markdown; charset=utf-8")
                self.send_header("Content-Disposition",
                                 f'attachment; filename="{name}"')
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        if path == "/api/board":
            q = parse_qs(u.query)
            svg = render_board_svg((q.get("report", [""])[0] or "").strip(),
                                   (q.get("game", [""])[0] or "").strip(),
                                   (q.get("move", [""])[0] or "").strip())
            if svg:
                self._send(200, svg, "image/svg+xml; charset=utf-8")
            else:
                self._send(404, "<p>Position not found</p>")
            return
        if path.startswith("/api/job/"):
            jid = path[len("/api/job/"):]
            job = JOBS.get(jid)
            if not job:
                self._json(404, {"error": "no such job"})
                return
            since = int((parse_qs(u.query).get("since", ["0"])[0]) or 0)
            text, n, done, ok, report_rel = job.snapshot(since)
            self._json(200, {"text": text, "n": n, "done": done,
                             "ok": ok, "report": report_rel})
            return
        self._send(404, "not found", "text/plain; charset=utf-8")

    def do_POST(self):
        u = urlparse(self.path)
        path = u.path
        if path == "/api/analyze":
            body = self._read_json()
            jid, err = JOBS.start(lambda job: do_analyze(job, body))
            self._json(200 if jid else 409,
                       {"job": jid} if jid else {"error": err})
            return
        if path == "/api/import":
            body = self._read_json()
            jid, err = JOBS.start(lambda job: do_import(job, body))
            self._json(200 if jid else 409,
                       {"job": jid} if jid else {"error": err})
            return
        if path == "/api/tsumego_hide":
            ok, message = do_tsumego_hide(self._read_json())
            self._json(200 if ok else 400, {"ok": ok, "message": message})
            return
        if path == "/api/tsumego_refresh":
            body = self._read_json()
            jid, err = JOBS.start(lambda job: do_tsumego_refresh(job, body))
            self._json(200 if jid else 409,
                       {"job": jid} if jid else {"error": err})
            return
        if path == "/api/delete":
            body = self._read_json()
            ok, err = delete_report(body.get("rel", ""))
            self._json(200 if ok else 400,
                       {"ok": True} if ok else {"error": err})
            return
        if path == "/api/note":
            body = self._read_json()
            rel = (body.get("report") or "").strip()
            nid = (body.get("id") or "").strip()
            data = None if body.get("delete") else body.get("note")
            ok, err = save_note(rel, nid, data)
            self._json(200 if ok else 400,
                       {"ok": True} if ok else {"error": err})
            return
        if path == "/api/transcribe":
            n = int(self.headers.get("Content-Length", 0) or 0)
            data = self.rfile.read(n) if n > 0 else b""
            if not data:
                self._json(400, {"error": "No audio received."})
                return
            rel = (parse_qs(u.query).get("report", [""])[0] or "").strip()
            text, err, audio = transcribe_audio(data, rel)
            if text is None:
                self._json(500, {"error": err, "audio": audio})
                return
            self._json(200, {"text": text, "audio": audio})
            return
        if path == "/api/voice":
            body = self._read_json()
            rel = ((body or {}).get("report") or "").strip()
            ok, err = save_voice(rel, (body or {}).get("text") or "")
            self._json(200 if ok else 500,
                       {"ok": True} if ok else {"error": err})
            return
        if path == "/api/summary":
            body = self._read_json()
            rel = ((body or {}).get("report") or "").strip()
            text, err = build_review_summary(rel)
            if err:
                self._json(200, {"error": err})
                return
            self._json(200, {"html": _md_to_html(text), "md": text,
                             "history": summary_history_html(rel)})
            return
        if path == "/api/voice_dir":
            body = self._read_json() or {}
            info, err = set_voice_audio_dir(body.get("path") or "",
                                            create=bool(body.get("create")))
            self._json(200, {"error": err} if err else {"ok": True, **info})
            return
        if path == "/api/prompt":
            body = self._read_json() or {}
            # "reset" and an empty prompt mean the same thing to the store (drop
            # the override) -- but only an explicit reset may clear it, or a
            # cleared textarea would silently wipe a saved prompt on Save.
            text = "" if body.get("reset") else (body.get("prompt") or "")
            if not body.get("reset") and not text.strip():
                self._json(200, {"error": "The prompt cannot be empty. Use "
                                          "Restore built-in default instead."})
                return
            custom, err = save_summary_system(text)
            self._json(200, {"error": err} if err else
                       {"ok": True, "custom": custom,
                        "prompt": load_summary_system()})
            return
        if path == "/api/practice_clear":
            body = self._read_json() or {}
            rel = (body.get("report") or "").strip()
            clear = bool(body.get("clear"))
            rdir = report_dir_from_rel(rel)
            if not rdir:
                self._json(200, {"error": "Report not found."})
                return
            try:
                n = set_all_hidden(rel, clear)
            except Exception as e:  # noqa: BLE001
                self._json(200, {"error": f"{type(e).__name__}: {e}"})
                return
            try:
                import_lizzie.rebuild_report(rdir, _safe_cfg().get("games_dirs", []))
            except Exception as e:  # noqa: BLE001
                self._json(200, {"error": "The change was saved, but rebuilding the "
                                          "report failed: " + str(e)})
                return
            self._json(200, {"ok": True, "hidden": n})
            return
        if path == "/api/practice_hide":
            body = self._read_json()
            ok, err = add_practice_hidden((body.get("report") or "").strip(),
                                          (body.get("id") or "").strip())
            self._json(200 if ok else 400,
                       {"ok": True} if ok else {"error": err})
            return
        if path == "/api/set_default":
            body = self._read_json()
            kv = {}
            if "games_subdir" in body:
                kv["default_games_subdir"] = str(body.get("games_subdir") or "")
            if "import_target" in body:
                kv["default_import_target"] = str(body.get("import_target") or "")
            try:
                set_default_config(**kv)
                self._json(200, {"ok": True})
            except Exception as e:  # noqa: BLE001
                self._json(400, {"error": f"{type(e).__name__}: {e}"})
            return
        self._send(404, "not found", "text/plain; charset=utf-8")
