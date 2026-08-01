#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mirror of Go - the download + analyse pipeline.

Chains three steps together for reuse by the GUI (fox_review_app.py) and the CLI:
  1) download the most recent N games for a Fox UID (deduplicated, skipping files
     that already exist);
  2) auto-detect *your* nickname from the downloaded games (the name that appears
     in every game);
  3) write config.json back, then call analyze + report to build the review.

This layer does not depend on Tkinter, so it can be imported on its own for unit
tests or command-line use.

It reuses the existing downloader `My games/fox_full_downloader.py` (same API and
filename rules) plus the existing analyze.py / report.py, which both read their
settings from config.json.
"""

import os
import re
import sys
import json
import time
import glob
import importlib
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
DOWNLOADER_DIR = os.path.join(REPO_ROOT, "My games")
CONFIG_PATH = os.path.join(HERE, "config.json")

# Make analyze / report / sgfparse importable (they live in HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
# Make the existing downloader importable (it lives in "My games")
if DOWNLOADER_DIR not in sys.path:
    sys.path.insert(0, DOWNLOADER_DIR)


def _log(msg, log=None):
    (log or print)(msg)


# ---------------------------------------------------------------------------
# Downloader
# ---------------------------------------------------------------------------
def _load_downloader():
    """Import the existing fox_full_downloader module (reusing its HTTP and
    filename logic)."""
    try:
        return importlib.import_module("fox_full_downloader")
    except Exception as e:
        raise RuntimeError(
            f"Could not load the downloader fox_full_downloader.py "
            f"(expected in {DOWNLOADER_DIR}): {e}"
        )


def default_games_dir(uid):
    """One subfolder per UID, so games from different accounts do not mix."""
    return os.path.join(DOWNLOADER_DIR, "yehu-games", str(uid))


def default_output_dir(uid):
    """One analysis output folder per UID."""
    return os.path.join(HERE, f"output_{uid}")


def download_recent(uid, limit=100, out_dir=None, log=None,
                    type_=4, max_pages=200, sleep=0.4):
    """Download the most recent `limit` games for this UID into out_dir.

    Deduplication: by chessid within a page, and on write we skip any SGF that
    already exists and is non-empty.
    Returns dict: {metas, saved:[(meta,path)], downloaded, skipped, failed:[(cid,err)]}
    """
    fox = _load_downloader()
    out_dir = out_dir or default_games_dir(uid)
    os.makedirs(out_dir, exist_ok=True)

    # --- 1. Page through the game list, collecting at most `limit` games (the API
    #        returns newest first) ---
    collected = []
    seen = set()
    lastcode = 0
    for page in range(1, max_pages + 1):
        if len(collected) >= limit:
            break
        payload = fox.fetch_chess_list(uid, lastcode=lastcode, type_=type_)
        chesslist = payload.get("chesslist", [])
        if not chesslist:
            _log(f"  list page {page}: empty, stopping", log)
            break
        new = 0
        for g in chesslist:
            cid = g.get("chessid")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            collected.append(g)
            new += 1
            if len(collected) >= limit:
                break
        _log(f"  list page {page}: {len(chesslist)} entries, "
             f"{len(collected)} collected so far", log)
        if new == 0:
            break
        lastcode = chesslist[-1].get("chessid", 0)
        time.sleep(0.3)

    _log(f"Planning to download {len(collected)} games (limit {limit})", log)

    # --- 2. Download each SGF, skipping ones already on disk ---
    saved, downloaded, skipped, failed = [], 0, 0, []
    for i, g in enumerate(collected, 1):
        cid = g["chessid"]
        fn = fox.make_filename(g)
        path = os.path.join(out_dir, fn)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            _log(f"  [{i}/{len(collected)}] already present, skipped: {fn}", log)
            skipped += 1
            saved.append((g, path))
            continue
        try:
            sgf = fox.fetch_sgf(cid)
            with open(path, "w", encoding="utf-8") as f:
                f.write(sgf)
            _log(f"  [{i}/{len(collected)}] ✓ {fn}", log)
            downloaded += 1
            saved.append((g, path))
        except Exception as e:  # noqa: BLE001 - log network errors per game, keep going
            _log(f"  [{i}/{len(collected)}] ✗ {cid}: {e}", log)
            failed.append((cid, str(e)))
        time.sleep(sleep)

    _log(f"Download finished: {downloaded} new, {skipped} skipped, {len(failed)} failed", log)
    return {
        "metas": collected,
        "saved": saved,
        "downloaded": downloaded,
        "skipped": skipped,
        "failed": failed,
        "out_dir": out_dir,
    }


def detect_nickname(metas):
    """Detect *your* nickname from the game metadata: the most frequent name.

    Every game downloaded for a UID contains that player (as Black or White), so
    their nickname appears in (almost) every game and is the most frequent one.
    Returns a string, or None.
    """
    c = Counter()
    for g in metas:
        for k in ("blackenname", "whiteenname"):
            v = (g.get(k) or "").strip()
            if v:
                c[v] += 1
    if not c:
        return None
    return c.most_common(1)[0][0]


def detect_nickname_from_sgf(games_dir, log=None):
    """Detect *your* nickname from a folder of local game records.

    Parses PB/PW from each SGF and counts the most frequent name -- yours appears
    in (almost) every game while the opponents all differ. Returns a string, or
    None. Used by local-folder mode, where no Fox metadata is available.
    """
    import sgfparse  # imported lazily to avoid an extra dependency without an engine
    c = Counter()
    n = 0
    for p in sorted(glob.glob(os.path.join(os.path.expanduser(games_dir),
                                            "**", "*.sgf"), recursive=True)):
        try:
            g = sgfparse.parse_sgf(p)
        except Exception:
            continue
        n += 1
        for v in ((g.get("pb") or "").strip(), (g.get("pw") or "").strip()):
            if v:
                c[v] += 1
    _log(f"  scanned {n} SGF file(s)", log)
    if not c:
        return None
    return c.most_common(1)[0][0]


def _sanitize(s):
    return re.sub(r"[^\w.-]", "_", str(s)) or "local"


# ---------------------------------------------------------------------------
# Reading and writing config
# ---------------------------------------------------------------------------
def load_config():
    import appconfig
    return appconfig.load_config()


def update_config(games_dir=None, user_name=None, num_games=None,
                  max_visits=None, max_time=None, mistake_th=None,
                  blunder_th=None, output_dir=None, log=None):
    """Update only the fields given, leaving ikatago_command and the rest as-is."""
    cfg = load_config()
    if games_dir is not None:
        cfg["games_dirs"] = [games_dir]
    if user_name:
        cfg["user_names"] = [user_name]
    if num_games is not None:
        cfg["num_games"] = int(num_games)
    if max_visits is not None:
        cfg["max_visits"] = int(max_visits)
    if max_time is not None:
        cfg["max_time_per_move"] = float(max_time)
    if mistake_th is not None:
        cfg["mistake_threshold"] = float(mistake_th)
    if blunder_th is not None:
        cfg["blunder_threshold"] = float(blunder_th)
    if output_dir is not None:
        cfg["output_dir"] = output_dir
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    _log(f"config.json updated (user_names={cfg.get('user_names')}, "
         f"num_games={cfg.get('num_games')}, max_visits={cfg.get('max_visits')})", log)
    return cfg


# ---------------------------------------------------------------------------
# Analysis + report (calls analyze.py / report.py, which read config.json)
# ---------------------------------------------------------------------------
def run_analysis(force=False, log=None):
    """Call analyze.main().  force=True re-analyses every game."""
    analyze = importlib.import_module("analyze")
    importlib.reload(analyze)  # make sure it picks up the latest config.json
    argv = ["--force"] if force else []
    _log(f"=== Starting analysis (cloud ikatago){' [forced re-analysis]' if force else ''} ===", log)
    rc = analyze.main(argv)
    if rc != 0:
        raise RuntimeError(f"Analysis did not succeed (analyze.main returned {rc}). "
                           f"Check the ikatago login and your config.")
    return rc


def run_report(log=None):
    """Call report.main() to write review_report.html; returns its path."""
    report = importlib.import_module("report")
    importlib.reload(report)
    _log("=== Building the review report ===", log)
    rc = report.main([])
    if rc != 0:
        raise RuntimeError(f"Report generation did not succeed (report.main returned {rc}).")
    cfg = load_config()
    return os.path.join(os.path.expanduser(cfg["output_dir"]), "review_report.html")


# ---------------------------------------------------------------------------
# One-shot full pipeline
# ---------------------------------------------------------------------------
def full_pipeline(uid=None, source="fox", local_dir=None, user_name=None,
                  download_limit=100, num_games=10, max_visits=300,
                  max_time=1.0, mistake_th=2.0, blunder_th=6.0,
                  force=False, do_download=True, do_analyze=True,
                  output_dir=None, games_dir=None, log=None):
    """Download or pick games -> detect the nickname -> write config -> analyse ->
    report.  Returns the report path, if one was produced.

    source="fox"   : download by Fox UID (do_download controls whether it really
                     downloads).
    source="local" : use the local SGF folder local_dir directly, no download.
    user_name      : nickname given by hand; blank means auto-detect.
    output_dir     : explicit report output folder (used to fold results into an
                     existing report); blank means name it from the UID or the
                     local folder name.
    games_dir      : (Fox mode only) explicit download/read folder for the games;
                     blank means the default My games/yehu-games/UID.
    """
    nickname = (user_name or "").strip() or None
    output_dir_override = (output_dir or "").strip() or None
    games_dir_override = (games_dir or "").strip() or None

    if source == "local":
        if not local_dir or not os.path.isdir(os.path.expanduser(local_dir)):
            raise ValueError(f"Local SGF folder does not exist: {local_dir!r}")
        games_dir = os.path.expanduser(local_dir)
        base = os.path.basename(os.path.normpath(games_dir))
        output_dir = os.path.join(HERE, f"output_local_{_sanitize(base)}")
        if not nickname:
            nickname = detect_nickname_from_sgf(games_dir, log=log)
        if nickname:
            _log(f"Using nickname: {nickname}", log)
        else:
            _log("! Could not detect a nickname; keeping the existing user_names from "
                 "config (enter it by hand if that does not match)", log)
    else:
        uid = str(uid or "").strip()
        if not uid.isdigit():
            raise ValueError(f"A UID must be digits only; got {uid!r}")
        games_dir = (os.path.expanduser(games_dir_override)
                     if games_dir_override else default_games_dir(uid))
        output_dir = default_output_dir(uid)
        if do_download:
            res = download_recent(uid, limit=download_limit, out_dir=games_dir, log=log)
            if not nickname:
                # Trust the PB/PW names actually written into the SGF -- the
                # analysis matches on exactly those.  The account names the Fox API
                # returns (blackenname/whiteenname) can differ from the in-game
                # nickname, which would later mean "no games matched".  Fall back to
                # the API names only if the SGFs yield nothing.
                nickname = (detect_nickname_from_sgf(games_dir, log=log)
                            or detect_nickname(res["metas"]))
            if nickname:
                _log(f"Using nickname: {nickname}", log)
            else:
                _log("! Could not detect a nickname; keeping the existing user_names "
                     "from config", log)
        elif not nickname:
            # Not downloading and no nickname given: try the SGFs already on disk
            nickname = detect_nickname_from_sgf(games_dir, log=log)

    if output_dir_override:
        output_dir = os.path.expanduser(output_dir_override)
        _log(f"Results will be added to: {output_dir}", log)

    update_config(games_dir=games_dir, user_name=nickname, num_games=num_games,
                  max_visits=max_visits, max_time=max_time, mistake_th=mistake_th,
                  blunder_th=blunder_th, output_dir=output_dir, log=log)

    report_path = None
    if do_analyze:
        run_analysis(force=force, log=log)
        report_path = run_report(log=log)
        _log(f"All done. Report: {report_path}", log)
    return report_path


# ---------------------------------------------------------------------------
# Command-line entry point (optional; the GUI does not go through here)
# ---------------------------------------------------------------------------
def _cli():
    import argparse
    p = argparse.ArgumentParser(
        description="Fox game download + KataGo review, end to end")
    p.add_argument("uid", nargs="?", help="numeric Fox UID (omit when using --local)")
    p.add_argument("--local", metavar="DIR", help="use a local SGF folder instead of downloading")
    p.add_argument("--name", help="your nickname (blank = auto-detect)")
    p.add_argument("--download", type=int, default=100, help="how many recent games to download (default 100)")
    p.add_argument("--games", type=int, default=10, help="how many games to analyse (default 10)")
    p.add_argument("--visits", type=int, default=300, help="max_visits per move (default 300)")
    p.add_argument("--time", type=float, default=1.0, help="max seconds per move (default 1.0)")
    p.add_argument("--mistake", type=float, default=2.0, help="mistake threshold in points (default 2.0)")
    p.add_argument("--blunder", type=float, default=6.0, help="blunder threshold in points (default 6.0)")
    p.add_argument("--force", action="store_true", help="re-analyse every game")
    p.add_argument("--no-download", action="store_true", help="skip downloading; analyse what is on disk")
    p.add_argument("--no-analyze", action="store_true", help="download only, do not analyse")
    a = p.parse_args()
    source = "local" if a.local else "fox"
    if source == "fox" and not a.uid:
        p.error("Give a Fox UID, or use --local to point at a local SGF folder")
    full_pipeline(uid=a.uid, source=source, local_dir=a.local, user_name=a.name,
                  download_limit=a.download, num_games=a.games,
                  max_visits=a.visits, max_time=a.time, mistake_th=a.mistake,
                  blunder_th=a.blunder, force=a.force,
                  do_download=not a.no_download, do_analyze=not a.no_analyze)


if __name__ == "__main__":
    _cli()
