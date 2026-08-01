#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mirror of Go - KataGo game review, local web app.

Starts a tiny server bound to 127.0.0.1 only and opens a browser:

    /            dashboard: the analyse / import module + every analysed report
    /analyze     the standalone "Analyse / Import" page
    /r/<report>  one report (with a top bar to go back or switch reports)

Analysis still runs through the local ikatago client (cloud KataGo); your
credentials never leave this machine.

Launch by double-clicking "Mirror of Go.command" in the repo root, or:
    python3 go_review/web_app.py            # port 8765, opens a browser
    python3 go_review/web_app.py --port 9000 --no-browser
"""

import io
import os
import re
import sys
import json
import html
import time
import zipfile
import shutil
import threading
import traceback
import tempfile
import argparse
import webbrowser
import datetime
from urllib.parse import urlparse, parse_qs, quote, unquote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import pipeline       # noqa: E402
import import_lizzie  # noqa: E402
import report         # noqa: E402
import go_terms       # noqa: E402


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


# ---------------------------------------------------------------------------
# Discovering, summarising and resolving report folders
# ---------------------------------------------------------------------------
_SUMMARY_CACHE = {}   # rdir -> (dir_mtime, summary dict)


def report_summary(rdir):
    """Cheap per-report summary for dashboard cards: game count, win/loss,
    last game date, source label. Cached and invalidated on dir mtime."""
    import glob as _glob
    try:
        dmt = os.path.getmtime(rdir)
    except OSError:
        dmt = 0
    cached = _SUMMARY_CACHE.get(rdir)
    if cached and cached[0] == dmt:
        return cached[1]
    games = wins = losses = 0
    last_date = ""
    for p in _glob.glob(os.path.join(rdir, "*.json")):
        if os.path.basename(p) in ("index.json", "notes.json", "practice_hidden.json"):
            continue
        games += 1
        try:
            with open(p, encoding="utf-8") as f:
                g = json.load(f)
        except Exception:
            continue
        w = g.get("won")
        if w is True:
            wins += 1
        elif w is False:
            losses += 1
        d = g.get("date") or ""
        if d > last_date:
            last_date = d
    try:
        source = report.source_label_from_path(rdir)
    except Exception:
        source = ""
    summ = {"games": games, "wins": wins, "losses": losses,
            "last_date": last_date, "source": source}
    _SUMMARY_CACHE[rdir] = (dmt, summ)
    return summ


def list_reports():
    """[{rel, label, mtime, has_html, summary}] -- existing reports, newest first."""
    out = []
    for d in import_lizzie.list_report_dirs(HERE):
        rel = os.path.relpath(d, HERE)
        html_path = os.path.join(d, "review_report.html")
        has_html = os.path.exists(html_path)
        try:
            mt = os.path.getmtime(html_path if has_html else d)
        except OSError:
            mt = 0
        out.append({"rel": rel, "label": rel, "mtime": mt,
                    "has_html": has_html, "summary": report_summary(d)})
    # newest game date first (fall back to file mtime for ties / undated)
    out.sort(key=lambda r: (r["summary"].get("last_date") or "", r["mtime"]),
             reverse=True)
    return out


def list_games_dirs():
    """Subfolders under "My games" that contain SGF files (depth <= 2), as
    relative paths — used to populate the download-folder picker."""
    base = pipeline.DOWNLOADER_DIR
    out = []
    if not os.path.isdir(base):
        return out
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs
                   if not d.startswith(".") and d != "__pycache__"]
        rel = os.path.relpath(root, base)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth >= 2:
            dirs[:] = []          # don't descend deeper than 2 levels
        if root == base:
            continue
        nsgf = sum(1 for f in files if f.lower().endswith(".sgf"))
        if nsgf:
            out.append({"rel": rel, "sgf": nsgf})
    out.sort(key=lambda r: r["rel"])
    return out


def report_dir_from_rel(rel):
    """Resolve a report rel-path safely under HERE. None if outside / missing."""
    rel = unquote(rel).strip("/")
    target = os.path.normpath(os.path.join(HERE, rel))
    if os.path.commonpath([target, HERE]) != HERE:
        return None
    if target == HERE or not os.path.isdir(target):
        return None
    return target


# ---------------------------------------------------------------------------
# Pages: shared styles + the analyse/import module + dashboard + analyse page + report nav
# ---------------------------------------------------------------------------
PAGE_CSS = r"""
/* ---- Golden Hour theme tokens (warm paper · chocolate ink · amber) ---- */
:root{
  --paper:#f6f1e8; --card:#fffdf9; --line:#e9dfce; --line-soft:#f1ead9;
  --ink:#3d352e; --ink-soft:#6f6357; --muted:#9a8d7b;
  --espresso:#2a241f; --espresso-2:#37302a; --espresso-line:#3f382f;
  --on-dark:#e7ddce; --on-dark-soft:#b0a18d;
  --amber:#b7791f; --amber-ink:#8a5a12; --amber-soft:#f6ecd6; --amber-line:#e6d3ab;
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Segoe UI",sans-serif}
a{color:inherit}
.hero{background:var(--espresso);color:#fff;padding:22px 26px}
.hero h1{margin:0;font-size:22px;letter-spacing:.01em}
.hero .sub{margin:4px 0 0;color:var(--on-dark-soft);font-size:13px}
.hero .back{display:inline-block;margin-bottom:8px;color:var(--on-dark);
  text-decoration:none;font-size:13px;font-weight:600}
.hero .back:hover{color:#fff}
main{max-width:1080px;margin:22px auto;padding:0 18px 60px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;
  padding:18px 20px;margin-bottom:26px;box-shadow:0 1px 2px rgba(74,64,58,.05)}
.card-h{display:flex;align-items:center;justify-content:space-between;
  margin-bottom:10px}
.card-h h2{margin:0;font-size:17px}
.btn-ghost{font-size:12.5px;font-weight:600;color:var(--amber-ink);
  text-decoration:none;border:1px solid var(--amber-line);border-radius:8px;
  padding:5px 10px}
.btn-ghost:hover{background:var(--amber-soft)}
.sec{font-size:15px;color:var(--ink-soft);margin:0 2px 12px;font-weight:700}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(248px,1fr));
  gap:14px}
.rep{display:block;background:var(--card);border:1px solid var(--line);
  border-radius:12px;padding:15px 16px;text-decoration:none;transition:.12s;
  color:var(--ink)}
.rep:hover{border-color:var(--amber);box-shadow:0 4px 14px rgba(183,121,31,.14);
  transform:translateY(-1px)}
.rep .nm{font-weight:700;font-size:14.5px;word-break:break-all}
.rep .tag{display:inline-block;margin-top:6px;font-size:11px;color:var(--amber-ink);
  background:var(--amber-soft);border-radius:20px;padding:2px 9px}
.rep .meta{margin-top:10px;font-size:12.5px;color:var(--ink-soft);
  display:flex;justify-content:space-between;gap:8px}
.rep .rec{margin-top:4px;font-size:12px;color:var(--muted)}
.rep .big{font-size:20px;font-weight:800;color:var(--ink);
  font-variant-numeric:tabular-nums}
.empty{color:var(--muted);font-size:13px;padding:8px 2px}

/* ---- analyse / import module ---- */
.ymmod{font-size:13px}
.ymmod .row{margin:9px 0}
.ymmod label{display:block;font-size:12px;color:#555;margin-bottom:3px}
.ymmod input[type=text],.ymmod input[type=number],.ymmod select{
  width:100%;padding:8px 9px;border:1px solid #cdd3da;border-radius:8px;
  font-size:13px;background:#fff}
.ymmod .two{display:flex;gap:12px}
.ymmod .two>div{flex:1}
.ymtabs{display:flex;gap:8px;margin-bottom:10px}
.ymtabs button{flex:1;max-width:240px;padding:9px;border:1px solid #cdd3da;
  background:#fff;border-radius:9px;cursor:pointer;font-size:13.5px;
  font-weight:600;color:#444}
.ymtabs button.on{background:var(--espresso);color:#fff;border-color:var(--espresso)}
.ympane{display:none}
.ympane.on{display:block}
.ymmod .go{margin-top:12px;padding:11px 22px;border:none;border-radius:9px;
  background:var(--amber);color:#fff;font-size:14px;font-weight:700;cursor:pointer}
.ymmod .go:hover{background:var(--amber-ink)}
.ymmod .go:disabled{background:#cbbfa6;cursor:not-allowed}
.ymmod .go2{background:var(--card);color:var(--amber-ink);
  border:1px solid var(--amber);margin-left:10px}
.ymmod .go2:hover{background:var(--amber-soft)}
.ymmod .setdef{flex:none;white-space:nowrap;padding:8px 12px;border-radius:8px;
  border:1px solid #cdd3da;background:#fff;color:#444;font-size:12.5px;
  font-weight:600;cursor:pointer}
.ymmod .setdef:hover{background:#f1f4f8;border-color:#2b6cb0;color:#2b6cb0}
.ymmod .setdef.ok{background:#e6f4ea;border-color:#38a169;color:#2f855a}
.ymmod .go2:disabled{background:#f1f4f8;color:#9fb3c8;border-color:#cdd3da}
.ymmod .hint{font-size:11.5px;color:#8a929c;margin-top:4px}
.ymmod .seg{display:flex;gap:16px;margin-bottom:8px}
.ymmod .seg label{display:flex;align-items:center;gap:5px;margin:0;
  font-size:13.5px;color:#333;cursor:pointer}
.ymmod fieldset{border:1px solid #e3e7eb;border-radius:10px;padding:12px 14px;
  margin:0}
#ym-log{margin-top:14px;background:#0f172a;color:#cbd5e1;border-radius:10px;
  padding:11px 12px;font-family:Menlo,monospace;font-size:11.5px;
  white-space:pre-wrap;max-height:260px;overflow-y:auto;display:none}
#ym-log.on{display:block}
"""


def _esc(s):
    return html.escape(str(s))


def _target_options_html():
    reps = list_reports()
    try:
        default = str(_safe_cfg().get("default_import_target") or "")
    except Exception:
        default = ""
    have_default = any(r["rel"] == default for r in reps)
    opts = []
    for i, r in enumerate(reps):
        sel = " selected" if (r["rel"] == default if have_default else i == 0) else ""
        opts.append(f'<option value="{_esc(r["rel"])}"{sel}>'
                    f'{_esc(r["label"])}</option>')
    opts.append('<option value="__new__">+ New report...</option>')
    return "".join(opts)


def _analyze_target_options_html():
    """For tab 1: default "auto", then existing reports to append into."""
    opts = ['<option value="__auto__" selected>(Auto: create or reuse a report of the same name)'
            '</option>']
    for r in list_reports():
        opts.append(f'<option value="{_esc(r["rel"])}">'
                    f'Add to: {_esc(r["label"])}</option>')
    return "".join(opts)


def _analysis_module_html():
    """The reusable (1) download+analyse / (2) import module (markup + script).  Inline; no
    overlay.  Used by both the dashboard and the standalone /analyze page."""
    default_uid = default_subdir = ""
    try:
        cfg = _safe_cfg()
        default_uid = str(cfg.get("default_fox_uid") or "")
        default_subdir = str(cfg.get("default_games_subdir") or "")
    except Exception:
        pass
    return (ANALYSIS_MODULE
            .replace("__DEFAULT_UID__", _esc(default_uid))
            .replace("__DEFAULT_SUBDIR__", json.dumps(default_subdir))
            .replace("__TARGET_OPTIONS__", _target_options_html())
            .replace("__ANALYZE_TARGET_OPTIONS__",
                     _analyze_target_options_html()))


ANALYSIS_MODULE = r"""
<div class="ymmod">
  <div class="ymtabs">
    <button data-tab="an" class="on">1. Download + analyse</button>
    <button data-tab="im">2. Import analysed SGF</button>
  </div>

  <!-- 1. download + analyse -->
  <div class="ympane on" id="ympane-an">
   <fieldset>
    <div class="seg">
      <label><input type="radio" name="ymsrc" value="fox" checked> Download by Fox UID</label>
      <label><input type="radio" name="ymsrc" value="local"> Local SGF folder</label>
    </div>
    <div class="row" id="ymfoxrow">
      <label>Fox UID (digits only)</label>
      <input type="text" id="ym-uid" value="__DEFAULT_UID__" placeholder="e.g. 531169471">
    </div>
    <div class="row" id="ymfoxdirrow">
      <label>Save games to this "My games" subfolder</label>
      <div style="display:flex;gap:8px;align-items:center">
        <select id="ym-foxdir" style="flex:1">
          <option value="">(Default: yehu-games/UID)</option>
          <option value="__new__">+ New subfolder...</option>
        </select>
        <button type="button" class="setdef" id="ym-foxdir-setdef"
                title="Make the current selection the default download folder">Set as default</button>
      </div>
      <input type="text" id="ym-foxdir-new" style="display:none;margin-top:6px"
             placeholder="New subfolder name, e.g. yehu_4d">
    </div>
    <div class="row" id="ymlocalrow" style="display:none">
      <label>Local SGF folder (absolute path on this Mac)</label>
      <input type="text" id="ym-localdir" placeholder="/Users/.../sgf_folder">
    </div>
    <div class="two">
      <div class="row"><label>How many recent games to download</label>
        <input type="number" id="ym-dl" value="1" min="1" max="500"></div>
      <div class="row"><label>Games to analyse</label>
        <input type="number" id="ym-ng" value="1" min="1" max="200"></div>
    </div>
    <div class="row"><label>Your nickname (leave blank to auto-detect)</label>
      <input type="text" id="ym-nick" placeholder="Blank = auto-detect"></div>
    <div class="row"><label>Add results to</label>
      <select id="ym-an-target">__ANALYZE_TARGET_OPTIONS__</select>
      <div class="hint">By default a report is created from the UID or folder name; pick "Add to..." to merge these games into an existing report.</div>
    </div>
    <div class="two">
      <div class="row"><label>Visits per move</label>
        <input type="number" id="ym-visits" value="300" min="50" max="5000" step="50"></div>
      <div class="row"><label>Max seconds per move</label>
        <input type="number" id="ym-time" value="1.0" min="0.2" max="30" step="0.5"></div>
    </div>
    <div class="two">
      <div class="row"><label>Mistake threshold (pts)</label>
        <input type="number" id="ym-mth" value="2.0" min="0.5" max="20" step="0.5"></div>
      <div class="row"><label>Blunder threshold (pts)</label>
        <input type="number" id="ym-bth" value="6.0" min="2" max="40" step="1"></div>
    </div>
    <div class="row"><label><input type="checkbox" id="ym-force"> Re-analyse everything (including games already done)</label></div>
    <button class="go" id="ym-run-an">Start: download + analyse + report</button>
    <button class="go go2" id="ym-run-dl">Download only (no analysis)</button>
    <button class="go go2" id="ym-run-lz">Download + open LizzieYZY</button>
    <div class="hint">Analysis runs through the local ikatago client (cloud KataGo) -- make sure it can log in.
      "Download only" just saves your Fox games to this Mac. "Open LizzieYZY" downloads and then launches
      LizzieYZY; once you have analysed the games there, bring them back in with "2. Import analysed SGF".</div>
   </fieldset>
  </div>

  <!-- 2. import analysed SGF -->
  <div class="ympane" id="ympane-im">
   <fieldset>
    <div class="row">
      <label>Analysed SGF files (exported from LizzieYZY; multiple allowed)</label>
      <input type="file" id="ym-files" accept=".sgf" multiple>
      <div class="hint" id="ym-files-hint">No files selected</div>
    </div>
    <div class="row">
      <label>Import into report</label>
      <div style="display:flex;gap:8px;align-items:center">
        <select id="ym-target" style="flex:1">__TARGET_OPTIONS__</select>
        <button type="button" class="setdef" id="ym-target-setdef"
                title="Make the current selection the default import target">Set as default</button>
      </div>
    </div>
    <div class="row" id="ym-newrow" style="display:none">
      <label>New report folder name</label>
      <input type="text" id="ym-newname" placeholder="e.g. output_local_xxx">
    </div>
    <div class="row"><label>Review subject nickname (blank = auto-detect; falls back to Black)</label>
      <input type="text" id="ym-subject" placeholder="Blank = auto-detect"></div>
    <div class="row"><label>On duplicate games</label>
      <select id="ym-dup"><option value="skip">Skip</option>
        <option value="overwrite">Overwrite</option></select></div>
    <button class="go" id="ym-run-im">Import and update the report</button>
   </fieldset>
  </div>

  <pre id="ym-log"></pre>
</div>
<script>
(function(){
  function $(id){ return document.getElementById(id); }
  if(!$('ym-run-an')) return;

  document.querySelectorAll('.ymtabs button').forEach(function(b){
    b.onclick=function(){
      document.querySelectorAll('.ymtabs button').forEach(function(x){
        x.classList.remove('on'); });
      b.classList.add('on');
      $('ympane-an').classList.toggle('on', b.dataset.tab==='an');
      $('ympane-im').classList.toggle('on', b.dataset.tab==='im');
    };
  });
  document.querySelectorAll('input[name=ymsrc]').forEach(function(r){
    r.onchange=function(){
      var local=document.querySelector('input[name=ymsrc]:checked').value==='local';
      $('ymfoxrow').style.display=local?'none':'';
      $('ymfoxdirrow').style.display=local?'none':'';
      $('ymlocalrow').style.display=local?'':'none';
    };
  });
  $('ym-target').onchange=function(){
    $('ym-newrow').style.display=this.value==='__new__'?'':'none';
  };

  // Remember the last Fox UID used (stored locally) so it need not be retyped
  try{ var lu=localStorage.getItem('ym_last_uid');
       if(lu && !$('ym-uid').value) $('ym-uid').value=lu; }catch(e){}

  // Existing "My games" subfolders -- pick one instead of typing a path
  var DEFAULT_SUBDIR=__DEFAULT_SUBDIR__;
  $('ym-foxdir').onchange=function(){
    $('ym-foxdir-new').style.display=this.value==='__new__'?'':'none';
  };
  fetch('/api/games_dirs?t='+Date.now(),{cache:'no-store'})
  .then(function(r){return r.json();}).then(function(d){
    var sel=$('ym-foxdir'); if(!sel) return;
    var newOpt=sel.querySelector('option[value="__new__"]');
    (d.dirs||[]).forEach(function(x){
      var o=document.createElement('option');
      o.value=x.rel; o.textContent=x.rel+' ('+x.sgf+' games)';
      sel.insertBefore(o, newOpt);
    });
    // Preselect the default folder, if it still exists
    if(DEFAULT_SUBDIR){
      var has=Array.prototype.some.call(sel.options,function(o){return o.value===DEFAULT_SUBDIR;});
      if(has) sel.value=DEFAULT_SUBDIR;
    }
  }).catch(function(){});

  // "Set as default": save the selected subfolder to config so it is preselected next time
  $('ym-foxdir-setdef').onclick=function(){
    var v=$('ym-foxdir').value;
    if(v==='__new__') v=$('ym-foxdir-new').value.trim();
    var btn=this;
    fetch('/api/set_default',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({games_subdir:v})}).then(function(r){return r.json();})
    .then(function(res){
      if(res && res.ok){
        DEFAULT_SUBDIR=v;
        var old=btn.textContent; btn.textContent='Default set \u2713'; btn.classList.add('ok');
        setTimeout(function(){ btn.textContent=old; btn.classList.remove('ok'); },1600);
      } else { alert('Could not save: '+((res&&res.error)||'unknown error')); }
    }).catch(function(e){ alert('Could not save: '+e); });
  };
  $('ym-target-setdef').onclick=function(){
    var v=$('ym-target').value;
    if(v==='__new__'){ alert('Pick an existing report before setting it as the default.'); return; }
    var btn=this;
    fetch('/api/set_default',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({import_target:v})}).then(function(r){return r.json();})
    .then(function(res){
      if(res && res.ok){
        var old=btn.textContent; btn.textContent='Default set \u2713'; btn.classList.add('ok');
        setTimeout(function(){ btn.textContent=old; btn.classList.remove('ok'); },1600);
      } else { alert('Could not save: '+((res&&res.error)||'unknown error')); }
    }).catch(function(e){ alert('Could not save: '+e); });
  };
  $('ym-files').onchange=function(){
    var n=this.files.length;
    $('ym-files-hint').textContent = n? (n+' file(s) selected') : 'No files selected';
  };

  var logEl=$('ym-log');
  function showLog(){ logEl.classList.add('on'); logEl.textContent=''; }
  function appendLog(t){ if(t){ logEl.textContent+=t;
    logEl.scrollTop=logEl.scrollHeight; } }
  function setBusy(b){ $('ym-run-an').disabled=b; $('ym-run-im').disabled=b;
    $('ym-run-dl').disabled=b; $('ym-run-lz').disabled=b; }

  var embedded = (window.parent && window.parent !== window);
  function onDone(report){
    if(embedded){
      window.parent.postMessage({type:'ymdone', report:report||''}, '*');
    } else if(report){
      location.href='/r/'+encodeURIComponent(report);
    }
  }
  function poll(jid, since){
    fetch('/api/job/'+jid+'?since='+since).then(function(r){return r.json();})
    .then(function(d){
      appendLog(d.text); since=d.n;
      if(d.done){
        setBusy(false);
        if(d.ok && d.report){
          appendLog('\n\u2713 Done -- loading the report...\n');
          setTimeout(function(){ onDone(d.report); }, 1500);
        } else if(d.ok){
          appendLog('\n\u2713 Done.\n'); onDone('');
        } else {
          appendLog('\n\u2717 The job failed -- see the log above.\n');
        }
      } else { setTimeout(function(){ poll(jid, since); }, 700); }
    }).catch(function(){ setTimeout(function(){ poll(jid, since); }, 1200); });
  }
  function startJob(url, body){
    setBusy(true); showLog(); appendLog('Starting the job...\n');
    fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body)}).then(function(r){return r.json();})
    .then(function(d){
      if(d.error){ appendLog('✗ '+d.error+'\n'); setBusy(false); return; }
      poll(d.job, 0);
    }).catch(function(e){ appendLog('\u2717 Request failed: '+e+'\n'); setBusy(false); });
  }

  function runAnalyze(mode){  // 'analyze' | 'download' | 'lizzie'
    var src=document.querySelector('input[name=ymsrc]:checked').value;
    var doAnalyze=(mode==='analyze'), openLizzie=(mode==='lizzie');
    if(mode==='download' && src!=='fox'){
      alert('"Download only" applies to Fox UID downloads.'); return; }
    var fd=$('ym-foxdir').value;
    if(fd==='__new__') fd=$('ym-foxdir-new').value.trim();
    var body={source:src, uid:$('ym-uid').value.trim(),
      games_subdir:fd,
      local_dir:$('ym-localdir').value.trim(), nick:$('ym-nick').value.trim(),
      download_limit:+$('ym-dl').value, num_games:+$('ym-ng').value,
      max_visits:+$('ym-visits').value, max_time:+$('ym-time').value,
      mistake_th:+$('ym-mth').value, blunder_th:+$('ym-bth').value,
      analyze_target:$('ym-an-target').value, force:$('ym-force').checked,
      do_analyze:doAnalyze, open_lizzie:openLizzie};
    if(src==='fox' && !/^\d+$/.test(body.uid)){
      alert('Enter a Fox UID made of digits only.'); return; }
    if(src==='local' && doAnalyze && !body.local_dir){
      alert('Enter the path to your local SGF folder.'); return; }
    if(src==='fox'){ try{ localStorage.setItem('ym_last_uid', body.uid); }catch(e){} }
    startJob('/api/analyze', body);
  }
  $('ym-run-an').onclick=function(){ runAnalyze('analyze'); };
  $('ym-run-dl').onclick=function(){ runAnalyze('download'); };
  $('ym-run-lz').onclick=function(){ runAnalyze('lizzie'); };
  $('ym-run-im').onclick=function(){
    var files=$('ym-files').files;
    if(!files.length){ alert('Choose the analysed SGF files first.'); return; }
    var target=$('ym-target').value;
    if(target==='__new__'){
      target=$('ym-newname').value.trim();
      if(!target){ alert('Enter a name for the new report folder.'); return; }
    }
    if(!target){ alert('Pick a target report, or create a new one.'); return; }
    var payload={target:target, subject:$('ym-subject').value.trim(),
      on_dup:$('ym-dup').value, files:[]};
    var pending=files.length;
    setBusy(true); showLog(); appendLog('Reading '+files.length+' file(s)...\n');
    Array.prototype.forEach.call(files, function(f){
      var fr=new FileReader();
      fr.onload=function(){ payload.files.push({name:f.name, text:fr.result});
        if(--pending===0) startJob('/api/import', payload); };
      fr.onerror=function(){ appendLog('\u2717 Could not read: '+f.name+'\n');
        if(--pending===0) startJob('/api/import', payload); };
      fr.readAsText(f);
    });
  };
})();
</script>
"""


def _page(title, body, extra_css=""):
    return (f"<!doctype html><html lang=\"zh\"><head><meta charset=\"utf-8\">"
            f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{_esc(title)}</title><style>{PAGE_CSS}{extra_css}</style>"
            f"</head><body>{body}</body></html>")


SHELL_CSS = r"""
html,body{height:100%}
.app{display:flex;height:100vh;overflow:hidden}
.side{width:288px;flex:none;background:var(--espresso);color:var(--on-dark);
  display:flex;flex-direction:column;height:100vh;transition:width .18s ease}
.app.collapsed .side{width:0;min-width:0;overflow:hidden;border:none}
.side .brand{padding:16px 18px;font-size:16px;font-weight:800;color:#fff;
  border-bottom:1px solid var(--espresso-line);display:flex;align-items:center;
  justify-content:space-between;gap:8px;white-space:nowrap}
.side .brand .collapse{flex:none;border:none;background:none;color:var(--on-dark-soft);
  cursor:pointer;font-size:18px;line-height:1;padding:3px 7px;border-radius:7px}
.side .brand .collapse:hover{background:var(--espresso-2);color:#fff}
#side-reopen{position:fixed;top:10px;left:10px;z-index:100000;display:none;
  align-items:center;justify-content:center;background:var(--espresso);color:#fff;
  border:none;border-radius:9px;width:36px;height:36px;font-size:17px;
  cursor:pointer;box-shadow:0 2px 10px rgba(42,36,31,.4)}
#side-reopen:hover{background:var(--amber)}
.app.collapsed #side-reopen{display:flex}
.side .newbtn{margin:12px 14px 6px;padding:11px;border-radius:9px;border:none;
  background:var(--amber);color:#fff;font-weight:700;font-size:13.5px;cursor:pointer}
.side .newbtn.on,.side .newbtn:hover{background:var(--amber-ink)}
.side .newbtn2{margin:0 14px 6px;padding:9px;border-radius:9px;
  border:1px solid var(--espresso-line);background:var(--espresso-2);
  color:var(--on-dark);font-weight:600;font-size:13px;cursor:pointer}
.side .newbtn2.on,.side .newbtn2:hover{background:#453b32;color:#fff}
.side .sidelink{display:block;text-align:center;text-decoration:none;
  box-sizing:border-box}
.side .lh{padding:8px 18px 4px;font-size:11.5px;color:var(--on-dark-soft)}
.side .list{flex:1;overflow-y:auto;padding:0 10px 16px}
.repitem{display:flex;align-items:flex-start;gap:6px;padding:9px 10px;
  border-radius:9px;margin-bottom:3px}
.repitem:hover{background:var(--espresso-2)}
.repitem.on{background:#453b32;box-shadow:inset 3px 0 0 var(--amber)}
.repitem .info{flex:1;min-width:0;cursor:pointer}
.repitem .nm{font-size:13.5px;font-weight:600;color:#fff;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.repitem .mt{font-size:11px;color:var(--on-dark-soft);margin-top:2px;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.repitem .del{flex:none;border:none;background:none;color:#8a7d6b;cursor:pointer;
  font-size:13px;padding:3px 5px;border-radius:6px;line-height:1}
.repitem .del:hover{background:#4a2a22;color:#f0a58a}
.side .empty{padding:10px 14px;color:var(--on-dark-soft);font-size:12.5px}
.main{flex:1;height:100vh;min-width:0}
.main iframe{display:block;width:100%;height:100%;border:none;background:var(--paper)}

/* On phones the sidebar becomes an overlay drawer instead of squeezing the
   report; it's collapsed by default and slides in over the report. */
@media (max-width:760px){
  .side{position:fixed;top:0;left:0;z-index:200;width:84vw;max-width:320px}
  .app.collapsed .side{width:0}
  #side-reopen{display:flex}
}
"""


def dashboard_page():
    body = (
        "<div class='app'>"
        "<aside class='side'>"
        "<div class='brand'><span>Mirror of Go &middot; KataGo Review</span>"
        "<button class='collapse' id='btn-collapse' title='Collapse the sidebar'>&laquo;</button></div>"
        "<button class='newbtn' id='btn-analyze'>+ Analyse / import games</button>"
        "<button class='newbtn2' id='btn-compare'>&#8646; Compare reports &middot; track progress</button>"
        "<button class='newbtn2' id='btn-summary'>&#128211; Review summary &middot; diagnostic profile</button>"
        "<button class='newbtn2' id='btn-terms'>&#128214; Go terms &middot; Chinese to English</button>"
        "<a class='newbtn2 sidelink' id='btn-backup' href='/api/backup' download "
        "title='Zips the code plus your transcripts, summaries and deleted-blunder "
        "lists. Leaves out generated reports, per-game analysis and config.json "
        "(which holds your passwords).'>&#128230; Back up project &middot; download zip</a>"
        "<div class='lh' id='lh'>Analysed reports</div>"
        "<div class='list' id='replist'></div>"
        "</aside>"
        "<button id='side-reopen' title='Expand the sidebar'>&raquo;</button>"
        "<div class='main'><iframe id='frame' src='about:blank'></iframe></div>"
        "</div>" + SHELL_JS)
    return _page("Mirror of Go &middot; KataGo Review", body, SHELL_CSS)


SHELL_JS = r"""
<script>
(function(){
  var frame=document.getElementById('frame');
  var active=null;
  function enc(s){ return encodeURIComponent(s); }

  // Sidebar collapse / expand (state stored locally and reused next time)
  var app=document.querySelector('.app');
  function setCollapsed(c){
    app.classList.toggle('collapsed', c);
    try{ localStorage.setItem('ym_side_collapsed', c?'1':'0'); }catch(e){}
  }
  document.getElementById('btn-collapse').onclick=function(){ setCollapsed(true); };
  document.getElementById('side-reopen').onclick=function(){ setCollapsed(false); };
  try{ if(localStorage.getItem('ym_side_collapsed')==='1')
    app.classList.add('collapsed'); }catch(e){}
  // Narrow phone screens: collapse the sidebar by default so the report has room
  if(window.matchMedia && window.matchMedia('(max-width:760px)').matches){
    var saved=null; try{ saved=localStorage.getItem('ym_side_collapsed'); }catch(e){}
    if(saved===null) app.classList.add('collapsed');
  }
  function setActive(key){
    active=key;
    document.getElementById('btn-analyze').classList.toggle('on', key==='__analyze__');
    var bc=document.getElementById('btn-compare');
    if(bc) bc.classList.toggle('on', key==='__compare__');
    var bs=document.getElementById('btn-summary');
    if(bs) bs.classList.toggle('on', key==='__summary__');
    var bt=document.getElementById('btn-terms');
    if(bt) bt.classList.toggle('on', key==='__terms__');
    document.querySelectorAll('.repitem').forEach(function(el){
      el.classList.toggle('on', el.dataset.rel===key); });
  }
  function openAnalyze(){ frame.src='/analyze?embed=1'; setActive('__analyze__'); }
  function openCompare(){ frame.src='/compare?embed=1'; setActive('__compare__'); }
  function openSummary(){ frame.src='/summary?embed=1'; setActive('__summary__'); }
  function openTerms(){ frame.src='/terms?embed=1'; setActive('__terms__'); }
  function openReport(rel){ frame.src='/r/'+enc(rel)+'?embed=1&t='+Date.now();
    setActive(rel);
    if(window.matchMedia && window.matchMedia('(max-width:760px)').matches)
      setCollapsed(true); }
  function fmtMeta(s){
    var p=[s.games+' games'];
    if(s.wins||s.losses) p.push(s.wins+'W \u00b7 '+s.losses+'L');
    if(s.last_date) p.push(s.last_date);
    return p.join(' \u00b7 ');
  }
  function loadReports(){
    return fetch('/api/reports?t='+Date.now(),{cache:'no-store'})
    .then(function(r){return r.json();})
    .then(function(d){
      var reps=d.reports||[];
      document.getElementById('lh').textContent='Analysed reports ('+reps.length+')';
      var list=document.getElementById('replist'); list.innerHTML='';
      if(!reps.length){
        var e=document.createElement('div'); e.className='empty';
        e.textContent='No reports yet. Use "+ Analyse / import games" above to build your first one.';
        list.appendChild(e);
      }
      reps.forEach(function(r){
        var row=document.createElement('div'); row.className='repitem';
        row.dataset.rel=r.rel;
        var info=document.createElement('div'); info.className='info';
        var nm=document.createElement('div'); nm.className='nm'; nm.textContent=r.label;
        var mt=document.createElement('div'); mt.className='mt';
        mt.textContent=fmtMeta(r.summary||{games:0,wins:0,losses:0,last_date:''});
        info.appendChild(nm); info.appendChild(mt);
        info.onclick=function(){ openReport(r.rel); };
        var del=document.createElement('button'); del.className='del';
        del.title='Delete this report'; del.textContent='\uD83D\uDDD1';
        del.onclick=function(e){ e.stopPropagation(); doDelete(r.rel, r.label); };
        row.appendChild(info); row.appendChild(del);
        list.appendChild(row);
      });
      if(active) setActive(active);
      return reps;
    });
  }
  function doDelete(rel,label){
    if(!confirm('Delete the report "'+label+'"?\nThis removes every analysed file in that folder and cannot be undone.'))
      return;
    fetch('/api/delete',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({rel:rel})}).then(function(r){return r.json();})
    .then(function(d){
      if(d.error){ alert('Delete failed: '+d.error); return; }
      if(active===rel) openAnalyze();
      loadReports();
    }).catch(function(e){ alert('Delete failed: '+e); });
  }
  window.addEventListener('message', function(e){
    if(e.data && e.data.type==='ymdone'){
      loadReports().then(function(){ if(e.data.report) openReport(e.data.report); });
    }
  });
  document.getElementById('btn-analyze').onclick=openAnalyze;
  var _bc=document.getElementById('btn-compare'); if(_bc) _bc.onclick=openCompare;
  var _bs=document.getElementById('btn-summary'); if(_bs) _bs.onclick=openSummary;
  var _bt=document.getElementById('btn-terms'); if(_bt) _bt.onclick=openTerms;
  loadReports().then(function(reps){
    if(reps.length) openReport(reps[0].rel); else openAnalyze();
  });
})();
</script>
"""


def analyze_page(embed=False):
    if embed:
        body = ("<main style='margin-top:14px'><section class='card'>"
                "<div class='card-h'><h2>Analyse / import games</h2></div>"
                f"{_analysis_module_html()}</section></main>")
    else:
        body = (
            "<div class='hero'><a class='back' href='/'>&larr; Back to dashboard</a>"
            "<h1>Analyse / import games</h1>"
            "<p class='sub'>Download and analyse your Fox games, or import an already-analysed SGF.</p></div>"
            f"<main><section class='card'>{_analysis_module_html()}</section></main>")
    return _page("Analyse / import &middot; Mirror of Go", body)


# ---------------------------------------------------------------------------
# Compare two reports (e.g. 3 dan vs 4 dan) to see progress
# ---------------------------------------------------------------------------
def _report_metrics(rel):
    rdir = report_dir_from_rel(rel)
    if not rdir:
        return None
    cfg = _safe_cfg()
    games = report.load_games(rdir, cfg.get("games_dirs", []))
    if not games:
        return None
    agg = report.aggregate(games)
    pl, wl = [], []
    for g in games:
        for m in g.get("all_user_moves", []):
            pl.append(m.get("points_lost", 0) or 0)
            wl.append((m.get("winrate_lost", 0) or 0) * 100)
    try:
        source = report.source_label_from_path(rdir)
    except Exception:
        source = ""
    last_date = max((g.get("date") or "" for g in games), default="")
    wins, losses = agg["wins"], agg["losses"]
    winpct = (wins / (wins + losses) * 100) if (wins + losses) else 0.0
    # Lead conversion & comeback rate, by phase checkpoint
    lm = lmw = le = lew = 0
    bm = bmw = be = bew = 0
    for g in games:
        c = report.classify_trajectory(g)
        if not c:
            continue
        won = c["won"]
        md, ed = report._lead_flags(c["curve"])
        bd, bed = report._behind_flags(c["curve"])
        if md:
            lm += 1
            lmw += 1 if won else 0
        if ed:
            le += 1
            lew += 1 if won else 0
        if bd:
            bm += 1
            bmw += 1 if won else 0
        if bed:
            be += 1
            bew += 1 if won else 0
    return {
        "rel": rel, "label": rel, "source": source, "last_date": last_date,
        "n": agg["n"], "wins": wins, "losses": losses, "winpct": winpct,
        "apl": agg["avg_points_lost"], "brate": agg["blunder_rate"],
        "nb": agg["n_blunders"], "nb_per_game": (agg["n_blunders"] / agg["n"]
                                                 if agg["n"] else 0),
        "avg_moves": agg["avg_moves"], "n_moves": agg["n_user_moves"],
        "mid_conv": (lmw / lm * 100) if lm else None, "mid_led": lm,
        "end_conv": (lew / le * 100) if le else None, "end_led": le,
        "mid_come": (bmw / bm * 100) if bm else None, "mid_beh": bm,
        "end_come": (bew / be * 100) if be else None, "end_beh": be,
        "pl": pl, "wl": wl,
    }


A_COLOR, B_COLOR = "#4c6ef5", "#f76707"


def _cmp_hist_svg(av, bv, alab, blab, title, bin_size, x_note, thresh=None,
                  thresh_label=None, cap=None, pct=False, width=760, height=280):
    """Overlaid (grouped-bar) distribution of a per-move metric for two reports,
    each normalised to % of ITS OWN moves so different sample sizes are
    comparable.  Draws each report's mean line + the blunder threshold."""
    av = [v for v in av if v is not None]
    bv = [v for v in bv if v is not None]
    if not av and not bv:
        return ""
    meanA = sum(av) / len(av) if av else 0
    meanB = sum(bv) / len(bv) if bv else 0
    allv = av + bv
    if cap is not None:
        av = [min(v, cap) for v in av]
        bv = [min(v, cap) for v in bv]
        hi = cap
    else:
        hi = (int(max(allv) / bin_size) + 1) * bin_size
    lo = 0.0
    nbins = max(1, int((hi - lo) / bin_size + 0.5))

    def binned(vals):
        b = [0] * nbins
        for v in vals:
            i = int((v - lo) / bin_size)
            i = 0 if i < 0 else (nbins - 1 if i >= nbins else i)
            b[i] += 1
        tot = len(vals) or 1
        return [c / tot * 100 for c in b]  # percent of moves

    pa, pb = binned(av), binned(bv)
    ymax = max(pa + pb + [1])
    yscale = ymax * 1.18 or 1
    pad_l, pad_r, pad_t, pad_b = 46, 14, 44, 46
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    bw = plot_w / nbins

    def fmt(v):
        s = f"{v:.0f}" if abs(v - round(v)) < 1e-9 else f"{v:.1f}"
        return s + ("%" if pct else "")

    def py(v):
        return pad_t + (1 - v / yscale) * plot_h

    def px(v):
        x = pad_l + ((v - lo) / (hi - lo)) * plot_w
        return max(pad_l, min(pad_l + plot_w, x))

    p = [f'<svg viewBox="0 0 {width} {height}" width="100%" '
         f'preserveAspectRatio="xMidYMid meet" '
         f'style="background:#fff;border:1px solid #e3e3e3;border-radius:8px">']
    p.append(f'<text x="{pad_l}" y="20" font-size="14" font-weight="700" '
             f'fill="#1a202c">{_esc(title)}</text>')
    # legend
    lx = width - pad_r - 210
    for i, (lab, col) in enumerate([(alab, A_COLOR), (blab, B_COLOR)]):
        ly = 14 + i * 15
        p.append(f'<rect x="{lx}" y="{ly-8}" width="11" height="11" rx="2" '
                 f'fill="{col}" fill-opacity="0.85"/>')
        p.append(f'<text x="{lx+16}" y="{ly+1}" font-size="10.5" fill="#444">'
                 f'{_esc(lab)}</text>')
    for k in range(5):
        yval = yscale * k / 4
        y = py(yval)
        p.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" '
                 f'y2="{y:.1f}" stroke="#eee"/>')
        p.append(f'<text x="{pad_l-6}" y="{y+3:.1f}" font-size="10" '
                 f'text-anchor="end" fill="#888">{yval:.0f}%</text>')
    p.append(f'<text x="12" y="{pad_t-20}" font-size="10" fill="#888">share</text>')
    base = pad_t + plot_h

    def curve(series, col):
        pts = [(pad_l + (i + 0.5) * bw, py(series[i])) for i in range(nbins)]
        area = ("M " + f"{pts[0][0]:.1f},{base:.1f} "
                + " ".join(f"L {x:.1f},{y:.1f}" for x, y in pts)
                + f" L {pts[-1][0]:.1f},{base:.1f} Z")
        p.append(f'<path d="{area}" fill="{col}" fill-opacity="0.12"/>')
        p.append('<path d="M ' + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                 + f'" fill="none" stroke="{col}" stroke-width="2.2" '
                 f'stroke-linejoin="round"/>')
    curve(pa, A_COLOR)
    curve(pb, B_COLOR)
    step = max(1, nbins // 10)
    for i in range(0, nbins + 1, step):
        p.append(f'<text x="{pad_l + i*bw:.1f}" y="{height-pad_b+15:.1f}" '
                 f'font-size="9" fill="#888" text-anchor="middle">'
                 f'{fmt(lo + i*bin_size)}</text>')
    p.append(f'<text x="{pad_l+plot_w:.1f}" y="{height-pad_b+15:.1f}" '
             f'font-size="9" fill="#888" text-anchor="middle">'
             f'{fmt(hi)}{"+" if cap is not None else ""}</text>')
    if thresh is not None and lo <= thresh <= hi:
        tx = px(thresh)
        p.append(f'<line x1="{tx:.1f}" y1="{pad_t:.1f}" x2="{tx:.1f}" '
                 f'y2="{pad_t+plot_h:.1f}" stroke="#e03131" stroke-width="1.3" '
                 f'stroke-dasharray="4 3"/>')
        if thresh_label:
            p.append(f'<text x="{tx+4:.1f}" y="{pad_t+34:.1f}" font-size="10" '
                     f'fill="#e03131" font-weight="700">{_esc(thresh_label)}</text>')
    for mean, col in ((meanA, A_COLOR), (meanB, B_COLOR)):
        mx = px(mean)
        p.append(f'<line x1="{mx:.1f}" y1="{pad_t:.1f}" x2="{mx:.1f}" '
                 f'y2="{pad_t+plot_h:.1f}" stroke="{col}" stroke-width="1.6" '
                 f'stroke-dasharray="5 4"/>')
        p.append(f'<text x="{mx+3:.1f}" y="{pad_t+12:.1f}" font-size="10" '
                 f'fill="{col}" font-weight="700">mean {fmt(mean)}</text>')
    p.append(f'<text x="{pad_l}" y="{height-8}" font-size="10" fill="#888">'
             f'{_esc(x_note)}</text>')
    p.append("</svg>")
    return "".join(p)


def _cmp_select(cur, other_param_val, which):
    opts = []
    for r in list_reports():
        sel = " selected" if r["rel"] == cur else ""
        opts.append(f'<option value="{_esc(r["rel"])}"{sel}>{_esc(r["label"])}'
                    f'</option>')
    return (f"<select class='cmpsel' data-which='{which}' "
            f"data-other='{_esc(other_param_val)}'>{''.join(opts)}</select>")


NEUTRAL_PCT = 4.0   # changes smaller than this are treated as ≈ flat (noise)


def _delta_cell(a, b, lower_better, fmt="{:.2f}", suffix=""):
    """A colored delta cell.  green = B improved over A, red = got worse, gray =
    negligible (|Δ| < NEUTRAL_PCT%) or a neutral metric (lower_better is None,
    e.g. game length).  For a metric where lower is better, a HIGHER value is
    worse (red); this matches points lost per move, where lower is better."""
    d = b - a
    if abs(d) < 1e-9:
        return "<td class='dl dl-flat'>flat</td>"
    pct = (abs(d) / a * 100) if a else 0
    sign = "" if d < 0 else "+"
    arrow = "▼" if d < 0 else "▲"
    val = f"{sign}{fmt.format(d)}{suffix}"
    # neutral metric, or a change too small to matter → gray, no good/bad
    if lower_better is None or pct < NEUTRAL_PCT:
        mark = arrow if lower_better is None else "≈"
        return (f"<td class='dl dl-flat'>{mark} {val}"
                f"<span class='dlp'>{pct:.0f}%</span></td>")
    improved = (d < 0) if lower_better else (d > 0)
    cls = "dl-good" if improved else "dl-bad"
    return (f"<td class='dl {cls}'>{arrow} {val}"
            f"<span class='dlp'>{pct:.0f}%</span></td>")


def compare_page(a, b, embed=False):
    reps = list_reports()
    rels = [r["rel"] for r in reps]
    # defaults: two reports ordered older -> newer by last game date
    if not (a and b):
        by_date = sorted(reps, key=lambda r: r["summary"].get("last_date") or "")
        if len(by_date) >= 2:
            a = a or by_date[-2]["rel"]
            b = b or by_date[-1]["rel"]
        elif reps:
            a = a or reps[0]["rel"]
            b = b or reps[0]["rel"]
    ma, mb = _report_metrics(a), _report_metrics(b)
    head = ("" if embed else
            "<div class='hero'><a class='back' href='/'>&larr; Back to dashboard</a>"
            "<h1>Compare reports &middot; track progress</h1>"
            "<p class='sub'>Pick two reports and compare points lost per move, blunder rate and distributions.</p></div>")
    if not ma or not mb:
        body = (head + "<main><section class='card'>"
                "<div class='card-h'><h2>Report comparison</h2></div>"
                f"<div class='cmpbar'>A {_cmp_select(a, b or '', 'a')} "
                f"vs B {_cmp_select(b, a or '', 'b')}</div>"
                "<p class='empty'>Pick two reports that contain games.</p>"
                "</section></main>")
        return _page("Report comparison &middot; Mirror of Go", body, COMPARE_CSS)

    la = f"A - {ma['label']}" + (f" ({ma['source']})" if ma['source'] else "")
    lb = f"B - {mb['label']}" + (f" ({mb['source']})" if mb['source'] else "")

    # verdict from apl (avg points lost per move), lower is better
    da = mb["apl"] - ma["apl"]
    pct = (abs(da) / ma["apl"] * 100) if ma["apl"] else 0
    if da <= -0.05 and pct >= 5:
        vcls, vt, arr = "imp-good", "Improved", "&#9660;"
    elif da >= 0.05 and pct >= 5:
        vcls, vt, arr = "imp-bad", "Slipped", "&#9650;"
    else:
        vcls, vt, arr = "imp-flat", "Roughly flat", "&rarr;"
    direction = "down" if da < 0 else ("up" if da > 0 else "flat")
    verdict = (
        f"<div class='improve {vcls}'>"
        f"<div class='impl'>Progress verdict &middot; avg points lost per move (A &rarr; B)</div>"
        f"<div class='impv'><span class='ar'>{arr}</span>{vt}"
        f"<span class='pct'>{pct:.0f}%</span></div>"
        f"<div class='impd'>From <b>{_esc(ma['label'])}</b> to <b>{_esc(mb['label'])}</b>, "
        f"average points lost per move went {direction} from <b>{ma['apl']:.2f}</b> to "
        f"<b>{mb['apl']:.2f}</b> "
        f"({'losing' if da<0 else 'losing an extra'} {abs(da):.2f} pts/move). "
        f"The lower the loss per move, the steadier your play.</div></div>")

    # comparison table
    def row(label, av, bv, lower_better, fmt="{:.2f}", suffix=""):
        return (f"<tr><td class='ml'>{_esc(label)}</td>"
                f"<td>{fmt.format(av)}{suffix}</td>"
                f"<td>{fmt.format(bv)}{suffix}</td>"
                f"{_delta_cell(av, bv, lower_better, fmt, suffix)}</tr>")

    def conv_row(label, av, an, bv, bn):
        def cell(v, n):
            return (f"{v:.0f}% <span class='sub2'>({n})</span>"
                    if v is not None else "—")
        if av is None or bv is None:
            delta = "<td class='dl dl-flat'>—</td>"
        else:
            delta = _delta_cell(av, bv, False, "{:.0f}", "%")  # higher = better
        return (f"<tr><td class='ml'>{_esc(label)}</td>"
                f"<td>{cell(av, an)}</td><td>{cell(bv, bn)}</td>{delta}</tr>")
    table = (
        "<table class='cmp'><thead><tr><th></th>"
        f"<th>{_esc(ma['label'])}</th><th>{_esc(mb['label'])}</th>"
        "<th>Change (A&rarr;B)</th></tr></thead><tbody>"
        f"<tr><td class='ml'>Games / moves</td><td>{ma['n']} games &middot; {ma['n_moves']} moves</td>"
        f"<td>{mb['n']} games &middot; {mb['n_moves']} moves</td><td class='dl dl-flat'>&mdash;</td></tr>"
        + row("Win rate", ma["winpct"], mb["winpct"], False, "{:.0f}", "%")
        + conv_row("Middlegame lead conversion", ma["mid_conv"], ma["mid_led"],
                   mb["mid_conv"], mb["mid_led"])
        + conv_row("Yose lead conversion", ma["end_conv"], ma["end_led"],
                   mb["end_conv"], mb["end_led"])
        + conv_row("Middlegame comeback rate", ma["mid_come"], ma["mid_beh"],
                   mb["mid_come"], mb["mid_beh"])
        + conv_row("Yose comeback rate", ma["end_come"], ma["end_beh"],
                   mb["end_come"], mb["end_beh"])
        + row("Avg points lost per move", ma["apl"], mb["apl"], True, "{:.2f}")
        + row("Blunder rate (&ge;6 pts / WR &minus;15%)", ma["brate"], mb["brate"], True, "{:.1f}", "%")
        + row("Blunders per game", ma["nb_per_game"], mb["nb_per_game"], True, "{:.1f}")
        + row("Avg moves per game", ma["avg_moves"], mb["avg_moves"], False, "{:.0f}")
        + "</tbody></table>")

    apl_hist = _cmp_hist_svg(
        ma["pl"], mb["pl"], la, lb,
        "Points lost per move (distribution, share of moves)", 0.5,
        "x-axis: points lost on a single move (0.5-pt bins, 15+ pooled); "
        "the red dashed line is the 6-pt blunder line",
        thresh=6, thresh_label="blunder line 6 pts", cap=15)
    wl_hist = _cmp_hist_svg(
        ma["wl"], mb["wl"], la, lb,
        "Win-rate lost per move (distribution, share of moves)", 2.5,
        "x-axis: win-rate drop on a single move (2.5% bins, 50%+ pooled); "
        "the red dashed line is the 15% blunder line",
        thresh=15, thresh_label="blunder line 15%", cap=50, pct=True)

    body = (
        head + "<main>"
        "<section class='card'><div class='card-h'><h2>Choose two reports to compare</h2></div>"
        f"<div class='cmpbar'>A {_cmp_select(a, b, 'a')} "
        f"<span class='vs'>vs</span> B {_cmp_select(b, a, 'b')}</div></section>"
        f"<section class='card'>{verdict}{table}</section>"
        f"<section class='card'>{apl_hist}</section>"
        f"<section class='card'>{wl_hist}</section>"
        "</main>"
        "<script>document.querySelectorAll('.cmpsel').forEach(function(sel){"
        "sel.addEventListener('change',function(){"
        "var w=this.dataset.which, other=this.dataset.other, v=this.value;"
        "var a=(w==='a')?v:other, b=(w==='b')?v:other;"
        "var e=/[?&]embed=1/.test(location.search)?'&embed=1':'';"
        "location.href='/compare?a='+encodeURIComponent(a)+'&b='+encodeURIComponent(b)+e;"
        "});});</script>")
    return _page("Report comparison &middot; Mirror of Go", body, COMPARE_CSS)


def summary_page(rel=None, embed=False):
    reps = list_reports()
    if not rel and reps:
        rel = reps[0]["rel"]
    opts = "".join(
        f"<option value='{_esc(r['rel'])}'{' selected' if r['rel']==rel else ''}>"
        f"{_esc(r['label'])}</option>" for r in reps)
    cached = load_summary(rel) if rel else ""
    inner = (_md_to_html(cached) if cached else
             "<p class='empty'>Nothing generated yet. Press <b>Generate / refresh</b> "
             "above to send this report's review notes (including the voice "
             "transcript) to DeepSeek, which derives your own weakness categories "
             "and training priorities.</p>")
    head = ("" if embed else
            "<div class='hero'><a class='back' href='/'>&larr; Back to dashboard</a>"
            "<h1>Review summary &middot; diagnostic profile</h1>"
            "<p class='sub'>Collapses scattered mistakes into root-cause categories and training priorities.</p></div>")
    body = (
        head + "<main>"
        "<section class='card'><div class='card-h'><h2>Diagnostic profile</h2></div>"
        f"<div class='cmpbar'>Report <select id='sumRep' class='cmpsel'>{opts}</select>"
        "<button class='sumgen' id='sumGen'>&#10227; Generate / refresh summary</button>"
        f"<a class='sumexp' id='sumExp' download "
        f"href='/api/summary_export?report={quote(rel or '')}'>&#8681; Export all "
        f"versions</a>"
        "<span id='sumStat' class='nstat'></span></div>"
        "<p class='hint'>Built from the reviews you spoke into the recorder in the "
        "blunder set, plus this report's lead conversion and comeback rate. DeepSeek "
        "derives your own weakness categories straight from your notes and diagnoses "
        "them. The result is saved into that report folder, so next time it loads "
        "instantly without recomputing.</p></section>"
        f"<section class='card'><div id='sumBody' class='smdbox'>{inner}</div>"
        f"<div id='sumHist'>{summary_history_html(rel) if rel else ''}</div>"
        "</section>"
        "</main>" + SUMMARY_JS)
    return _page("Review summary &middot; Mirror of Go", body, SUMMARY_CSS)


# ---------------------------------------------------------------------------
# Go terminology dictionary (/terms) — English names for the Chinese terms
# ---------------------------------------------------------------------------
def terms_page(embed=False):
    """Searchable English/Chinese Go glossary.  Data lives in go_terms.py; the
    filtering is pure client-side JS so the page also works from a saved copy."""
    groups = go_terms.by_category()
    total = sum(len(rows) for _, _, rows in groups)

    chips = ["<button class='navbtn on' data-fc='all'>All "
             f"<i>{total}</i></button>"]
    for cid, label, rows in groups:
        chips.append(f"<button class='navbtn' data-fc='{cid}'>{label} "
                     f"<i>{len(rows)}</i></button>")

    secs = []
    for cid, label, rows in groups:
        trs = []
        for _c, en, zh, py, say, meaning in rows:
            # Everything searchable goes into one lowercase haystack: the English
            # term, the Chinese, its pinyin, and the definition text.  Markup is
            # stripped first, or a search for "b" would hit every <b> tag.
            plain = re.sub(r"<[^>]+>", "", meaning)
            hay = _esc(" ".join((en, zh, py, plain)).lower())
            say_html = (f"<span class='tsay'>{_esc(say)}</span>" if say else "")
            trs.append(
                f"<tr class='trow' data-c='{cid}' data-s=\"{hay}\">"
                f"<td class='ten'><b>{_esc(en)}</b>{say_html}</td>"
                f"<td class='tzh'>{_esc(zh)}<span class='tpy'>{_esc(py)}</span></td>"
                f"<td class='tdef'>{meaning}</td></tr>")
        secs.append(
            f"<section class='card tsec' data-c='{cid}'>"
            f"<div class='card-h'><h2>{label}</h2>"
            f"<span class='nstat'>{len(rows)} terms</span></div>"
            "<table class='tterm'><thead><tr>"
            "<th>English</th><th>Chinese</th><th>What it means</th>"
            "</tr></thead><tbody>"
            + "".join(trs) + "</tbody></table></section>")

    head = ("" if embed else
            "<div class='hero'><a class='back' href='/'>&larr; Back to dashboard</a>"
            "<h1>Go terms &middot; Chinese to English</h1>"
            "<p class='sub'>The English name for every move, shape and idea you "
            "already know in Chinese.</p></div>")
    body = (
        head + "<main>"
        "<section class='card'>"
        "<div class='card-h'><h2>Terminology dictionary</h2>"
        f"<span class='nstat'>{total} terms</span></div>"
        "<p class='hint' style='margin:0 0 10px'>Most English Go vocabulary is "
        "borrowed from Japanese, which is why the spelling rarely matches the "
        "sound &mdash; so each term shows how to say it. Search in "
        "<b>English</b>, <b>Chinese</b> or <b>pinyin</b> (no IME needed: type "
        "<code>shoujin</code> to find 手筋).</p>"
        "<input type='text' id='tq' class='tsearch' autocomplete='off' "
        "placeholder='Search terms, e.g. tesuji / 手筋 / shoujin / liberty'>"
        "<div class='navbar' style='margin-top:10px'>"
        "<div class='navrow'><span class='navlbl'>Category</span>"
        + "".join(chips) + "</div></div>"
        "<div class='flcount' id='tcount' style='margin:10px 0 0'></div>"
        "</section>"
        + "".join(secs) +
        "<section class='card' id='tnone' style='display:none'>"
        "<p class='empty'>Nothing matches that search.</p></section>"
        "</main>" + TERMS_JS)
    return _page("Go terms &middot; Mirror of Go", body, TERMS_CSS)


TERMS_CSS = r"""
.tsearch{width:100%;padding:11px 13px;border:1px solid var(--amber-line);
  border-radius:10px;font-size:14.5px;background:#fff;color:var(--ink)}
.tsearch:focus{outline:none;border-color:var(--amber);
  box-shadow:0 0 0 3px rgba(183,121,31,.13)}
.navbar{display:flex;flex-direction:column;gap:6px}
.navrow{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.navlbl{flex:none;width:74px;font-size:11.5px;color:var(--muted);font-weight:700}
.navbtn{border:1px solid var(--line);background:var(--card);color:var(--ink-soft);
  border-radius:20px;padding:5px 11px;font-size:12.5px;cursor:pointer;
  font-family:inherit}
.navbtn:hover{border-color:var(--amber);color:var(--amber-ink)}
.navbtn.on{background:var(--espresso);border-color:var(--espresso);color:#fff}
.navbtn i{font-style:normal;opacity:.65;font-size:11px;margin-left:3px}
.flcount{font-size:12.5px;color:var(--ink-soft);font-weight:600}
.nstat{color:var(--muted);font-size:12.5px}
.hint{color:var(--muted);font-size:12.5px;line-height:1.6}
.hint code{background:var(--amber-soft);padding:1px 5px;border-radius:4px}
.empty{color:var(--muted);font-size:13px;padding:8px 2px}
table.tterm{width:100%;border-collapse:collapse;font-size:14px}
table.tterm th{font-size:11.5px;color:var(--muted);font-weight:700;text-align:left;
  padding:0 10px 7px;border-bottom:1px solid var(--amber-line);white-space:nowrap}
table.tterm td{padding:10px;border-bottom:1px solid var(--line-soft);
  vertical-align:top;line-height:1.65}
table.tterm tr:last-child td{border-bottom:none}
table.tterm tr.trow:hover td{background:#fbf7ef}
td.ten{width:23%;min-width:150px}
td.ten b{font-size:14.5px;color:var(--espresso)}
.tsay{display:block;font-size:11.5px;color:var(--amber-ink);margin-top:2px;
  letter-spacing:.02em}
td.tzh{width:17%;min-width:104px;font-size:15px;color:var(--ink)}
.tpy{display:block;font-size:11.5px;color:var(--muted);margin-top:2px}
td.tdef{color:var(--ink-soft);font-size:13.5px}
td.tdef b{color:var(--ink)}
@media (max-width:760px){
  table.tterm thead{display:none}
  table.tterm td{display:block;border:none;padding:2px 0}
  table.tterm tr.trow{display:block;padding:10px 0;
    border-bottom:1px solid var(--line-soft)}
  td.ten,td.tzh{width:auto}
}
"""


TERMS_JS = r"""
<script>
(function(){
  var q=document.getElementById('tq');
  var cnt=document.getElementById('tcount');
  var none=document.getElementById('tnone');
  var rows=[].slice.call(document.querySelectorAll('tr.trow'));
  var secs=[].slice.call(document.querySelectorAll('section.tsec'));
  var btns=[].slice.call(document.querySelectorAll('.navbtn[data-fc]'));
  var cat='all';

  function apply(){
    var term=(q.value||'').trim().toLowerCase();
    var shown=0;
    rows.forEach(function(r){
      var okc=(cat==='all'||r.dataset.c===cat);
      var okq=(!term||r.dataset.s.indexOf(term)>=0);
      var vis=okc&&okq;
      r.style.display=vis?'':'none';
      if(vis) shown++;
    });
    // Hide a category card entirely when none of its rows survive the filter.
    var liveSecs=0;
    secs.forEach(function(s){
      var any=[].slice.call(s.querySelectorAll('tr.trow'))
        .some(function(r){ return r.style.display!=='none'; });
      s.style.display=any?'':'none';
      if(any) liveSecs++;
    });
    none.style.display=shown?'none':'';
    cnt.textContent=(term||cat!=='all')
      ? (shown+' of '+rows.length+' terms'+(liveSecs>1?' in '+liveSecs+' categories':''))
      : (rows.length+' terms');
  }
  q.addEventListener('input', apply);
  // Esc clears the box, so you can get back to the full list one-handed.
  q.addEventListener('keydown', function(e){
    if(e.key==='Escape'){ q.value=''; apply(); }
  });
  btns.forEach(function(b){
    b.onclick=function(){
      cat=b.dataset.fc;
      btns.forEach(function(x){ x.classList.toggle('on', x===b); });
      apply();
      if(cat!=='all'){
        var s=document.querySelector("section.tsec[data-c='"+cat+"']");
        if(s) s.scrollIntoView({behavior:'smooth',block:'start'});
      }
    };
  });
  apply();
  q.focus();
})();
</script>
"""


SUMMARY_JS = r"""
<script>
(function(){
  var sel=document.getElementById('sumRep');
  var gen=document.getElementById('sumGen');
  var stat=document.getElementById('sumStat');
  var box=document.getElementById('sumBody');
  var embed=/[?&]embed=1/.test(location.search);
  function rel(){ return sel? sel.value : ''; }
  if(sel) sel.addEventListener('change', function(){
    var e=embed?'&embed=1':'';
    location.href='/summary?report='+encodeURIComponent(rel())+e;
  });
  if(gen) gen.onclick=function(){
    gen.disabled=true;
    stat.textContent='Generating... (DeepSeek analysis, usually 20\u201360s -- keep this page open)';
    fetch('/api/summary',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({report:rel()})})
    .then(function(r){return r.json();})
    .then(function(d){
      gen.disabled=false;
      if(d.error){ stat.textContent='Failed: '+d.error; return; }
      box.innerHTML=d.html||'';
      // The version just generated moves into the archive, so refresh the list.
      var h=document.getElementById('sumHist');
      if(h) h.innerHTML=d.history||'';
      stat.textContent='Updated \u2713 \u00b7 the previous one is kept below';
    }).catch(function(e){ gen.disabled=false; stat.textContent='Failed: '+e; });
  };
})();
</script>
"""


SUMMARY_CSS = r"""
.cmpbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:14px}
.cmpsel{padding:8px 9px;border:1px solid var(--amber-line);border-radius:8px;
  font-size:13px;background:#fff;max-width:42vw}
.sumgen{border:1px solid var(--amber);background:var(--amber);color:#fff;
  border-radius:8px;padding:8px 14px;font-size:13px;font-weight:700;cursor:pointer}
.sumgen:hover{filter:brightness(1.05)}
.sumgen:disabled{opacity:.55;cursor:default}
.sumexp{border:1px solid var(--amber-line);background:var(--card);
  color:var(--amber-ink);border-radius:8px;padding:8px 14px;font-size:13px;
  font-weight:700;cursor:pointer;text-decoration:none}
.sumexp:hover{background:var(--amber-soft)}
.sumhist{margin-top:26px;padding-top:16px;border-top:1px solid var(--amber-line)}
.sumhist-h{font-size:13px;font-weight:700;color:var(--ink-soft);
  margin-bottom:8px;display:flex;align-items:center;gap:8px}
.sumver{border:1px solid var(--line);border-radius:10px;margin-bottom:8px;
  background:var(--card)}
.sumver>summary{cursor:pointer;padding:9px 13px;font-size:13px;font-weight:600;
  color:var(--ink-soft);list-style:none}
.sumver>summary::-webkit-details-marker{display:none}
.sumver>summary::before{content:'\25B8';margin-right:8px;color:var(--muted)}
.sumver[open]>summary::before{content:'\25BE'}
.sumver>summary:hover{color:var(--amber-ink)}
.sumver[open]>summary{border-bottom:1px solid var(--line-soft)}
.sumver .smdbox{padding:4px 16px 14px}
.nstat{color:var(--muted);font-size:12.5px}
.hint{color:var(--muted);font-size:12.5px;margin:10px 0 0;line-height:1.6}
.smdbox{font-size:14.5px;line-height:1.75;color:var(--ink)}
.smdbox h1{font-size:22px;margin:6px 0 12px}
.smdbox h2{font-size:18px;margin:22px 0 8px;padding-top:6px;
  border-top:1px solid var(--amber-line)}
.smdbox h3{font-size:15.5px;margin:16px 0 6px;color:var(--espresso)}
.smdbox h4{font-size:14px;margin:12px 0 4px;color:var(--muted)}
.smdbox p{margin:8px 0}
.smdbox ul,.smdbox ol{margin:8px 0;padding-left:22px}
.smdbox li{margin:3px 0}
.smdbox blockquote{margin:10px 0;padding:8px 14px;border-left:3px solid var(--amber);
  background:var(--amber-soft);color:var(--espresso);border-radius:0 8px 8px 0}
.smdbox hr{border:0;border-top:1px solid var(--amber-line);margin:18px 0}
.smdbox code{background:var(--amber-soft);padding:1px 5px;border-radius:4px;
  font-size:13px}
table.smd{width:100%;border-collapse:collapse;margin:12px 0;font-size:13.5px}
table.smd th,table.smd td{border:1px solid var(--amber-line);padding:7px 9px;
  text-align:left;vertical-align:top}
table.smd thead th{background:var(--amber-soft);color:var(--espresso);
  font-weight:700}
table.smd tbody tr:nth-child(even){background:#fbf7ef}
"""


COMPARE_CSS = r"""
.cmpbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:14px}
.cmpbar .vs{color:#a0aec0;font-weight:700}
.cmpsel{padding:8px 9px;border:1px solid #cdd3da;border-radius:8px;font-size:13px;
  background:#fff;max-width:42vw}
table.cmp{width:100%;border-collapse:collapse;margin-top:12px;font-size:14px}
table.cmp th,table.cmp td{padding:9px 10px;text-align:right;border-bottom:1px solid #eef1f4}
table.cmp th{font-size:12px;color:#718096;font-weight:600}
table.cmp td.ml,table.cmp th:first-child{text-align:left}
table.cmp td.ml{color:var(--ink-soft);font-weight:600}
table.cmp td .sub2{color:var(--muted);font-size:11px;font-weight:400}
td.dl{font-weight:700;white-space:nowrap}
td.dl-good{color:#2f855a}td.dl-bad{color:#c53030}td.dl-flat{color:var(--muted);font-weight:600}
td.dl .dlp{margin-left:6px;font-size:11px;opacity:.75;font-weight:600}
.improve{padding:14px 16px;border-radius:12px;border:1px solid #e3e7eb;margin-bottom:6px}
.improve .impl{font-size:12px;color:#718096;font-weight:600}
.improve .impv{font-size:22px;font-weight:800;margin:4px 0;display:flex;
  align-items:center;gap:10px}
.improve .impv .ar{font-size:20px}
.improve .impv .pct{font-size:15px;font-weight:700;opacity:.8}
.improve .impd{font-size:13px;color:#4a5568;line-height:1.7}
.improve.imp-good{background:#e9f7ef;border-color:#a7e0be}
.improve.imp-good .impv{color:#2f855a}
.improve.imp-bad{background:#fdecea;border-color:#f5b5ac}
.improve.imp-bad .impv{color:#c53030}
.improve.imp-flat{background:var(--line-soft,#f1ead9)}
.improve.imp-flat .impv{color:var(--ink-soft,#6f6357)}
"""


# ---------------------------------------------------------------------------
# Static export: an index.html that opens without the server (view only -- analysing
# and importing still need the app running)
# ---------------------------------------------------------------------------
STATIC_CSS = r"""
:root{
  --paper:#f6f1e8; --card:#fffdf9; --line:#e9dfce;
  --ink:#3d352e; --ink-soft:#6f6357; --muted:#9a8d7b;
  --espresso:#2a241f; --on-dark-soft:#b0a18d;
  --amber:#b7791f; --amber-ink:#8a5a12; --amber-soft:#f6ecd6; --amber-line:#e6d3ab;}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Segoe UI",sans-serif}
.hero{background:var(--espresso);color:#fff;padding:22px 26px}
.hero h1{margin:0;font-size:22px}
.hero .sub{margin:5px 0 0;color:var(--on-dark-soft);font-size:13px}
main{max-width:1080px;margin:22px auto;padding:0 18px 60px}
.note{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--amber);
  border-radius:10px;padding:13px 16px;margin-bottom:24px;font-size:13.5px;
  color:var(--ink-soft);line-height:1.7}
.note b{color:var(--ink)}
.note code{background:var(--amber-soft);border-radius:5px;padding:1px 6px;font-size:12.5px}
.sec{font-size:15px;color:var(--ink-soft);margin:0 2px 12px;font-weight:700}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(248px,1fr));gap:14px}
.rep{display:block;background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:15px 16px;text-decoration:none;color:var(--ink);transition:.12s}
.rep:hover{border-color:var(--amber);box-shadow:0 4px 14px rgba(183,121,31,.14);
  transform:translateY(-1px)}
.rep .nm{font-weight:700;font-size:14.5px;word-break:break-all}
.rep .tag{display:inline-block;margin-top:6px;font-size:11px;color:var(--amber-ink);
  background:var(--amber-soft);border-radius:20px;padding:2px 9px}
.rep .meta{margin-top:10px;font-size:12.5px;color:var(--ink-soft);
  display:flex;justify-content:space-between;gap:8px}
.rep .rec{margin-top:4px;font-size:12px;color:var(--muted)}
.rep .big{font-size:20px;font-weight:800;color:var(--ink);font-variant-numeric:tabular-nums}
.empty{color:var(--muted);font-size:13px;padding:8px 2px}
"""


def _static_card_html(r):
    s = r["summary"]
    rec = f"{s['wins']}W &middot; {s['losses']}L" if (s["wins"] or s["losses"]) else ""
    date = f"latest {s['last_date']}" if s["last_date"] else ""
    tag = f"<div class='tag'>{_esc(s['source'])}</div>" if s["source"] else ""
    href = quote(r["rel"]) + "/review_report.html"
    return (f"<a class='rep' href='{href}'>"
            f"<div class='nm'>{_esc(r['label'])}</div>{tag}"
            f"<div class='meta'><span><span class='big'>{s['games']}</span> games</span>"
            f"<span>{_esc(date)}</span></div>"
            f"<div class='rec'>{_esc(rec)}</div></a>")


def build_static_index():
    """A standalone dashboard that opens via file:// (no server).  Report cards
    link directly to each folder's review_report.html.  Analysis/import is not
    available here — it needs the local program running."""
    reps = [r for r in list_reports() if r["has_html"]]
    cards = "".join(_static_card_html(r) for r in reps) or \
        "<div class='empty'>No reports yet. Start the app and run an analysis.</div>"
    today = datetime.date.today().isoformat()
    body = (
        "<div class='hero'><h1>Mirror of Go &middot; KataGo Review</h1>"
        f"<p class='sub'>Offline viewer &middot; {len(reps)} reports &middot; {today}</p></div>"
        "<main>"
        "<div class='note'>This is the <b>offline viewer</b> -- it opens even after "
        "you close the terminal. To <b>download, analyse or import new games</b>, "
        "double-click <code>Mirror of Go.command</code> to start the app (which opens "
        "the full interface).</div>"
        f"<div class='sec'>Analysed reports ({len(reps)})</div>"
        f"<div class='grid'>{cards}</div>"
        "</main>")
    return ("<!doctype html><html lang=\"zh\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>Mirror of Go &middot; KataGo Review</title>"
            f"<style>{STATIC_CSS}</style></head><body>{body}</body></html>")


def write_static_index():
    """Write/refresh index.html next to the report folders.  Best-effort."""
    try:
        path = os.path.join(HERE, "index.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(build_static_index())
        return path
    except Exception:
        return None


def _report_nav_html(current_rel):
    reports = list_reports()
    opts = []
    for r in reports:
        sel = " selected" if r["rel"] == current_rel else ""
        opts.append(f'<option value="{_esc(r["rel"])}"{sel}>'
                    f'{_esc(r["label"])}</option>')
    options = "".join(opts) or '<option value="">(No reports yet)</option>'
    return ("<style>body{padding-top:48px!important}"
            "#ymnav{position:fixed;top:0;left:0;right:0;height:48px;z-index:99999;"
            "background:var(--espresso,#2a241f);color:#fff;display:flex;"
            "align-items:center;gap:14px;"
            "padding:0 16px;font-family:-apple-system,'PingFang SC',sans-serif;"
            "box-shadow:0 1px 6px rgba(42,36,31,.3)}"
            "#ymnav a{color:#fff;text-decoration:none;font-weight:600;font-size:14px}"
            "#ymnav a:hover{opacity:.8}#ymnav .sep{opacity:.35}"
            "#ymnav select{margin-left:auto;padding:6px 8px;border-radius:7px;"
            "border:none;font-size:13px;max-width:52vw}</style>"
            "<div id='ymnav'><a href='/'>&larr; Dashboard</a><span class='sep'>|</span>"
            "<a href='/analyze'>+ Analyse / import</a>"
            f"<select id='ymnav-rep' title='Switch report'>{options}</select></div>"
            "<script>document.getElementById('ymnav-rep').onchange=function(){"
            "if(this.value) location.href='/r/'+encodeURIComponent(this.value);};"
            "</script>")


def render_report(rel, embed=False):
    """Read a report's HTML; inject the slim top nav bar unless embedded in the
    dashboard shell (the sidebar already provides navigation)."""
    rdir = report_dir_from_rel(rel)
    if not rdir:
        return None
    html_path = os.path.join(rdir, "review_report.html")
    if not os.path.exists(html_path):
        return None
    with open(html_path, encoding="utf-8") as f:
        doc = f.read()
    if embed:
        return doc
    nav = _report_nav_html(rel)
    lower = doc.lower()
    idx = lower.find("<body")
    if idx != -1:
        end = doc.find(">", idx)
        if end != -1:
            return doc[:end + 1] + nav + doc[end + 1:]
    if "</head>" in doc:
        return doc.replace("</head>", "</head>" + nav, 1)
    return nav + doc


# ---------------------------------------------------------------------------
# Job implementations
# ---------------------------------------------------------------------------
def _safe_cfg():
    try:
        return pipeline.load_config()
    except Exception:
        return {}


def _reload_app_modules():
    """Pick up on-disk code changes (report.py, import_lizzie.py, …) without
    restarting the long-running server.  importlib.reload updates each module
    in place, so existing references (web_app.report, import_lizzie.report, …)
    all see the new code.  Dependencies are reloaded before their dependents."""
    import importlib
    for name in ("appconfig", "sgfparse", "estimate_score", "analyze",
                 "report", "import_lizzie", "pipeline", "go_terms"):
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


_BOARD_GAMES = {}   # (rdir, mtime) -> games list, so repeated zooms are fast


def render_board_svg(rel, game_file, move):
    """Regenerate one blunder's full-board SVG on demand (for the lazy zoom)."""
    rdir = report_dir_from_rel(rel or "")
    if not rdir:
        return None
    try:
        mvn = int(move)
    except (TypeError, ValueError):
        return None
    key = (rdir, os.path.getmtime(rdir))
    games = _BOARD_GAMES.get(key)
    if games is None:
        games = report.load_games(rdir, _safe_cfg().get("games_dirs", []))
        _BOARD_GAMES.clear()
        _BOARD_GAMES[key] = games
    g = next((x for x in games if x.get("filename") == game_file), None)
    if not g:
        return None
    m = next((x for x in g.get("all_user_moves", [])
              if x.get("move_number") == mvn), None)
    if not m:
        return None
    try:
        return report.full_board_svg(g, m, "bd")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Voice notes: transcription with a local faster-whisper model
# ---------------------------------------------------------------------------
_WHISPER = None
_WHISPER_ERR = None


def _get_whisper():
    global _WHISPER, _WHISPER_ERR
    if _WHISPER is not None:
        return _WHISPER
    if _WHISPER_ERR is not None:
        return None
    path = os.path.expanduser((_safe_cfg().get("whisper_model") or "").strip())
    if not path or not os.path.isdir(path):
        _WHISPER_ERR = ("Speech model folder not found (whisper_model in "
                        "config.json): " + (path or "not configured"))
        return None
    try:
        from faster_whisper import WhisperModel
    except Exception as e:  # noqa: BLE001
        _WHISPER_ERR = f"faster-whisper is not installed (pip install faster-whisper): {e}"
        return None
    try:
        print("Loading the speech model (slow the first time)...")
        _WHISPER = WhisperModel(path, device="cpu", compute_type="int8")
        print("Speech model ready.")
    except Exception as e:  # noqa: BLE001
        _WHISPER_ERR = f"Could not load the speech model: {e}"
        return None
    return _WHISPER


DEFAULT_VOICE_AUDIO_DIR = "~/Desktop/English Coach/VideoAudioFiles"


def voice_audio_dir():
    """Where recordings are kept, from config's `voice_audio_dir`.

    Recordings are deliberately stored OUTSIDE the report folders so another
    project (the English-coaching one) can consume them without reaching into
    go_review.  Set the key to "" to go back to discarding audio after
    transcription."""
    raw = _safe_cfg().get("voice_audio_dir", DEFAULT_VOICE_AUDIO_DIR)
    raw = (raw or "").strip()
    return os.path.expanduser(raw) if raw else ""


def _audio_stem(rel):
    """`Recording <YYYYMMDD-HHMMSS> <report>` — the English Coach library keys a
    recording on its folder name ("stem") and names every file inside after it.
    Keeping their `Recording <date>-<time>` prefix makes these sort in with the
    user's own takes; the report suffix says which Go project it came from."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = (rel or "").replace("/", "_").replace("\\", "_").strip()
    base = re.sub(r"[^\w-]", "_", base)        # no dots: keeps ".." out of names
    base = re.sub(r"_{2,}", "_", base).strip("_")
    return f"Recording {stamp} {base}" if base else f"Recording {stamp}"


def save_voice_audio(data, rel):
    """Write the raw recording into its own folder, English Coach style:

        VideoAudioFiles/Recording 20260726-224624 yehu_3d_r2/
            Recording 20260726-224624 yehu_3d_r2.webm

    The matching `.txt` transcript is added by `save_voice_text` once whisper
    has run, giving that project the `<stem>/<stem>.{webm,txt}` pair it expects.
    (`.polished.txt`, `.result.json` and `history.json` are that app's business,
    so we never write them.)

    Returns (path, error).  A failure here must never lose the user's take, so
    the caller falls back to a temp file and still transcribes."""
    d = voice_audio_dir()
    if not d:
        return None, None                      # retention switched off on purpose
    try:
        stem = _audio_stem(rel)
        folder = os.path.join(d, stem)
        if os.path.isdir(folder):    # same report, same second — never clobber
            i = 2
            while os.path.isdir(f"{folder}-{i}"):
                i += 1
            folder, stem = f"{folder}-{i}", f"{stem}-{i}"
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, stem + ".webm")
        with open(path, "wb") as f:
            f.write(data)
        return path, None
    except Exception as e:                      # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def save_voice_text(audio_path, text):
    """Drop `<stem>.txt` next to the recording — plain transcript prose, no
    header, matching what the English Coach library already stores."""
    if not (audio_path and text and text.strip()):
        return None
    try:
        path = os.path.splitext(audio_path)[0] + ".txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write(text.strip() + "\n")
        return path
    except Exception as e:                      # noqa: BLE001
        print(f"  ! could not write the transcript next to the recording: {e}")
        return None


# ---------------------------------------------------------------------------
# Transcription progress.  The POST blocks until the whole take is done, which
# on a long recording is a minute or more of silence; the browser polls this
# while it waits.  faster-whisper hands back a *generator* of segments plus the
# audio duration, so this is genuine progress through the audio, not a spinner.
# ---------------------------------------------------------------------------
_PROGRESS = {"active": False, "stage": "", "pct": 0, "pos": 0.0,
             "duration": 0.0, "elapsed": 0.0, "label": ""}


def _mmss(sec):
    sec = int(max(0, sec or 0))
    return f"{sec // 60}:{sec % 60:02d}"


def _progress(stage, pct=None, pos=None, duration=None, started=None,
              active=True):
    p = _PROGRESS
    p["active"] = active
    p["stage"] = stage
    if pct is not None:
        p["pct"] = max(0, min(100, int(pct)))
    if pos is not None:
        p["pos"] = float(pos)
    if duration is not None:
        p["duration"] = float(duration)
    if started:
        p["elapsed"] = time.time() - started
    bits = [stage]
    if p["duration"] and stage.startswith("Transcribing"):
        bits = [f"Transcribing {p['pct']}%",
                f"{_mmss(p['pos'])} of {_mmss(p['duration'])}"]
        # Rough ETA from the throughput so far — better than no number at all.
        if p["pos"] > 1 and p["elapsed"] > 1:
            rate = p["pos"] / p["elapsed"]
            if rate > 0:
                left = (p["duration"] - p["pos"]) / rate
                if left >= 1:
                    bits.append(f"about {_mmss(left)} left")
    elif p["elapsed"] >= 3:
        bits.append(f"{_mmss(p['elapsed'])} elapsed")
    p["label"] = " · ".join(bits)
    return p


def transcribe_audio(data, rel=None):
    """Save the recording, then transcribe it with faster-whisper.

    Returns (text, error, stem) where `stem` is the English Coach folder name
    the take was filed under.  The audio is kept permanently in
    `voice_audio_dir()`; only the fallback temp copy is deleted."""
    started = time.time()
    _progress("Saving the recording", pct=0, pos=0, duration=0,
              started=started)
    saved, save_err = save_voice_audio(data, rel)
    if save_err:
        print(f"  ! could not save the recording to "
              f"{voice_audio_dir()}: {save_err}")
    # The folder name is the useful identifier — the .webm and .txt inside both
    # carry it, and it is what the other project keys on.
    stem = (os.path.basename(os.path.dirname(saved)) if saved else None)

    _progress("Loading the speech model", pct=0, started=started)
    m = _get_whisper()
    if not m:
        # No model, but the audio is already safe on disk — say so, so the user
        # knows the take was not lost.
        err = _WHISPER_ERR or "Voice transcription is unavailable."
        if saved:
            err += (f" The recording itself was saved to \"{stem}\" "
                    f"(transcript missing, so add the .txt by hand or re-run "
                    f"once the model is installed).")
        _progress("", active=False)
        return None, err, stem

    lang = (_safe_cfg().get("whisper_language") or "").strip() or None
    tmp = None
    if saved:
        src = saved
    else:
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(data)
            tmp = f.name
        src = tmp
    try:
        _progress("Analysing the audio", pct=0, started=started)
        segments, info = m.transcribe(src, language=lang, vad_filter=True)
        total = float(getattr(info, "duration", 0) or 0)
        _progress("Transcribing", pct=0, pos=0, duration=total, started=started)
        parts, n = [], 0
        # `segments` is a generator: whisper only does the work as we iterate,
        # so this loop IS the transcription and each step is real progress.
        for s in segments:
            parts.append(s.text)
            n += 1
            end = float(getattr(s, "end", 0) or 0)
            pct = (end / total * 100) if total else 0
            _progress("Transcribing", pct=min(99, pct), pos=end,
                      duration=total, started=started)
            if n % 5 == 0:
                print(f"    ... transcribed {_mmss(end)} of {_mmss(total)}",
                      flush=True)
        text = "".join(parts).strip()
        _progress("Saving the transcript", pct=100, started=started)
        # Pair the transcript with the audio, the way the English Coach library
        # stores every other recording.
        save_voice_text(saved, text)
        return text, None, stem
    except Exception as e:  # noqa: BLE001
        return None, f"Transcription failed: {e}", stem
    finally:
        _progress("", active=False)
        if tmp:                                 # only the fallback copy goes away
            try:
                os.remove(tmp)
            except OSError:
                pass


def _notes_path(rel):
    rdir = report_dir_from_rel(rel or "")
    return os.path.join(rdir, "notes.json") if rdir else None


def load_notes(rel):
    p = _notes_path(rel)
    if p and os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _voice_path(rel):
    rdir = report_dir_from_rel(rel or "")
    return os.path.join(rdir, "review_voice.md") if rdir else None


def load_voice(rel):
    p = _voice_path(rel)
    if p and os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""
    return ""


def save_voice(rel, text):
    p = _voice_path(rel)
    if not p:
        return False, "Report not found."
    try:
        with open(p, "w", encoding="utf-8") as f:
            f.write(text or "")
    except OSError as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"
    return True, None


def _hidden_path(rel):
    rdir = report_dir_from_rel(rel or "")
    return os.path.join(rdir, "practice_hidden.json") if rdir else None


def load_practice_hidden(rel):
    p = _hidden_path(rel)
    if p and os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return list(json.load(f))
        except Exception:
            return []
    return []


def _all_blunder_keys(rel):
    """Every blunder key (`filename#move`) that exists in this report *today*."""
    rdir = report_dir_from_rel(rel or "")
    if not rdir:
        return []
    games = report.load_games(rdir, _safe_cfg().get("games_dirs", []))
    keys = []
    for g in games:
        for m in g.get("all_user_moves", []):
            if ((m.get("points_lost", 0) or 0) >= report.PTS_BLUNDER
                    or (m.get("winrate_lost", 0) or 0) >= report.WR_BLUNDER):
                keys.append(f"{g.get('filename','')}#{m.get('move_number')}")
    return keys


def set_all_hidden(rel, hide):
    """Delete-all / restore-all.

    Deleting writes out the keys that exist *right now* rather than setting a
    blanket flag — that was the old `practice_cleared` marker, and it kept
    suppressing the section for games imported afterwards.  With explicit keys,
    a new game's blunders are simply keys nobody deleted, so they show up.

    Returns the number of hidden keys afterwards."""
    p = _hidden_path(rel)
    if not p:
        raise ValueError("Report not found.")
    keys = sorted(set(_all_blunder_keys(rel))) if hide else []
    with open(p, "w", encoding="utf-8") as f:
        json.dump(keys, f, ensure_ascii=False, indent=1)
    # Retire the legacy marker if this folder still has one, so it can never
    # hide a freshly analysed game again.
    rdir = report_dir_from_rel(rel or "")
    mp = os.path.join(rdir, "practice_cleared") if rdir else None
    if mp and os.path.exists(mp):
        try:
            os.remove(mp)
        except OSError as e:                      # noqa: BLE001
            print(f"  ! could not remove the legacy practice_cleared marker: {e}")
    return len(keys)


def add_practice_hidden(rel, nid):
    p = _hidden_path(rel)
    if not p:
        return False, "Report not found."
    if not nid:
        return False, "No blunder id given to delete."
    hidden = set(load_practice_hidden(rel))
    hidden.add(nid)
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(sorted(hidden), f, ensure_ascii=False, indent=1)
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"
    return True, None


def save_note(rel, nid, data):
    """Write/merge/delete a single blunder note in <report>/notes.json.
    data=None deletes.  Returns (ok, error)."""
    p = _notes_path(rel)
    if not p:
        return False, "Report not found."
    if not nid:
        return False, "No note id given."
    notes = load_notes(rel)
    if data is None:
        notes.pop(nid, None)
    else:
        data = dict(data)
        data["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
        notes[nid] = data
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=1)
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"
    return True, None


# ---------------------------------------------------------------------------
# Review summary: hand the notes to DeepSeek and get a diagnostic profile back
# ---------------------------------------------------------------------------
def _prompt_file(name):
    try:
        with open(os.path.join(HERE, "prompts", name), "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _summary_system():
    return (
        "You are a Go review coach. You will be given the aggregate data for a "
        "batch of one player's games, plus that player's own review commentary "
        "(mostly a transcript of them talking out loud, so expect slips, repetition "
        "and misheard Go terms). The commentary may be in Chinese, English or a mix; "
        "read whatever language it is in.\n\n"
        "Group the scattered mistakes into the few weakness categories that "
        "EMERGE FROM THESE NOTES. The categories are not from a preset list -- you "
        "name them yourself, based on what actually recurs (usually 3-6 of them, "
        "more or fewer as the data warrants).\n\n"
        "Requirements:\n"
        "- Diagnose root causes, not symptoms. The player usually already knows "
        "*what* went wrong; your job is *why* it went wrong that way, and whether "
        "the same flaw keeps reappearing.\n"
        "- Separate ability problems (they could not read it out, so they need "
        "targeted training) from habit problems (they saw it and did not do it, so "
        "it can be fixed immediately and pays off faster). Label each category as "
        "one or the other.\n"
        "- Reconstruct misheard Go terms from context (ladder, cap, ko fight, "
        "sabaki and similar are often transcribed wrong; in Chinese audio, "
        "zhengzi / feizhao / jiezheng / tengnuo). Do not make the player clean up "
        "the text first.\n"
        "- Be honest about the numbers. If the sample is small, say the difference "
        "is not significant rather than forcing a story of improvement or decline. "
        "Where lead conversion and comeback rate are given, if holding a lead is "
        "clearly weaker than coming back, make 'simplify once ahead / close the "
        "game out' a top priority.\n\n"
        "Output in ENGLISH markdown. Be concise. Do NOT list every move one by one, "
        "and do not use words like batch, cumulative, cross-batch or comparison -- "
        "this is one overall summary of all their notes, and newly added notes are "
        "simply more of the same material.\n"
        "1. An opening overall judgement (3-5 sentences) naming the 1-2 root causes "
        "most worth fixing.\n"
        "2. \"Your weakness profile\" -- a short paragraph per emerging category: "
        "the category name (yours), its essence / root cause, at most 1-2 "
        "representative moves, whether it is ability or habit, and what to train. "
        "A compact table is welcome (weakness | roughly how often | ability/habit).\n"
        "3. \"What you keep telling yourself\" -- the principles and maxims distilled "
        "from their spoken review.\n"
        "4. \"Training priorities\" -- ordered by what matters most, each with one "
        "concrete drill.\n"
        "Output the markdown only, with no pleasantries.")


def _summary_path(rel):
    rdir = report_dir_from_rel(rel or "")
    return os.path.join(rdir, "review_summary.md") if rdir else None


def load_summary(rel):
    p = _summary_path(rel)
    if p and os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""
    return ""


# ---------------------------------------------------------------------------
# Summary history: every generation is kept, so regenerating never destroys the
# previous diagnosis.  One file per version in <report>/summaries/, named for
# when it was made; review_summary.md stays as "the latest" so anything that
# already reads it keeps working.
# ---------------------------------------------------------------------------
SUMMARY_DIR = "summaries"
_STAMP_FMT = "%Y-%m-%d_%H%M%S"


def _summary_dir(rel, create=False):
    rdir = report_dir_from_rel(rel or "")
    if not rdir:
        return None
    d = os.path.join(rdir, SUMMARY_DIR)
    if create:
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            return None
    return d


def _adopt_legacy_summary(rel):
    """Older reports only ever had review_summary.md.  Fold it into the archive
    the first time we look, dated by its mtime, so no past diagnosis is lost."""
    d = _summary_dir(rel)
    p = _summary_path(rel)
    if not d or not p or not os.path.exists(p):
        return
    if os.path.isdir(d) and any(f.endswith(".md") for f in os.listdir(d)):
        return                                   # archive already started
    try:
        stamp = datetime.datetime.fromtimestamp(os.path.getmtime(p))
        os.makedirs(d, exist_ok=True)
        with open(p, encoding="utf-8") as f:
            text = f.read()
        with open(os.path.join(d, stamp.strftime(_STAMP_FMT) + ".md"),
                  "w", encoding="utf-8") as f:
            f.write(text)
    except OSError as e:                          # noqa: BLE001
        print(f"  ! could not archive the existing summary for {rel}: {e}")


def archive_summary(rel, text):
    """Store one generated summary as its own dated file."""
    d = _summary_dir(rel, create=True)
    if not d:
        return None
    path = os.path.join(d, datetime.datetime.now().strftime(_STAMP_FMT) + ".md")
    n = 2
    while os.path.exists(path):                   # same second, twice
        path = os.path.join(d, datetime.datetime.now().strftime(_STAMP_FMT)
                            + f"-{n}.md")
        n += 1
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path
    except OSError as e:                          # noqa: BLE001
        print(f"  ! could not archive the summary: {e}")
        return None


def list_summaries(rel):
    """[(datetime_or_None, path)] for every archived version, newest first."""
    _adopt_legacy_summary(rel)
    d = _summary_dir(rel)
    if not d or not os.path.isdir(d):
        return []
    out = []
    for fn in os.listdir(d):
        if not fn.endswith(".md"):
            continue
        try:
            when = datetime.datetime.strptime(fn[:17], _STAMP_FMT)
        except ValueError:
            when = None
        out.append((when, os.path.join(d, fn)))
    out.sort(key=lambda t: (t[0] or datetime.datetime.min), reverse=True)
    return out


def _pretty_stamp(when, path):
    if when:
        return when.strftime("%d %b %Y, %H:%M")
    return os.path.basename(path)[:-3]


def summary_history_html(rel, skip_latest=True):
    """Collapsible <details> for the older versions (the newest is already
    rendered in full above)."""
    rows = list_summaries(rel)
    if skip_latest:
        rows = rows[1:]
    if not rows:
        return ""
    out = ["<div class='sumhist'><div class='sumhist-h'>Previous summaries "
           f"<span class='nstat'>{len(rows)}</span></div>"]
    for when, path in rows:
        try:
            with open(path, encoding="utf-8") as f:
                md = f.read()
        except OSError:
            continue
        out.append("<details class='sumver'><summary>"
                   f"{_esc(_pretty_stamp(when, path))}</summary>"
                   f"<div class='smdbox'>{_md_to_html(md)}</div></details>")
    out.append("</div>")
    return "".join(out)


def export_summaries_md(rel):
    """Every version of this project's summaries in one Markdown document,
    oldest first, for handing to an AI at the end of a project."""
    rows = list(reversed(list_summaries(rel)))
    label = os.path.basename(str(report_dir_from_rel(rel) or rel).rstrip("/\\"))
    today = datetime.date.today().isoformat()
    parts = [f"# Review summaries — project {label}",
             "",
             f"{len(rows)} summary version(s), oldest first. Exported {today}.",
             ""]
    for i, (when, path) in enumerate(rows, 1):
        try:
            with open(path, encoding="utf-8") as f:
                md = f.read().strip()
        except OSError:
            continue
        parts.append(f"\n---\n\n## Version {i} — {_pretty_stamp(when, path)}\n")
        parts.append(md)
        parts.append("")
    return "\n".join(parts) + "\n"


def _summary_input(rel, notes):
    """Assemble the player's notes + aggregate stats as the DeepSeek user turn."""
    rdir = report_dir_from_rel(rel)
    cfg = _safe_cfg()
    games = report.load_games(rdir, cfg.get("games_dirs", []))
    agg = report.aggregate(games)

    lm = lmw = le = lew = bm = bmw = be = bew = 0
    from collections import Counter
    shapes = Counter()
    for g in games:
        c = report.classify_trajectory(g)
        if not c:
            continue
        shapes[report.TRAJ_LABEL.get(c["type"], c["type"])] += 1
        md_, ed_ = report._lead_flags(c["curve"])
        bd_, bed_ = report._behind_flags(c["curve"])
        if md_:
            lm += 1
            lmw += 1 if c["won"] else 0
        if ed_:
            le += 1
            lew += 1 if c["won"] else 0
        if bd_:
            bm += 1
            bmw += 1 if c["won"] else 0
        if bed_:
            be += 1
            bew += 1 if c["won"] else 0

    def pc(a, b):
        return f"{round(a / b * 100)}% ({a}/{b})" if b else "sample too small"

    L = []
    L.append("I am the player in this report. Below is the review material for all "
             "of my games -- please give me one overall summary of my weaknesses and "
             "my training priorities.")
    L.append("")
    L.append("## 1. Aggregate report stats")
    L.append(f"- {agg['n']} games: {agg['wins']}W {agg['losses']}L; "
             f"{agg['n_user_moves']} of my moves analysed.")
    L.append(f"- {agg['avg_points_lost']} points lost per move on average; "
             f"blunder rate {agg['blunder_rate']}%; "
             f"{agg['n_blunders']} blunders in total.")
    pa = agg.get("phase_avg", {})
    L.append(f"- Points lost per move by phase: fuseki {pa.get('opening','-')}, "
             f"middlegame {pa.get('middlegame','-')}, "
             f"yose {pa.get('endgame','-')}.")
    L.append(f"- Lead conversion (entered the phase >=90% winning and still won): "
             f"middlegame {pc(lmw, lm)}, yose {pc(lew, le)}.")
    L.append(f"- Comeback rate (entered the phase <=10% winning and still won): "
             f"middlegame {pc(bmw, bm)}, yose {pc(bew, be)}.")
    if shapes:
        L.append("- Game trajectory classes: " + ", ".join(f"{k} x{v}"
                                          for k, v in shapes.most_common()) + ".")
    L.append("")
    L.append("## 2. My spoken review (voice transcript -- expect slips, repetition "
             "and misheard terms; one passage often covers several moves in a row, so "
             "split it into individual mistakes)")
    voice = (load_voice(rel) or "").strip()
    L.append("")
    L.append(voice or "(No voice transcript for this report yet.)")
    L.append("")

    # Extra structured notes, if any still exist from the old per-position flow.
    if notes:
        L.append("## 3. Additional structured notes (where they duplicate the "
                 "spoken review, prefer the spoken version)")
        L.append("")
        ordered = sorted(notes.values(),
                         key=lambda x: (x.get("points_lost", 0) or 0), reverse=True)
        for i, note in enumerate(ordered, 1):
            wr = note.get("winrate_lost", 0) or 0
            txt = (note.get("note") or "").strip()
            bits = []
            if note.get("cause"):
                bits.append("cause: " + ", ".join(note["cause"]))
            if note.get("maxims"):
                bits.append("maxims: " + "; ".join(note["maxims"]))
            if txt:
                bits.append("comment: " + txt)
            L.append(f"- {note.get('game','')} move {note.get('move','?')}: "
                     f"I played {note.get('played','?')} (AI: {note.get('best','?')}), "
                     f"losing {note.get('points_lost',0)} pts / win rate -{round(wr)}%"
                     + ("; " + "; ".join(bits) if bits else ""))
        L.append("")

    # A reference list of the report's worst blunders so the model can map my
    # spoken references ("that C12 mistake...") to concrete moves.
    tb = agg.get("top_blunders", [])[:20]
    if tb:
        L.append("## Appendix: main blunders in this report (so you can map the "
                 "moves I mention out loud to concrete plays)")
        L.append("")
        L.append("| Game | Move | I played | KataGo | Pts lost | WR drop | Phase |")
        L.append("|---|---|---|---|---|---|---|")
        ph_lab = {"opening": "fuseki", "middlegame": "middlegame", "endgame": "yose"}
        for m in tb:
            wr = round((m.get("winrate_lost", 0) or 0) * 100)
            L.append(f"| {m.get('game','')} | {m.get('move_number','?')} | "
                     f"{m.get('played','?')} | {m.get('best','?')} | "
                     f"{m.get('points_lost',0)} | {wr}% | "
                     f"{ph_lab.get(m.get('phase',''), m.get('phase',''))} |")
        L.append("")

    L.append("")
    L.append("Group all of my review commentary above into the few weakness "
             "categories that emerge from it (name them yourself; do not use a preset "
             "list). Give me an overall judgement, a weakness profile (with "
             "representative moves, and whether each is ability or habit), the "
             "principles and maxims I keep repeating to myself, and concrete drills "
             "in priority order. Answer in English. Do not list every move one by "
             "one, and do not compare batches or reports.")
    return "\n".join(L)


def _call_deepseek(system, user, cfg):
    import urllib.request
    import urllib.error
    key = (cfg.get("deepseek_api_key") or "").strip()
    if not key:
        return None, ("DeepSeek is not configured yet. Add deepseek_api_key to "
                      "config.json and try again (that file is gitignored, so it is "
                      "never committed).")
    base = (cfg.get("deepseek_base_url") or "https://api.deepseek.com").rstrip("/")
    model = cfg.get("deepseek_model") or "deepseek-chat"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0.3,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        base + "/chat/completions", data=payload,
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=240) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"], None
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001
            pass
        return None, f"DeepSeek returned {e.code}: {body}"
    except Exception as e:  # noqa: BLE001
        return None, f"DeepSeek call failed: {e}"


def build_review_summary(rel):
    """Generate the diagnostic archive via DeepSeek; cache to review_summary.md."""
    rdir = report_dir_from_rel(rel or "")
    if not rdir:
        return None, "Report not found."
    notes = load_notes(rel)
    voice = (load_voice(rel) or "").strip()
    if not voice and not notes:
        return None, ("This report has no review material yet. Go to the blunder set, "
                      "press \"Start voice review\", talk through the blunders as you "
                      "look at them, and stop -- your take is transcribed, then come "
                      "back here to generate the summary.")
    text, err = _call_deepseek(_summary_system(),
                               _summary_input(rel, notes), _safe_cfg())
    if err:
        return None, err
    if not (text and text.strip()):
        return None, "DeepSeek returned nothing -- please try again shortly."
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    text = text.strip() + (f"\n\n---\n> Generated by DeepSeek from all of your review "
                           f"notes &middot; {stamp}\n")
    # Fold any pre-archive summary in first, so regenerating never silently
    # drops the one that was already on disk.
    _adopt_legacy_summary(rel)
    archive_summary(rel, text)
    try:
        with open(os.path.join(rdir, "review_summary.md"), "w",
                  encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass
    return text, None


def _md_to_html(md):
    """Minimal, dependency-free markdown -> HTML (headings/tables/lists/quote)."""
    import re as _re
    lines = (md or "").replace("\r\n", "\n").split("\n")
    n = len(lines)
    out = []
    i = 0

    def inline(s):
        s = html.escape(s)
        s = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        s = _re.sub(r"`(.+?)`", r"<code>\1</code>", s)
        return s

    row_re = _re.compile(r"^\s*\|.*\|\s*$")
    sep_re = _re.compile(r"^\s*\|[\s:\-|]+\|\s*$")
    while i < n:
        ln = lines[i]
        if row_re.match(ln) and i + 1 < n and sep_re.match(lines[i + 1]):
            hdr = [c.strip() for c in ln.strip().strip("|").split("|")]
            i += 2
            body = []
            while i < n and row_re.match(lines[i]):
                body.append([c.strip() for c in
                             lines[i].strip().strip("|").split("|")])
                i += 1
            t = ["<table class='smd'><thead><tr>"]
            t += ["<th>" + inline(c) + "</th>" for c in hdr]
            t.append("</tr></thead><tbody>")
            for r in body:
                t.append("<tr>" + "".join("<td>" + inline(c) + "</td>"
                                          for c in r) + "</tr>")
            t.append("</tbody></table>")
            out.append("".join(t))
            continue
        m = _re.match(r"^(#{1,4})\s+(.*)$", ln)
        if m:
            lv = len(m.group(1))
            out.append(f"<h{lv}>" + inline(m.group(2)) + f"</h{lv}>")
            i += 1
            continue
        if _re.match(r"^\s*(-{3,}|\*{3,})\s*$", ln):
            out.append("<hr>")
            i += 1
            continue
        if _re.match(r"^\s*>\s?", ln):
            buf = []
            while i < n and _re.match(r"^\s*>\s?", lines[i]):
                buf.append(inline(_re.sub(r"^\s*>\s?", "", lines[i])))
                i += 1
            out.append("<blockquote>" + "<br>".join(buf) + "</blockquote>")
            continue
        if _re.match(r"^\s*[-*+]\s+", ln):
            buf = []
            while i < n and _re.match(r"^\s*[-*+]\s+", lines[i]):
                buf.append("<li>" + inline(_re.sub(r"^\s*[-*+]\s+", "",
                                                   lines[i])) + "</li>")
                i += 1
            out.append("<ul>" + "".join(buf) + "</ul>")
            continue
        if _re.match(r"^\s*\d+\.\s+", ln):
            buf = []
            while i < n and _re.match(r"^\s*\d+\.\s+", lines[i]):
                buf.append("<li>" + inline(_re.sub(r"^\s*\d+\.\s+", "",
                                                   lines[i])) + "</li>")
                i += 1
            out.append("<ol>" + "".join(buf) + "</ol>")
            continue
        if ln.strip() == "":
            i += 1
            continue
        out.append("<p>" + inline(ln) + "</p>")
        i += 1
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Backup: zip the project itself plus the notes you cannot regenerate.
#
# Deliberately left out: review_report.html and index.html (generated on every
# rebuild), the per-game *.sgf.json (derived from the analysed SGFs you import),
# and config.json (plaintext ikatago password + DeepSeek key — a backup should
# be safe to drop in cloud storage).  That takes ~85 MB down to well under one.
# ---------------------------------------------------------------------------
BACKUP_SKIP_DIRS = {"__pycache__", ".ipynb_checkpoints", ".git", "node_modules"}
BACKUP_SKIP_FILES = {".DS_Store", "config.json", "index.html",
                     "review_report.html"}
# Inside a report folder these are yours; everything else there is derived.
BACKUP_REPORT_FILES = {"review_voice.md", "review_summary.md",
                       "practice_hidden.json", "notes.json"}

BACKUP_README = """Mirror of Go — project backup
=============================

Made {when} from {root}

WHAT IS IN HERE
  <repo>/*.command                the double-click launcher
  <repo>/My games/                the Fox downloader module that pipeline.py
    fox_full_downloader.py        imports (no downloaded games, just the code)
  <repo>/go_review/*.py           the application
  <repo>/go_review/*.md,          docs and the original skill prompts
    prompts/, tests/, avatar/
  <repo>/go_review/               settings template
    config.example.json
  <repo>/go_review/<report>/      per project:
      *.sgf.json                    the per-game KataGo analysis - this is
                                    what rebuilds the reports (step 2)
      review_voice.md               your spoken-review transcripts
      review_summary.md             the latest DeepSeek diagnosis
      summaries/*.md                every archived summary version
      practice_hidden.json          which blunders you deleted/mastered
      notes.json                    legacy per-position notes, if any

WHAT IS DELIBERATELY LEFT OUT
  config.json          holds your ikatago password and DeepSeek API key in
                       plain text. Excluded so this zip is safe to store or
                       share. See step 3 below.
  config.txt (Lizzie)  also stores the ikatago password.
  review_report.html   regenerated in seconds from the JSON above:
  index.html             python3 go_review/web_app.py --rebuild-reports
  My games/<games>      your downloaded/analysed SGFs (~114 MB) - back these
                       up separately if you want them.
  ikatago / KataGo      the engine binaries and network weights.
  Voice recordings (.webm) live in your English Coach library, not here.

TO RESTORE ON ANOTHER MAC
  1. Unzip.
  2. Rebuild the reports from the analysis JSON (a few seconds, no engine and
     no internet needed):
         python3 go_review/web_app.py --rebuild-reports
  3. Start it - double-click the .command file, or:
         python3 go_review/web_app.py
     It runs WITHOUT config.json, falling back to config.example.json, so
     everything you can read is available straight away.
     If double-clicking does nothing, the executable bit was lost in the zip:
         chmod +x *.command
     On first launch macOS may block it: right-click > Open, or allow it in
     System Settings > Privacy & Security.

  That is all that is needed to READ everything. The rest is only for making
  NEW reviews on that machine:
  4. Copy config.example.json to config.json and refill: ikatago_command,
     deepseek_api_key, games_dirs, output_dir, user_names, whisper_model,
     voice_audio_dir, lizzie_jar.
  5. Install what is machine-specific:
         pip install faster-whisper      (voice transcription)
         a faster-whisper model at the path in whisper_model
         the ikatago client + your Fox login (cloud KataGo)
         LizzieYZY + Java, if you import analysed SGFs that way

WHAT WORKS AFTER STEPS 1-3, WITH NOTHING INSTALLED
  - every report: overview, trajectory, blunder diagrams, game by game
  - your voice transcripts, and every archived review summary + export
  - the Go terms dictionary, compare reports, the offline index.html
  Only recording, transcribing, analysing and generating NEW summaries
  need steps 4-5.
"""


def _backup_top():
    """Name of the top folder inside the zip — the repo folder, so unzipping
    reproduces `<repo>/一目弈镜.command` next to `<repo>/go_review/`."""
    return os.path.basename(os.path.dirname(HERE)) or "ClaudeCode-Go"


def backup_manifest():
    """[(absolute_path, name_inside_the_zip)] for everything worth keeping.

    The zip is rooted at the *repo* folder, not go_review, because the launcher
    (`一目弈镜.command`) and the Fox downloader that `pipeline` imports both live
    one level up.  Unzipping therefore gives a tree you can actually run.
    Only named files are taken from outside go_review — never the 114 MB of
    downloaded games, the ikatago/KataGo binaries, or Lizzie's config.txt
    (which also stores the ikatago password)."""
    root = HERE
    repo = os.path.dirname(root)
    top = _backup_top()
    try:
        reports = {os.path.abspath(d) for d in import_lizzie.list_report_dirs(root)}
    except Exception:                             # noqa: BLE001
        reports = set()
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in BACKUP_SKIP_DIRS and not d.startswith(".")]
        absdir = os.path.abspath(dirpath)
        owner = next((r for r in reports
                      if absdir == r or absdir.startswith(r + os.sep)), None)
        for fn in sorted(filenames):
            if fn in BACKUP_SKIP_FILES or fn.startswith("."):
                continue
            if owner:
                inside = os.path.relpath(absdir, owner)
                if inside == os.curdir:
                    # Your notes, plus the per-game analysis JSON — that is what
                    # lets `--rebuild-reports` bring the reports back on another
                    # machine without re-importing the SGFs.  Only the generated
                    # review_report.html is skipped (see BACKUP_SKIP_FILES).
                    if not (fn in BACKUP_REPORT_FILES or fn.endswith(".json")):
                        continue
                elif inside == SUMMARY_DIR:
                    if not fn.endswith(".md"):
                        continue
                else:
                    continue                  # nothing else in a report folder
            p = os.path.join(absdir, fn)
            out.append((p, "/".join([top, "go_review",
                                     os.path.relpath(p, root)])))

    # The few things outside go_review that the app genuinely needs to run.
    extras = [os.path.join(repo, "My games", "fox_full_downloader.py")]
    try:
        for fn in sorted(os.listdir(repo)):
            if fn.endswith(".command") or fn in ("README.md", "LICENSE",
                                                 ".gitignore"):
                extras.append(os.path.join(repo, fn))
    except OSError:
        pass
    for p in extras:
        if os.path.isfile(p):
            out.append((p, "/".join([top, os.path.relpath(p, repo)])))
    return sorted(out, key=lambda t: t[1])


def build_backup_zip():
    """Return (zip_bytes, file_count, uncompressed_bytes)."""
    files = backup_manifest()
    buf = io.BytesIO()
    total = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr(_backup_top() + "/BACKUP_README.txt", BACKUP_README.format(
            when=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), root=HERE))
        for path, arc in files:
            try:
                z.write(path, arc)
                total += os.path.getsize(path)
            except OSError as e:                  # noqa: BLE001
                print(f"  ! skipped {arc}: {e}")
    return buf.getvalue(), len(files), total


def delete_report(rel):
    """Delete a report folder. Only known report dirs strictly under HERE may be
    removed. Returns (ok, error_message)."""
    if not rel or not str(rel).strip():
        return False, "No report given to delete."
    rdir = report_dir_from_rel(rel)
    if not rdir:
        return False, "Report not found (or the path is invalid)."
    known = {r["rel"] for r in list_reports()}
    if os.path.relpath(rdir, HERE) not in known:
        return False, "That folder is not an analysed report -- refusing to delete it."
    try:
        shutil.rmtree(rdir)
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"
    _SUMMARY_CACHE.pop(rdir, None)
    write_static_index()
    return True, None


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
        if path == "/terms":
            self._send(200, terms_page(embed=embed))
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


if __name__ == "__main__":
    main()
