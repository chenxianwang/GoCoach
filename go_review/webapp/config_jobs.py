"""Config access, live code reload, and the analyse/import job runners."""

import os
import sys
import json
import tempfile

import pipeline       # noqa: E402
import import_lizzie  # noqa: E402

from .paths import HERE
from .static_export import write_static_index


# ---------------------------------------------------------------------------
# Job implementations
# ---------------------------------------------------------------------------

def _safe_cfg():
    try:
        return pipeline.load_config()
    except Exception:
        return {}


def _reload_app_modules():
    """Pick up on-disk code changes (report/*.py, import_lizzie.py, …) without
    restarting the long-running server.  importlib.reload updates each module
    in place, so existing references (web_app.report, import_lizzie.report, …)
    all see the new code.  Dependencies are reloaded before their dependents.

    `report` is a package: reloading `sys.modules["report"]` only re-runs
    `report/__init__.py`, which just re-imports names that are already cached
    in `sys.modules["report.<submodule>"]` -- so edits to report/board.py etc.
    would otherwise never be picked up.  Reload every report.* submodule first,
    in the same dependency order report/__init__.py imports them in, then the
    package itself so it re-binds its re-exports to the fresh submodules."""
    import importlib
    report_submodule_order = [
        "constants", "assets", "data", "board", "charts", "trends",
        "trajectory", "practice", "summary", "pages", "legacy", "core",
    ]
    report_submodules = [f"report.{n}" for n in report_submodule_order
                          if f"report.{n}" in sys.modules]
    for name in ("appconfig", "sgfparse", "estimate_score", "analyze",
                 *report_submodules, "report", "import_lizzie", "pipeline",
                 "go_terms"):
        mod = sys.modules.get(name)
        if mod is not None:
            try:
                importlib.reload(mod)
            except Exception as e:  # noqa: BLE001
                print(f"  ! could not reload {name} (ignored): {e}")


def _friendly_hint(e):
    """A human-friendly hint for common failure modes, shown above the traceback."""
    msg = f"{type(e).__name__}: {e}".lower()
    if "ikatago" in msg or "login" in msg or "ready" in msg:
        return ("Hint: analysis depends on the local ikatago client (cloud KataGo). "
                "Check that it is installed, can log in, and that ikatago_command in "
                "config.json is correct (or set the IKATAGO_USERNAME / "
                "IKATAGO_PASSWORD environment variables).")
    if "uid" in msg:
        return "Hint: a Fox UID is digits only, e.g. 531169471."
    if "no games" in msg or "not exist" in msg or "does not exist" in msg:
        return ("Hint: no games found to analyse. Check the UID / nickname, or "
                "whether the SGF folder path is right.")
    if "sgf" in msg or "analy" in msg:
        return ("Hint: importing needs an SGF that LizzieYZY has analysed (with "
                "KataGo analysis embedded). A plain game record cannot be imported.")
    return ("Hint: something went wrong. Expand the log below for detail; the usual "
            "causes are ikatago not being logged in, or a network problem.")


def _launch_lizzie():
    """Open LizzieYZY (the Java jar) so the user can analyse the just-downloaded
    games there.  Path comes from config.json 'lizzie_jar' (kept out of git)."""
    jar = (_safe_cfg().get("lizzie_jar") or "").strip()
    if not jar:
        print("! LizzieYZY is not configured: set lizzie_jar (the jar path) in config.json.")
        return
    jar = os.path.expanduser(jar)
    if not os.path.exists(jar):
        print(f"! LizzieYZY jar not found: {jar}")
        return
    import subprocess
    try:
        # argv form avoids shell-quoting issues with the (amd64) parentheses.
        subprocess.Popen(["java", "-jar", jar],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"LizzieYZY started: {jar}")
        print("First time only -- set up the engine: menu Settings > Engine (or the "
              "Engine Management dialog), paste the ikatago command from your "
              "config.json into Command, click Add > Save, and set Auto load to "
              "Default engine.")
        print("Once that is done, load the SGF you just downloaded in LizzieYZY and "
              "run the KataGo analysis; then bring the result back with "
              "\"2. Import analysed SGF\".")
    except FileNotFoundError:
        print("! Launch failed: java not found. Install a Java runtime first.")
    except Exception as e:  # noqa: BLE001
        print(f"! Could not start LizzieYZY: {e}")


