"""Static CSS/JS string assets embedded into server-rendered pages."""


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
    var bz=document.getElementById('btn-tsumego');
    if(bz) bz.classList.toggle('on', key==='__tsumego__');
    document.querySelectorAll('.repitem').forEach(function(el){
      el.classList.toggle('on', el.dataset.rel===key); });
  }
  function openAnalyze(){ frame.src='/analyze?embed=1'; setActive('__analyze__'); }
  function openCompare(){ frame.src='/compare?embed=1'; setActive('__compare__'); }
  function openSummary(){ frame.src='/summary?embed=1'; setActive('__summary__'); }
  function openTerms(){ frame.src='/terms?embed=1'; setActive('__terms__'); }
  function openTsumego(){ frame.src='/tsumego?embed=1&t='+Date.now();
    setActive('__tsumego__'); }
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
  var _bz=document.getElementById('btn-tsumego'); if(_bz) _bz.onclick=openTsumego;
  loadReports().then(function(reps){
    if(reps.length) openReport(reps[0].rel); else openAnalyze();
  });
})();
</script>
"""


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
