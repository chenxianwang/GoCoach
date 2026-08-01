#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mirror of Go - KataGo game review, desktop GUI.

Enter a numeric Fox UID -> download the most recent N games (deduplicated) ->
set the analysis options -> analyse and build the report in one click.
Analysis depends on the local ikatago client (cloud KataGo), so run this on the Mac
where ikatago can log in.

Launch by double-clicking "Mirror of Go.command" in the repo root, or:
    python3 go_review/fox_review_app.py
"""

import os
import sys
import queue
import threading
import traceback
import webbrowser

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import pipeline  # noqa: E402
import import_lizzie  # noqa: E402


# ---------------------------------------------------------------------------
# Redirect print from worker threads into the log box (thread-safe: push to a
# queue, poll from the main thread)
# ---------------------------------------------------------------------------
class _QueueWriter:
    def __init__(self, q):
        self.q = q

    def write(self, s):
        if s:
            self.q.put(s)

    def flush(self):
        pass


class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.report_path = None
        self.busy = False

        root.title("Mirror of Go - KataGo Review")
        root.geometry("760x820")
        root.minsize(680, 680)
        self._imp_files = []   # selected analysed SGF paths (files or one folder)

        cfg = self._safe_load_cfg()

        pad = {"padx": 8, "pady": 4}
        frm = ttk.Frame(root, padding=12)
        frm.pack(fill="both", expand=True)

        # ---- title ----
        ttk.Label(frm, text="Mirror of Go - KataGo Review",
                  font=("PingFang SC", 18, "bold")).grid(row=0, column=0,
                  columnspan=4, sticky="w", pady=(0, 2))
        ttk.Label(frm, text="Enter a Fox UID -> download recent games -> review with KataGo",
                  foreground="#666").grid(row=1, column=0, columnspan=4,
                  sticky="w", pady=(0, 10))

        # ---- game source ----
        box1 = ttk.LabelFrame(frm, text="Game source", padding=10)
        box1.grid(row=2, column=0, columnspan=4, sticky="ew", **pad)
        box1.columnconfigure(1, weight=1)

        self.source = tk.StringVar(value="fox")
        ttk.Radiobutton(box1, text="Download by Fox UID", value="fox",
                        variable=self.source,
                        command=self._sync_source).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(box1, text="Local SGF folder (already downloaded)", value="local",
                        variable=self.source,
                        command=self._sync_source).grid(row=0, column=1,
                        columnspan=2, sticky="w")

        # Fox UID row
        self.lbl_uid = ttk.Label(box1, text="Fox UID (digits only)")
        self.lbl_uid.grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.uid = tk.StringVar()
        self.ent_uid = ttk.Entry(box1, textvariable=self.uid)
        self.ent_uid.grid(row=1, column=1, columnspan=2, sticky="ew", padx=6, pady=(8, 0))

        self.lbl_dl = ttk.Label(box1, text="Recent games to download")
        self.lbl_dl.grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.dl = tk.IntVar(value=100)
        self.spn_dl = ttk.Spinbox(box1, from_=1, to=500, textvariable=self.dl, width=8)
        self.spn_dl.grid(row=2, column=1, sticky="w", padx=6, pady=(6, 0))
        ttk.Label(box1, text="(games already downloaded are skipped)",
                  foreground="#888").grid(row=2, column=2, sticky="w", pady=(6, 0))

        # local folder row
        self.lbl_dir = ttk.Label(box1, text="Local SGF folder")
        self.lbl_dir.grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.local_dir = tk.StringVar()
        self.ent_dir = ttk.Entry(box1, textvariable=self.local_dir)
        self.ent_dir.grid(row=3, column=1, sticky="ew", padx=6, pady=(6, 0))
        self.btn_browse = ttk.Button(box1, text="Browse...", command=self._pick_dir)
        self.btn_browse.grid(row=3, column=2, sticky="w", padx=6, pady=(6, 0))

        # nickname (used by both sources; blank means auto-detect)
        ttk.Label(box1, text="Your nickname").grid(row=4, column=0, sticky="w", pady=(6, 0))
        self.nick = tk.StringVar()
        ttk.Entry(box1, textvariable=self.nick).grid(row=4, column=1,
                  sticky="ew", padx=6, pady=(6, 0))
        ttk.Label(box1, text="(leave blank to auto-detect)",
                  foreground="#888").grid(row=4, column=2, sticky="w", pady=(6, 0))

        self._sync_source()

        # ---- analysis options ----
        box2 = ttk.LabelFrame(frm, text="Analysis options", padding=10)
        box2.grid(row=3, column=0, columnspan=4, sticky="ew", **pad)
        for c in (1, 3):
            box2.columnconfigure(c, weight=1)

        ttk.Label(box2, text="Games to analyse").grid(row=0, column=0, sticky="w")
        self.ng = tk.IntVar(value=int(cfg.get("num_games", 10)))
        ttk.Spinbox(box2, from_=1, to=200, textvariable=self.ng, width=8).grid(
            row=0, column=1, sticky="w", padx=6)

        ttk.Label(box2, text="Visits per move").grid(row=0, column=2, sticky="w")
        self.visits = tk.IntVar(value=int(cfg.get("max_visits", 300)))
        ttk.Spinbox(box2, from_=50, to=5000, increment=50,
                    textvariable=self.visits, width=8).grid(
            row=0, column=3, sticky="w", padx=6)

        ttk.Label(box2, text="Max seconds per move").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.mtime = tk.DoubleVar(value=float(cfg.get("max_time_per_move", 1.0)))
        ttk.Spinbox(box2, from_=0.2, to=30, increment=0.5,
                    textvariable=self.mtime, width=8).grid(
            row=1, column=1, sticky="w", padx=6, pady=(6, 0))

        ttk.Label(box2, text="Mistake threshold (pts)").grid(row=1, column=2, sticky="w", pady=(6, 0))
        self.mth = tk.DoubleVar(value=float(cfg.get("mistake_threshold", 2.0)))
        ttk.Spinbox(box2, from_=0.5, to=20, increment=0.5,
                    textvariable=self.mth, width=8).grid(
            row=1, column=3, sticky="w", padx=6, pady=(6, 0))

        ttk.Label(box2, text="Blunder threshold (pts)").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.bth = tk.DoubleVar(value=float(cfg.get("blunder_threshold", 6.0)))
        ttk.Spinbox(box2, from_=2, to=40, increment=1,
                    textvariable=self.bth, width=8).grid(
            row=2, column=1, sticky="w", padx=6, pady=(6, 0))

        self.force = tk.BooleanVar(value=False)
        ttk.Checkbutton(box2, text="Re-analyse everything (including games already done)",
                        variable=self.force).grid(row=2, column=2,
                        columnspan=2, sticky="w", pady=(6, 0))

        # ---- buttons ----
        box3 = ttk.Frame(frm)
        box3.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(4, 4))
        self.btn_all = ttk.Button(box3, text="1. Download + analyse + report",
                                  command=self.on_all)
        self.btn_all.pack(side="left", padx=4)
        self.btn_dl = ttk.Button(box3, text="Download only", command=self.on_download)
        self.btn_dl.pack(side="left", padx=4)
        self.btn_an = ttk.Button(box3, text="Analyse + report only", command=self.on_analyze)
        self.btn_an.pack(side="left", padx=4)
        self.btn_open = ttk.Button(box3, text="Open report", command=self.on_open,
                                   state="disabled")
        self.btn_open.pack(side="left", padx=4)

        # ---- import analysed games (SGF analysed by LizzieYZY) ----
        box4 = ttk.LabelFrame(frm, text="Import analysed games (SGF analysed by LizzieYZY)",
                              padding=10)
        box4.grid(row=5, column=0, columnspan=4, sticky="ew", **pad)
        box4.columnconfigure(1, weight=1)

        ttk.Label(box4, text="Analysed SGF").grid(row=0, column=0, sticky="w")
        self.imp_src = tk.StringVar()
        self.ent_imp = ttk.Entry(box4, textvariable=self.imp_src)
        self.ent_imp.grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(box4, text="Choose files...",
                   command=self._pick_imp_files).grid(row=0, column=2, padx=2)
        ttk.Button(box4, text="Choose folder...",
                   command=self._pick_imp_dir).grid(row=0, column=3, padx=2)

        ttk.Label(box4, text="Import into report").grid(row=1, column=0, sticky="w",
                                              pady=(8, 0))
        self.imp_target = tk.StringVar()
        self.cmb_target = ttk.Combobox(box4, textvariable=self.imp_target,
                                       values=self._report_choices())
        self.cmb_target.grid(row=1, column=1, sticky="ew", padx=6, pady=(8, 0))
        ttk.Button(box4, text="Browse / new...",
                   command=self._pick_target).grid(row=1, column=2, padx=2,
                   pady=(8, 0))
        ttk.Label(box4, text="(pick an existing report, or type a new folder name)",
                  foreground="#888").grid(row=1, column=3, sticky="w",
                  pady=(8, 0))

        ttk.Label(box4, text="Review subject nickname").grid(row=2, column=0, sticky="w",
                                            pady=(6, 0))
        self.imp_subject = tk.StringVar()
        ttk.Entry(box4, textvariable=self.imp_subject).grid(row=2, column=1,
                  sticky="ew", padx=6, pady=(6, 0))
        ttk.Label(box4, text="(blank = auto-detect from the Fox nickname; falls back to Black)",
                  foreground="#888").grid(row=2, column=2, columnspan=2,
                  sticky="w", pady=(6, 0))

        ttk.Label(box4, text="On duplicate games").grid(row=3, column=0, sticky="w",
                                            pady=(6, 0))
        self.imp_dup = tk.StringVar(value="Skip")
        ttk.Combobox(box4, textvariable=self.imp_dup, width=8, state="readonly",
                     values=["Skip", "Overwrite"]).grid(row=3, column=1, sticky="w",
                     padx=6, pady=(6, 0))
        self.btn_imp = ttk.Button(box4, text="2. Import and update the report",
                                  command=self.on_import)
        self.btn_imp.grid(row=3, column=2, columnspan=2, sticky="e",
                          padx=2, pady=(6, 0))

        # ---- progress + log ----
        self.prog = ttk.Progressbar(frm, mode="indeterminate")
        self.prog.grid(row=6, column=0, columnspan=4, sticky="ew", padx=8, pady=(4, 2))

        logbox = ttk.LabelFrame(frm, text="Run log", padding=6)
        logbox.grid(row=7, column=0, columnspan=4, sticky="nsew", **pad)
        frm.rowconfigure(7, weight=1)
        frm.columnconfigure(0, weight=1)
        self.log = tk.Text(logbox, height=12, wrap="word", font=("Menlo", 11))
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(logbox, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=sb.set, state="disabled")

        self._println("Ready. Enter your Fox UID and press the one-click button.\n"
                      "Note: analysis uses the local ikatago client (cloud KataGo) "
                      "-- make sure it can log in.")
        self.root.after(120, self._drain)

    # ---- source switching ----
    def _sync_source(self):
        local = self.source.get() == "local"
        fox_state = "disabled" if local else "normal"
        local_state = "normal" if local else "disabled"
        for w in (self.ent_uid, self.spn_dl):
            w.configure(state=fox_state)
        for w in (self.ent_dir, self.btn_browse):
            w.configure(state=local_state)
        # "Download only" only makes sense in Fox mode; the one-click button's
        # label follows the selected source.
        if hasattr(self, "btn_dl"):
            self.btn_dl.configure(state=fox_state)
        if hasattr(self, "btn_all"):
            self.btn_all.configure(
                text="1. Analyse + report" if local
                else "1. Download + analyse + report")

    def _pick_dir(self):
        d = filedialog.askdirectory(title="Choose the folder holding your SGF games")
        if d:
            self.local_dir.set(d)

    # ---- import: choose source / target ----
    def _report_choices(self):
        """Existing report folders (shown relative to go_review) for the
        "Import into report" dropdown."""
        out = []
        for d in import_lizzie.list_report_dirs(HERE):
            rel = os.path.relpath(d, HERE)
            out.append(rel)
        return out

    def _pick_imp_files(self):
        fs = filedialog.askopenfilenames(
            title="Choose the SGF files LizzieYZY analysed",
            filetypes=[("SGF games", "*.sgf"), ("All files", "*.*")])
        if fs:
            self._imp_files = list(fs)
            self.imp_src.set(f"{len(fs)} files" if len(fs) > 1 else fs[0])

    def _pick_imp_dir(self):
        d = filedialog.askdirectory(title="Choose the folder holding the analysed SGFs")
        if d:
            self._imp_files = [d]
            self.imp_src.set(d)

    def _pick_target(self):
        d = filedialog.askdirectory(title="Choose or create the target report folder")
        if d:
            # If it sits inside go_review, show a relative path for readability
            try:
                rel = os.path.relpath(d, HERE)
                self.imp_target.set(rel if not rel.startswith("..") else d)
            except ValueError:
                self.imp_target.set(d)

    # ---- helpers ----
    def _safe_load_cfg(self):
        try:
            return pipeline.load_config()
        except Exception:
            return {}

    def _println(self, s):
        self.log.configure(state="normal")
        self.log.insert("end", s.rstrip("\n") + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _drain(self):
        try:
            while True:
                s = self.q.get_nowait()
                self.log.configure(state="normal")
                self.log.insert("end", s)
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(120, self._drain)

    def _set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for b in (self.btn_all, self.btn_dl, self.btn_an, self.btn_imp):
            b.configure(state=state)
        if busy:
            self.prog.start(12)
        else:
            self.prog.stop()

    def _valid_uid(self):
        uid = self.uid.get().strip()
        if not uid.isdigit():
            messagebox.showerror("Invalid UID",
                                 "Enter a Fox UID made of digits only, e.g. 531169471")
            return None
        return uid

    def _valid_source(self):
        """Validate the source inputs; returns dict(source, uid, local_dir) or None."""
        if self.source.get() == "local":
            d = self.local_dir.get().strip()
            if not d or not os.path.isdir(d):
                messagebox.showerror("Invalid folder",
                                     "Choose a local SGF folder that exists.")
                return None
            return {"source": "local", "uid": None, "local_dir": d}
        uid = self._valid_uid()
        if not uid:
            return None
        return {"source": "fox", "uid": uid, "local_dir": None}

    # ---- run (worker thread) ----
    def _run(self, fn):
        if self.busy:
            return
        self._set_busy(True)

        def worker():
            old_out, old_err = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = _QueueWriter(self.q)
            ok = True
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                ok = False
                self.q.put(f"\n[error] {type(e).__name__}: {e}\n")
                self.q.put(traceback.format_exc())
            finally:
                sys.stdout, sys.stderr = old_out, old_err
                self.root.after(0, lambda: self._done(ok))

        threading.Thread(target=worker, daemon=True).start()

    def _done(self, ok):
        self._set_busy(False)
        if self.report_path and os.path.exists(self.report_path):
            self.btn_open.configure(state="normal")
        if ok:
            self._println("Done.")

    # ---- button callbacks ----
    def on_download(self):
        uid = self._valid_uid()
        if not uid:
            return

        def task():
            res = pipeline.download_recent(uid, limit=self.dl.get())
            nick = pipeline.detect_nickname(res["metas"])
            if nick:
                print(f"Detected nickname: {nick}")
        self._run(task)

    def on_analyze(self):
        src = self._valid_source()
        if not src:
            return

        def task():
            self.report_path = pipeline.full_pipeline(
                uid=src["uid"], source=src["source"], local_dir=src["local_dir"],
                user_name=self.nick.get(), num_games=self.ng.get(),
                max_visits=self.visits.get(), max_time=self.mtime.get(),
                mistake_th=self.mth.get(), blunder_th=self.bth.get(),
                force=self.force.get(), do_download=False, do_analyze=True)
        self._run(task)

    def on_all(self):
        src = self._valid_source()
        if not src:
            return
        # Local mode has no download step
        do_dl = src["source"] == "fox"

        def task():
            self.report_path = pipeline.full_pipeline(
                uid=src["uid"], source=src["source"], local_dir=src["local_dir"],
                user_name=self.nick.get(), download_limit=self.dl.get(),
                num_games=self.ng.get(), max_visits=self.visits.get(),
                max_time=self.mtime.get(), mistake_th=self.mth.get(),
                blunder_th=self.bth.get(), force=self.force.get(),
                do_download=do_dl, do_analyze=True)
        self._run(task)

    def on_import(self):
        if not self._imp_files:
            messagebox.showerror("No games selected",
                                 "Use \"Choose files...\" or \"Choose folder...\" to "
                                 "pick the analysed SGFs first.")
            return
        target = self.imp_target.get().strip()
        if not target:
            messagebox.showerror("No target report",
                                 "Pick an existing report under \"Import into report\", "
                                 "or type a new folder name.")
            return
        # Relative paths resolve against go_review; absolute paths are used as-is
        target_dir = target if os.path.isabs(target) else os.path.join(HERE, target)
        if not os.path.isdir(target_dir):
            if not messagebox.askyesno("Create report",
                    f"The target folder does not exist. Create it?\n{target_dir}"):
                return
        on_dup = "overwrite" if self.imp_dup.get() == "Overwrite" else "skip"
        subject = self.imp_subject.get().strip() or None
        paths = list(self._imp_files)
        cfg = self._safe_load_cfg()

        def task():
            n, rp = import_lizzie.run_import(
                paths, target_dir, cfg, subject_name=subject,
                on_dup=on_dup, rebuild=True, log=print)
            if rp:
                self.report_path = rp
            # Refresh the target dropdown so the new report is selectable next time
            self.root.after(0, lambda: self.cmb_target.configure(
                values=self._report_choices()))
        self._run(task)

    def on_open(self):
        if self.report_path and os.path.exists(self.report_path):
            webbrowser.open("file://" + os.path.abspath(self.report_path))
        else:
            messagebox.showinfo("No report yet", "Run an analysis to build a report first.")


def _set_app_icon(root):
    """Give the window/Dock an icon when launched via the .command (i.e. not
    from the .app bundle). Best-effort: silently ignore anything unavailable."""
    png = os.path.join(HERE, "appicon.png")
    # 1) Tk window icon (works cross-platform; titlebar / app switcher).
    try:
        if os.path.exists(png):
            img = tk.PhotoImage(file=png)
            root.iconphoto(True, img)
            root._icon_ref = img  # keep a reference so it isn't GC'd
    except Exception:
        pass
    # 2) macOS Dock icon via Cocoa, if pyobjc happens to be installed.
    try:
        if sys.platform == "darwin" and os.path.exists(png):
            from AppKit import NSApplication, NSImage  # type: ignore
            ns = NSImage.alloc().initByReferencingFile_(png)
            if ns is not None:
                NSApplication.sharedApplication().setApplicationIconImage_(ns)
    except Exception:
        pass


def main():
    root = tk.Tk()
    _set_app_icon(root)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