def do_analyze(job, body):
    _reload_app_modules()
    src = body.get("source", "fox")
    do_an = bool(body.get("do_analyze", True))   # False = download only, no analysis
    # Optional: fold the results into an existing report (otherwise the report is
    # named automatically from the UID / folder name).
    target = (body.get("analyze_target") or "").strip()
    out_dir = None
    if target and target != "__auto__":
        out_dir = (target if os.path.isabs(target)
                   else os.path.join(HERE, target))
    # Optional (Fox only): save the games into a named subfolder under "My games"
    games_subdir = (body.get("games_subdir") or "").strip()
    games_dir = None
    if src == "fox" and games_subdir:
        gd = os.path.expanduser(games_subdir)
        games_dir = (gd if os.path.isabs(gd)
                     else os.path.join(pipeline.DOWNLOADER_DIR, games_subdir))
    try:
        rp = pipeline.full_pipeline(
            uid=body.get("uid") or None,
            source=src,
            local_dir=body.get("local_dir") or None,
            user_name=body.get("nick") or "",
            download_limit=int(body.get("download_limit", 100)),
            num_games=int(body.get("num_games", 10)),
            max_visits=int(body.get("max_visits", 300)),
            max_time=float(body.get("max_time", 1.0)),
            mistake_th=float(body.get("mistake_th", 2.0)),
            blunder_th=float(body.get("blunder_th", 6.0)),
            force=bool(body.get("force", False)),
            do_download=(src == "fox"),
            do_analyze=do_an,
            output_dir=out_dir,
            games_dir=games_dir,
            log=print)
    except Exception as e:  # noqa: BLE001
        print("\n" + _friendly_hint(e))
        raise
    if not do_an and not body.get("open_lizzie"):
        print("Download complete (not analysed). When you want to review, come back "
              "and press \"Start: download + analyse + report\".")
    if body.get("open_lizzie"):
        print("Download complete -- opening LizzieYZY...")
        _launch_lizzie()
    if rp and os.path.exists(rp):
        job.report = os.path.relpath(os.path.dirname(os.path.abspath(rp)), HERE)
    write_static_index()


def do_import(job, body):
    _reload_app_modules()
    target = (body.get("target") or "").strip()
    if not target:
        raise ValueError("No target report given.")
    target_dir = (target if os.path.isabs(target)
                  else os.path.join(HERE, target))
    files = body.get("files") or []
    if not files:
        raise ValueError("No SGF files were received.")
    tmp = tempfile.mkdtemp(prefix="ymyj_imp_")
    paths = []
    for i, f in enumerate(files):
        name = os.path.basename(f.get("name") or f"game_{i}.sgf")
        if not name.lower().endswith(".sgf"):
            name += ".sgf"
        p = os.path.join(tmp, name)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(f.get("text") or "")
        paths.append(p)
    cfg = _safe_cfg()
    try:
        n, rp = import_lizzie.run_import(
            paths, target_dir, cfg,
            subject_name=(body.get("subject") or None),
            on_dup=(body.get("on_dup") or "skip"),
            rebuild=True, log=print)
    except Exception as e:  # noqa: BLE001
        print("\n" + _friendly_hint(e))
        raise
    if rp and os.path.exists(rp):
        job.report = os.path.relpath(os.path.dirname(os.path.abspath(rp)), HERE)
    write_static_index()


def set_default_config(**kv):
    """Persist a few simple defaults (e.g. default_games_subdir) into config.json
    WITHOUT round-tripping through the env-expanding loader — so ${ENV}
    placeholders (and any credentials) are preserved verbatim, never leaked."""
    import appconfig
    path = appconfig.REAL_PATH
    src = path if os.path.exists(path) else appconfig.EXAMPLE_PATH
    try:
        with open(src, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        raw = {}
    raw.update({k: v for k, v in kv.items() if v is not None})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)
    return True
