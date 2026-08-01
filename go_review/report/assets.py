"""Static CSS/JS string assets embedded into generated report pages."""


PRACTICE_CLEAR_JS = r"""
<script>
(function(){
  function repRel(){ var m=location.pathname.match(/^\/r\/(.+)$/);
    return m?decodeURIComponent(m[1].replace(/\/$/,'')):null; }
  var REL=repRel();
  function setCleared(v){
    if(!REL){ alert('Open this report inside the app (local server) to do that.'); return; }
    if(v && !confirm("Delete all blunder positions in this project?\n"
      +"For a project you have finished reviewing: removes every blunder diagram "
      +"and its content, and shrinks the report file. You can Restore at any time.")) return;
    fetch('/api/practice_clear',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({report:REL,clear:v})}).then(function(r){return r.json();})
    .then(function(d){ if(d.error){ alert('Failed: '+d.error); return; } location.reload(); })
    .catch(function(e){ alert('Failed: '+e); });
  }
  window.practiceClear=function(){ setCleared(true); };
  window.practiceRestore=function(){ setCleared(false); };
})();
</script>
"""


TRENDS_JS = """
<script>
function toggleSeries(g){
  var svg=g.ownerSVGElement; if(!svg) return;
  var si=g.getAttribute('data-si');
  var ser=svg.querySelector('.tser[data-si=\"'+si+'\"]');
  if(!ser) return;
  var off=ser.style.display==='none';
  ser.style.display=off?'':'none';
  g.style.opacity=off?'1':'0.35';
}
</script>
"""


VOICE_PANEL = (
    "<div class='vcpanel'>"
    "<div class='vcrow'>"
    "<button type='button' class='vcbtn' id='vcBtn' onclick='vcToggle()'>"
    "&#127908; Start voice review</button>"
    "<span class='vctimer' id='vcTimer'>00:00</span>"
    "<span class='vcstat sub' id='vcStat'></span></div>"
    "<p class='sub vchint'>One recording can cover many moves: scroll through the "
    "blunders below and talk through your thinking, your blind spots and what you "
    "learned. Hit <b>Stop &amp; transcribe</b> at the end and the whole take is turned "
    "into text and saved to this report, ready for <b>Review Summary</b> to turn into "
    "your weakness profile.</p>"
    "<div class='vcbar' id='vcBar'><i id='vcBarFill'></i></div>"
    "<textarea id='vcText' class='vctext' rows='4' "
    "placeholder='The transcript will appear here -- edit it freely...'></textarea>"
    "<div class='vcrow'><button type='button' class='vcsave' onclick='vcSave()'>"
    "Save text</button><span class='sub' style='margin-left:8px'>"
    "Saved automatically; you can also edit and save by hand.</span></div>"
    "</div>")


FLOAT_REC = (
    "<div id='vcFloat' class='vcfloat'><span class='vcdot'></span>"
    "Recording <span id='vcFloatT'>00:00</span>"
    "<button type='button' onclick='vcToggle()'>Stop &amp; transcribe</button></div>")


VOICE_JS = r"""
<script>
(function(){
  function repRel(){ var m=location.pathname.match(/^\/r\/(.+)$/);
    return m?decodeURIComponent(m[1].replace(/\/$/,'')):null; }
  var REL=repRel(), server=!!REL;
  var HKEY='ymhidden:'+(REL||location.pathname);
  var VKEY='ymvoice:'+(REL||location.pathname);
  function el(id){ return document.getElementById(id); }

  // ---- delete a blunder from the practice set (persists; shrinks on rebuild) ----
  function hideCard(nid){ document.querySelectorAll('.diag').forEach(function(d){
    if(d.dataset.key===nid) d.remove(); }); }
  function loadHidden(){
    if(server){
      fetch('/api/practice_hidden?report='+encodeURIComponent(REL)+'&t='+Date.now(),{cache:'no-store'})
      .then(function(r){return r.json();}).then(function(d){
        (d.hidden||[]).forEach(hideCard); document.dispatchEvent(new Event('ymnotes')); })
      .catch(function(){});
    } else {
      try{ JSON.parse(localStorage.getItem(HKEY)||'[]').forEach(hideCard); }catch(e){}
      document.dispatchEvent(new Event('ymnotes'));
    }
  }
  window.delBlunder=function(btn){
    var d=btn.closest('.diag'); if(!d) return; var nid=d.dataset.key;
    if(!confirm('Remove this position from the practice set?\n(The report file shrinks on the next rebuild; the move still counts in Overview > Total blunders.)')) return;
    if(server){
      fetch('/api/practice_hide',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({report:REL,id:nid})}).then(function(r){return r.json();})
      .then(function(res){ if(res.error){ alert('Delete failed: '+res.error); return; }
        d.remove(); document.dispatchEvent(new Event('ymnotes')); })
      .catch(function(e){ alert('Delete failed: '+e); });
    } else {
      try{ var s=JSON.parse(localStorage.getItem(HKEY)||'[]');
        if(s.indexOf(nid)<0) s.push(nid); localStorage.setItem(HKEY,JSON.stringify(s)); }catch(e){}
      d.remove(); document.dispatchEvent(new Event('ymnotes'));
    }
  };

  // ---- batch voice review: one continuous recording across many positions ----
  var _mr=null, _chunks=[], _recording=false, _t0=0, _timer=null;
  function fmt(s){ var m=Math.floor(s/60), x=s%60;
    return (m<10?'0':'')+m+':'+(x<10?'0':'')+x; }
  function tick(){ var s=Math.floor((Date.now()-_t0)/1000);
    var i=el('vcTimer'); if(i) i.textContent=fmt(s);
    var f=el('vcFloatT'); if(f) f.textContent=fmt(s); }
  function setFloat(on){ var f=el('vcFloat'); if(f) f.style.display=on?'flex':'none'; }

  // ---- transcription heartbeat -------------------------------------------
  // The POST blocks for the whole take, so poll the server for where it has
  // got to. faster-whisper yields segments as it decodes, so the percentage
  // is real progress through the audio rather than a spinner.
  var _prog=null;
  function bar(pct, on){
    var b=el('vcBar'), f=el('vcBarFill');
    if(!b||!f) return;
    b.style.display = on ? 'block' : 'none';
    f.style.width = (pct||0)+'%';
    f.className = (pct>0) ? '' : 'idle';
  }
  function pollStart(st){
    pollStop();
    bar(0, true);
    var misses=0;
    _prog=setInterval(function(){
      fetch('/api/transcribe_progress?t='+Date.now(),{cache:'no-store'})
      .then(function(r){return r.json();}).then(function(p){
        if(!p || !p.active){ misses++; return; }
        misses=0;
        st.textContent=p.label||'Working...';
        bar(p.pct||0, true);
      }).catch(function(){ misses++; });
      // If the server never reports activity, stop nagging it.
      if(misses>20) pollStop();
    }, 500);
  }
  function pollStop(){
    if(_prog){ clearInterval(_prog); _prog=null; }
    bar(0, false);
  }
  function loadVoice(){
    if(server){
      fetch('/api/voice?report='+encodeURIComponent(REL)+'&t='+Date.now(),{cache:'no-store'})
      .then(function(r){return r.json();}).then(function(d){
        var t=el('vcText'); if(t) t.value=d.text||''; }).catch(function(){});
    } else { try{ var t=el('vcText'); if(t) t.value=localStorage.getItem(VKEY)||''; }catch(e){} }
  }
  function saveVoice(text, cb){
    if(server){
      fetch('/api/voice',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({report:REL,text:text})})
      .then(function(r){return r.json();}).then(function(res){ cb&&cb(!res.error,res.error); })
      .catch(function(e){ cb&&cb(false,''+e); });
    } else { try{ localStorage.setItem(VKEY,text); cb&&cb(true); }catch(e){ cb&&cb(false,''+e); } }
  }
  window.vcSave=function(){ var st=el('vcStat'); st.textContent='Saving...';
    saveVoice(el('vcText').value, function(ok,err){
      st.textContent=ok?'Saved \u2713':'Save failed: '+(err||''); }); };
  window.vcToggle=function(){
    var btn=el('vcBtn'), st=el('vcStat');
    if(!server){ alert('Voice transcription needs the app running (start the local server first).'); return; }
    if(!navigator.mediaDevices || !window.MediaRecorder){ alert('This browser does not support recording.'); return; }
    if(!_recording){
      navigator.mediaDevices.getUserMedia({audio:true}).then(function(stream){
        _chunks=[]; _mr=new MediaRecorder(stream);
        _mr.ondataavailable=function(e){ if(e.data && e.data.size) _chunks.push(e.data); };
        _mr.onstop=function(){
          stream.getTracks().forEach(function(t){ t.stop(); });
          clearInterval(_timer); setFloat(false);
          btn.innerHTML='\uD83C\uDFA4 Start voice review'; btn.classList.remove('on');
          st.textContent='Uploading the recording...';
          pollStart(st);
          var blob=new Blob(_chunks,{type:'audio/webm'});
          // Pass the report so the server can name the kept .webm after it.
          fetch('/api/transcribe?report='+encodeURIComponent(REL||''),
            {method:'POST',headers:{'Content-Type':'audio/webm'},body:blob})
          .then(function(r){return r.json();}).then(function(d){
            pollStop();
            if(d.error){
              // The audio is saved before transcription, so a Whisper failure
              // still leaves the take on disk \u2014 tell the user where it went.
              st.textContent='Transcription failed: '+d.error;
              return;
            }
            var t=el('vcText');
            var stamp='['+new Date().toLocaleString()+']';
            if(d.audio) stamp+='  recording: '+d.audio;
            t.value=(t.value?t.value.replace(/\s+$/,'')+'\n\n':'')+stamp+'\n'+(d.text||'');
            saveVoice(t.value, function(){
              st.textContent=d.text
                ? ('Transcribed and saved \u2713'+(d.audio?' \u00b7 filed under "'+d.audio+'"':'')+' (edit below)')
                : '(Nothing recognised in the audio.)'; });
          }).catch(function(e){ pollStop(); st.textContent='Transcription failed: '+e; });
        };
        _mr.start(); _recording=true; _t0=Date.now(); tick(); _timer=setInterval(tick,1000);
        setFloat(true);
        btn.innerHTML='\u23F9 Stop &amp; transcribe'; btn.classList.add('on');
        st.textContent='Recording... scroll through as many blunders as you like and keep talking; hit stop to transcribe the whole take.';
      }).catch(function(e){ alert('Cannot access the microphone: '+e); });
    } else { _recording=false; if(_mr) _mr.stop(); }
  };

  loadHidden();
  loadVoice();
})();
</script>
"""


BOARD_MODAL = """
<div id='bd-modal' class='bdmask'>
  <div class='bdbox'>
    <button class='bdclose' onclick='closeBoard()'>&times;</button>
    <div class='bdtitle' id='bd-title'></div>
    <div class='bdtogs'>
      <label><input type='checkbox' id='bd-mv' checked>
        <span style='color:#e02424'>&#9632;</span> Move played</label>
      <label><input type='checkbox' id='bd-ai' checked>
        <span style='color:#1f9d55'>&#9679;</span> AI recommendation (numbered continuation)</label>
      <label id='bd-est-lbl' style='display:none'><input type='checkbox' id='bd-est'>
        <span style='color:#111'>&#9632;</span>/<span style='color:#bbb'>&#9633;</span>
        AI territory estimate (square size = ownership confidence, dead stones marked; circled number = that group's approximate points)</label>
      <label><input type='checkbox' id='bd-libs'>
        <span style='color:#e02424'>&#9312;</span> Liberties per group (coloured at &le;3: <span style='color:#e02424'>red 1</span>/<span style='color:#f76707'>orange 2</span>/<span style='color:#f2b200'>yellow 3</span>)</label>
      <label><input type='checkbox' id='bd-conn'>
        <span style='color:#2b6cb0'>&#9741;</span> Combined liberties (switch on, then click several <b>same-colour</b> groups to see their liberties once linked)</label>
    </div>
    <div class='bdest' id='bd-est-line'></div>
    <div class='bdconn' id='bd-conn-line'></div>
    <div class='bdbody' id='bd-body'></div>
    <div class='bdinfo' id='bd-info'></div>
  </div>
</div>
"""


PRACTICE_JS = """
<script>
(function(){
  var fp='all', fc='all', fpts=0, fwr=0, fst='all';

  // Mastered positions persist in the browser, keyed by game+move so the state
  // survives regenerating the report.
  var STORE='go_review_mastered';
  function load(){
    try{ return new Set(JSON.parse(localStorage.getItem(STORE)||'[]')); }
    catch(e){ return new Set(); }
  }
  function save(set){
    try{ localStorage.setItem(STORE, JSON.stringify(Array.from(set))); }
    catch(e){}
  }
  var mastered = load();

  function refreshCard(d){
    var done = mastered.has(d.getAttribute('data-key'));
    d.classList.toggle('done', done);
    var b = d.querySelector('.msbtn');
    if(b) b.innerHTML = done ? '&#8617; Move back to review' : '&#10003; Mark as mastered';
  }
  // Recompute EVERY filter-button count from the cards actually present in the
  // DOM (so deleting positions updates all the tallies, not just the filtered count).
  function setI(attr,val,n){
    var el=document.querySelector('i['+attr+'="'+val+'"]'); if(el) el.textContent=n; }
  function recount(){
    var byPhase={}, byCat={}, total=0, todo=0, done=0;
    document.querySelectorAll('.diag').forEach(function(d){
      total++;
      var ph=d.getAttribute('data-phase'); byPhase[ph]=(byPhase[ph]||0)+1;
      var cat=d.getAttribute('data-cat'); byCat[cat]=(byCat[cat]||0)+1;
      if(mastered.has(d.getAttribute('data-key'))) done++; else todo++;
    });
    setI('data-cp','all',total); setI('data-cc','all',total);
    document.querySelectorAll('i[data-cp]').forEach(function(el){
      var v=el.getAttribute('data-cp'); if(v!=='all') el.textContent=byPhase[v]||0; });
    document.querySelectorAll('i[data-cc]').forEach(function(el){
      var v=el.getAttribute('data-cc'); if(v!=='all') el.textContent=byCat[v]||0; });
    var ct=document.getElementById('cnt-todo'); if(ct) ct.textContent=todo;
    var cd=document.getElementById('cnt-done'); if(cd) cd.textContent=done;
  }
  window.toggleMaster = function(btn){
    var d = btn.closest('.diag');
    var k = d.getAttribute('data-key');
    if(mastered.has(k)) mastered.delete(k); else mastered.add(k);
    save(mastered);
    refreshCard(d);
    recount();
    apply();
  };

  function apply(){
    var shown=0, gms={};
    document.querySelectorAll('.diag').forEach(function(d){
      var okp = fp==='all' || d.getAttribute('data-phase')===fp;
      var okc = fc==='all' || d.getAttribute('data-cat')===fc;
      var okpts = parseFloat(d.getAttribute('data-pts')) >= fpts;
      var okwr = parseFloat(d.getAttribute('data-wr')) >= fwr;
      var done = mastered.has(d.getAttribute('data-key'));
      var okst = fst==='all' || (fst==='done'?done:!done);
      var okdt = (window.GR ? GR.inRange(d.getAttribute('data-date')) : true);
      var vis = okp && okc && okpts && okwr && okst && okdt;
      d.style.display = vis ? '' : 'none';
      if(vis){ shown++; gms[(d.getAttribute('data-key')||'').split('#')[0]]=1; }
    });
    var fl=document.getElementById('flcount');
    if(fl) fl.textContent=shown+' shown \u00B7 from '+
      Object.keys(gms).length+' game(s)';
  }
  function wire(attr, set){
    document.querySelectorAll('.navbtn['+attr+']').forEach(function(b){
      b.addEventListener('click', function(){
        set(b.getAttribute(attr));
        document.querySelectorAll('.navbtn['+attr+']').forEach(function(x){
          x.classList.toggle('on', x===b);});
        apply();
      });
    });
  }
  wire('data-fp', function(v){ fp=v; });
  wire('data-fc', function(v){ fc=v; });
  wire('data-fpts', function(v){ fpts=parseFloat(v); });
  wire('data-fwr', function(v){ fwr=parseFloat(v); });
  wire('data-fst', function(v){ fst=v; });

  document.querySelectorAll('.diag').forEach(refreshCard);
  recount();
  apply();
  document.addEventListener('grdate', apply);
  // notes load / change, or a blunder is deleted -> recount all + re-filter
  document.addEventListener('ymnotes', function(){ recount(); apply(); });

  // Full-board modal: click a card's diagram to see the whole board at that
  // position, with the actual move and KataGo's line toggleable.
  var modal=document.getElementById('bd-modal');
  var bdBody=document.getElementById('bd-body');
  function applyTogs(){
    if(!bdBody) return;
    var mv=bdBody.querySelector("[id$='-mv']");
    var ai=bdBody.querySelector("[id$='-ai']");
    var est=bdBody.querySelector("[id$='-est']");
    var estnum=bdBody.querySelector("[id$='-estnum']");
    var dead=bdBody.querySelector("[id$='-dead']");
    var libs=bdBody.querySelector("[id$='-libs']");
    var cmv=document.getElementById('bd-mv'), cai=document.getElementById('bd-ai');
    var ce=document.getElementById('bd-est');
    var cl=document.getElementById('bd-libs');
    if(mv) mv.style.display=(cmv&&cmv.checked)?'':'none';
    if(ai) ai.style.display=(cai&&cai.checked)?'':'none';
    if(est) est.style.display=(ce&&ce.checked)?'':'none';
    // Dead-stone X marks and per-group point numbers follow the AI-estimate toggle.
    if(dead) dead.style.display=(ce&&ce.checked)?'':'none';
    if(estnum) estnum.style.display=(ce&&ce.checked)?'':'none';
    if(libs) libs.style.display=(cl&&cl.checked)?'':'none';
    // The numeric result always shows (whenever the position has ownership data);
    // it is not hidden by the square overlay toggle.
  }
  function bdRepRel(){ var m=location.pathname.match(/^\/r\/(.+)$/);
    return m?decodeURIComponent(m[1].replace(/\/$/,'')):null; }
  function bdSetup(d){
    document.getElementById('bd-title').textContent=d.getAttribute('data-title')||'';
    document.getElementById('bd-info').textContent=d.getAttribute('data-info')||'';
    var cmv=document.getElementById('bd-mv'), cai=document.getElementById('bd-ai');
    if(cmv) cmv.checked=true; if(cai) cai.checked=true;
    var cl=document.getElementById('bd-libs'); if(cl) cl.checked=false;
    var cc=document.getElementById('bd-conn'); if(cc) cc.checked=false;
    connReset(false);
    var hasEst=d.getAttribute('data-est')==='1';
    var lbl=document.getElementById('bd-est-lbl');
    var ce=document.getElementById('bd-est');
    var line=document.getElementById('bd-est-line');
    if(lbl) lbl.style.display=hasEst?'':'none';
    if(ce) ce.checked=false;
    if(line){ var t=d.getAttribute('data-estline')||'';
              line.textContent=t; line.style.display=(hasEst&&t)?'':'none'; }
  }
  window.openBoard=function(el){
    var d=el.closest('.diag'); if(!d||!modal) return;
    bdSetup(d);
    modal.classList.add('open');
    var rel=bdRepRel();
    if(!rel){  // offline (file://): no server to render the full board
      bdBody.innerHTML="<p style='padding:24px;color:#8a7d6b'>The full board cannot be enlarged in offline viewing mode. "+
        "Open the report inside the app (double-click Mirror of Go.command) to zoom in and see the full variation.</p>";
      return;
    }
    bdBody.innerHTML="<p style='padding:24px;color:#8a7d6b'>Loading the full board...</p>";
    fetch('/api/board?report='+encodeURIComponent(rel)+
      '&game='+encodeURIComponent(d.getAttribute('data-game')||'')+
      '&move='+encodeURIComponent(d.getAttribute('data-move')||'')+'&t='+Date.now(),
      {cache:'no-store'})
    .then(function(r){ return r.ok?r.text():Promise.reject('HTTP '+r.status); })
    .then(function(svg){ bdBody.innerHTML=svg; applyTogs(); })
    .catch(function(e){ bdBody.innerHTML="<p style='padding:24px;color:#c53030'>"+
      "Load failed: "+e+"</p>"; });
  };
  window.closeBoard=function(){
    if(!modal) return; modal.classList.remove('open'); bdBody.innerHTML='';
  };
  var cmv=document.getElementById('bd-mv'); if(cmv) cmv.addEventListener('change', applyTogs);
  var cai=document.getElementById('bd-ai'); if(cai) cai.addEventListener('change', applyTogs);
  var cest=document.getElementById('bd-est'); if(cest) cest.addEventListener('change', applyTogs);
  var clib=document.getElementById('bd-libs'); if(clib) clib.addEventListener('change', applyTogs);
  if(modal) modal.addEventListener('click', function(e){ if(e.target===modal) closeBoard(); });
  document.addEventListener('keydown', function(e){ if(e.key==='Escape') closeBoard(); });

  // ---- Connect-liberties tool ----------------------------------------------
  // Pick several same-colour groups and see how many liberties they'd have once
  // joined; warn when they can't actually be connected. The board snapshot is
  // read from the SVG's data-board attribute so everything runs client-side.
  var connOn=false, connSel={};            // group key -> {color, stones[], key}
  var connLine=document.getElementById('bd-conn-line');
  var connHint='Combined liberties: click same-colour groups on the board (as many as you like); click again to deselect.';

  function connSvg(){ return bdBody ? bdBody.querySelector('svg') : null; }
  function connLayer(){ return bdBody ? bdBody.querySelector("[id$='-conn']") : null; }
  function boardOf(svg){
    return {n:parseInt(svg.getAttribute('data-n'),10),
            pad:parseFloat(svg.getAttribute('data-pad')),
            cell:parseFloat(svg.getAttribute('data-cell')),
            s:svg.getAttribute('data-board')||''};
  }
  function connClear(){
    connSel={};
    var g=connLayer(); if(g) g.innerHTML='';
    if(connLine){ connLine.innerHTML=''; connLine.style.display='none'; }
  }
  function connReset(on){
    connOn=on; connClear();
    if(bdBody) bdBody.classList.toggle('connmode', on);
    if(on && connLine){ connLine.style.display=''; connLine.innerHTML=connHint; }
  }
  function clickGrid(svg, b, evt){
    var pt=svg.createSVGPoint(); pt.x=evt.clientX; pt.y=evt.clientY;
    var ctm=svg.getScreenCTM(); if(!ctm) return null;
    var loc=pt.matrixTransform(ctm.inverse());
    var x=Math.round((loc.x-b.pad)/b.cell), y=Math.round((loc.y-b.pad)/b.cell);
    if(x<0||x>=b.n||y<0||y>=b.n) return null;
    if(Math.abs(loc.x-(b.pad+x*b.cell))>b.cell*0.5) return null;
    if(Math.abs(loc.y-(b.pad+y*b.cell))>b.cell*0.5) return null;
    return {x:x,y:y};
  }
  function groupAt(b,x,y){
    var c=b.s.charAt(y*b.n+x); if(c==='0'||c==='') return null;
    var seen={}, st=[[x,y]], stones=[]; seen[y*b.n+x]=1;
    while(st.length){
      var p=st.pop(); stones.push(p);
      var nb=[[p[0]+1,p[1]],[p[0]-1,p[1]],[p[0],p[1]+1],[p[0],p[1]-1]];
      for(var k=0;k<4;k++){
        var qx=nb[k][0], qy=nb[k][1];
        if(qx<0||qx>=b.n||qy<0||qy>=b.n) continue;
        var idx=qy*b.n+qx;
        if(b.s.charAt(idx)===c && !seen[idx]){ seen[idx]=1; st.push([qx,qy]); }
      }
    }
    stones.sort(function(a,c2){ return (a[1]*b.n+a[0])-(c2[1]*b.n+c2[0]); });
    return {color:c, stones:stones, key:stones[0][0]+','+stones[0][1]};
  }
  function libsOf(b, stoneSet){
    var libs={};
    Object.keys(stoneSet).forEach(function(k){
      var xy=k.split(','), x=+xy[0], y=+xy[1];
      var nb=[[x+1,y],[x-1,y],[x,y+1],[x,y-1]];
      nb.forEach(function(q){
        if(q[0]<0||q[0]>=b.n||q[1]<0||q[1]>=b.n) return;
        var kk=q[0]+','+q[1];
        if(stoneSet[kk]) return;
        if(b.s.charAt(q[1]*b.n+q[0])==='0') libs[kk]=1;
      });
    });
    return libs;
  }
  function draw(b, rings, libKeys, connectors){
    var layer=connLayer(); if(!layer) return;
    function SX(x){ return (b.pad+x*b.cell); }
    function SY(y){ return (b.pad+y*b.cell); }
    var out=[];
    rings.forEach(function(s){
      out.push('<circle cx="'+SX(s[0])+'" cy="'+SY(s[1])+'" r="'+(b.cell*0.5).toFixed(1)
        +'" fill="none" stroke="#2b6cb0" stroke-width="2"/>');
    });
    (libKeys||[]).forEach(function(k){
      var xy=k.split(',');
      out.push('<circle cx="'+SX(+xy[0])+'" cy="'+SY(+xy[1])+'" r="'+(b.cell*0.16).toFixed(1)
        +'" fill="#17b3c4"/>');
    });
    (connectors||[]).forEach(function(k){
      var xy=k.split(','), cx=SX(+xy[0]), cy=SY(+xy[1]), s=b.cell*0.34;
      out.push('<rect x="'+(cx-s/2).toFixed(1)+'" y="'+(cy-s/2).toFixed(1)+'" width="'
        +s.toFixed(1)+'" height="'+s.toFixed(1)+'" fill="#2f9e44" stroke="#fff" '
        +'stroke-width="1" transform="rotate(45 '+cx+' '+cy+')"/>');
    });
    layer.innerHTML=out.join('');
  }
  function recompute(b){
    var groups=Object.keys(connSel).map(function(k){ return connSel[k]; });
    var rings=[];
    groups.forEach(function(g){ g.stones.forEach(function(s){ rings.push(s); }); });
    if(!groups.length){
      draw(b, rings, [], []);
      if(connLine){ connLine.style.display=''; connLine.innerHTML=connHint; }
      return;
    }
    var selColor=null, mixed=false;
    groups.forEach(function(g){
      if(selColor===null) selColor=g.color; else if(selColor!==g.color) mixed=true;
    });
    if(mixed){
      draw(b, rings, [], []);
      if(connLine){ connLine.style.display='';
        connLine.innerHTML='<span class="bad">Cannot link: the selected groups are different colours</span> (only same-colour groups can be linked).'; }
      return;
    }
    var stoneSet={};
    groups.forEach(function(g){ g.stones.forEach(function(s){ stoneSet[s[0]+','+s[1]]=1; }); });
    if(groups.length===1){
      var lk1=Object.keys(libsOf(b, stoneSet));
      draw(b, rings, lk1, []);
      if(connLine){ connLine.style.display='';
        connLine.innerHTML='This group has <b>'+lk1.length+'</b> liberties.'; }
      return;
    }
    // connectors: empty points orthogonally adjacent to >=2 selected groups.
    var adj={};
    groups.forEach(function(g,gi){
      g.stones.forEach(function(s){
        var nb=[[s[0]+1,s[1]],[s[0]-1,s[1]],[s[0],s[1]+1],[s[0],s[1]-1]];
        nb.forEach(function(q){
          if(q[0]<0||q[0]>=b.n||q[1]<0||q[1]>=b.n) return;
          if(b.s.charAt(q[1]*b.n+q[0])!=='0') return;
          var kk=q[0]+','+q[1]; (adj[kk]=adj[kk]||{})[gi]=1;
        });
      });
    });
    var parent=groups.map(function(_,i){ return i; });
    function find(i){ while(parent[i]!==i){ parent[i]=parent[parent[i]]; i=parent[i]; } return i; }
    var connectors=[];
    Object.keys(adj).forEach(function(kk){
      var gs=Object.keys(adj[kk]).map(Number);
      if(gs.length>=2){ connectors.push(kk);
        for(var t=1;t<gs.length;t++) parent[find(gs[0])]=find(gs[t]); }
    });
    var root=find(0), allConn=groups.every(function(_,i){ return find(i)===root; });
    if(!allConn){
      draw(b, rings, [], []);
      if(connLine){ connLine.style.display='';
        connLine.innerHTML='<span class="bad">Cannot link: these groups share no point that connects them directly</span>'
          +' (too far apart -- it would take several moves, so it is not counted here).'; }
      return;
    }
    var merged={};
    Object.keys(stoneSet).forEach(function(k){ merged[k]=1; });
    connectors.forEach(function(k){ merged[k]=1; });
    var lk=Object.keys(libsOf(b, merged));
    draw(b, rings, lk, connectors);
    if(connLine){ connLine.style.display='';
      connLine.innerHTML='Linking <b>'+groups.length+'</b> groups \u2192 <b>'+lk.length+'</b> liberties in total'
        +' (requires playing the <b>'+connectors.length+'</b> connecting points, shown as green squares; light blue dots are liberties).'; }
  }
  if(bdBody) bdBody.addEventListener('click', function(evt){
    if(!connOn) return;
    var svg=connSvg(); if(!svg) return;
    var b=boardOf(svg);
    var gp=clickGrid(svg,b,evt); if(!gp) return;
    var g=groupAt(b, gp.x, gp.y); if(!g) return;
    if(connSel[g.key]) delete connSel[g.key]; else connSel[g.key]=g;
    recompute(b);
  });
  var cconn=document.getElementById('bd-conn');
  if(cconn) cconn.addEventListener('change', function(){ connReset(cconn.checked); });

  // Cycle through this blunder's similar positions. Clear filters first so the
  // target is visible, then scroll to it and flash a highlight.
  window.goSim = function(btn){
    var ids=(btn.getAttribute('data-sims')||'').split(',').filter(Boolean);
    if(!ids.length) return;
    var k=parseInt(btn.getAttribute('data-i')||'0',10) % ids.length;
    btn.setAttribute('data-i', k+1);
    ["[data-fp='all']","[data-fc='all']","[data-fpts='0']","[data-fwr='0']",
     "[data-fst='all']"]
      .forEach(function(sel){
        var b=document.querySelector('.navbtn'+sel); if(b) b.click();
      });
    var el=document.getElementById(ids[k]);
    if(el){
      el.scrollIntoView({behavior:'smooth', block:'center'});
      el.classList.add('hl');
      setTimeout(function(){ el.classList.remove('hl'); }, 1600);
    }
  };
})();
</script>
"""


# ---- HTML shell ------------------------------------------------------------

CSS = """
:root{
 --paper:#f6f1e8; --card:#fffdf9; --line:#e9dfce; --line-soft:#f1ead9;
 --ink:#3d352e; --ink-soft:#6f6357; --muted:#9a8d7b;
 --espresso:#2a241f; --espresso-2:#37302a; --espresso-line:#3f382f;
 --on-dark:#e7ddce; --on-dark-soft:#b0a18d;
 --amber:#b7791f; --amber-ink:#8a5a12; --amber-soft:#f6ecd6; --amber-line:#e6d3ab;}
body{font-family:-apple-system,"PingFang SC",Segoe UI,Helvetica,Arial,sans-serif;
 margin:0;color:var(--ink);line-height:1.5;background:var(--paper)}
.layout{display:flex;align-items:flex-start;min-height:100vh}
.sidebar{position:sticky;top:0;align-self:flex-start;height:100vh;width:212px;
 flex:none;box-sizing:border-box;background:var(--espresso);color:var(--on-dark);
 padding:22px 14px;overflow-y:auto}
.brand{font-size:18px;font-weight:700;color:#fff;line-height:1.25}
.brand span{display:block;font-size:10.5px;font-weight:500;color:var(--amber);
 letter-spacing:1.5px;margin-top:3px}
.sidebar nav{display:flex;flex-direction:column;gap:3px;margin-top:24px}
.navlink{font:inherit;font-size:14px;text-align:left;cursor:pointer;border:none;
 background:transparent;color:var(--on-dark);border-radius:8px;padding:9px 12px;
 display:flex;align-items:center;gap:8px;transition:background .12s}
.navlink:hover{background:var(--espresso-2)}
.navlink.active{background:var(--amber);color:#fff;font-weight:600}
.navlink .dot{width:7px;height:7px;border-radius:50%;background:#6b5e4a;flex:none}
.navlink.active .dot{background:#ffe9bf}
.sidebar .meta{font-size:11px;color:var(--on-dark-soft);margin-top:26px;
 line-height:1.6;border-top:1px solid var(--espresso-line);padding-top:14px}
.content{flex:1;min-width:0;max-width:1000px;margin:0 auto;
 padding:30px 34px;box-sizing:border-box;background:var(--card);min-height:100vh}
.page{display:none}.page.active{display:block}
.page>h1:first-child,.page>h2:first-child{margin-top:0}
@media(max-width:760px){
 .layout{flex-direction:column}
 .sidebar{position:static;height:auto;width:auto}
 .sidebar nav{flex-direction:row;flex-wrap:wrap;margin-top:14px;gap:6px}
 .navlink{font-size:13px;padding:7px 11px}
 .content{padding:20px 16px}
}
h1{font-size:24px;margin-bottom:4px}h2{font-size:19px;margin-top:34px;
 border-bottom:2px solid var(--line);padding-bottom:6px}
h3{font-size:16px;margin-bottom:4px}
.sub{color:var(--ink-soft);font-size:13px;margin-top:0}
.cards{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0}
.card{flex:1;min-width:130px;background:var(--card);border:1px solid var(--line);
 border-radius:8px;padding:14px 16px}
.card .v{font-size:26px;font-weight:800;letter-spacing:-.01em;
 font-variant-numeric:tabular-nums}.card .l{font-size:12px;color:var(--ink-soft)}
.ovctl{margin:10px 0 0}
.ovctl .exw{display:inline-flex;align-items:center;gap:6px;font-size:13px;
 color:#4a5568;cursor:pointer;user-select:none}
.ovctl .exw input{cursor:pointer}
.ovctl .exwnote{margin-left:10px;font-size:12px;color:#a0aec0}
.improve{margin:6px 0 16px;padding:14px 16px;border-radius:12px;
 border:1px solid #e2e8f0;background:#f7fafc}
.improve .impl{font-size:11px;letter-spacing:.08em;color:#718096;font-weight:700}
.improve .impv{font-size:22px;font-weight:800;margin:3px 0 5px;
 display:flex;align-items:baseline;gap:8px}
.improve .impv .ar{font-size:18px}
.improve .impv .pct{font-size:14px;font-weight:700;opacity:.85}
.improve .impd{font-size:13px;color:#4a5568;line-height:1.55}
.imp-good{background:#f0fff4;border-color:#9ae6b4}.imp-good .impv{color:#276749}
.imp-bad{background:#fff5f5;border-color:#feb2b2}.imp-bad .impv{color:#c53030}
.imp-flat{background:#f7fafc;border-color:#e2e8f0}.imp-flat .impv{color:#4a5568}
.imp-na .impv{color:#718096;font-size:16px}
.charts2{display:grid;grid-template-columns:1fr;gap:14px}
.chart{min-width:0}
.chart .pt{cursor:pointer}.chart .pt:hover{fill:rgba(0,0,0,.06)}
#tipbox{position:fixed;z-index:9999;pointer-events:none;display:none;
 background:#1a202c;color:#fff;font-size:12px;line-height:1.3;padding:5px 9px;
 border-radius:6px;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,.25)}
@media(max-width:760px){.charts2{grid-template-columns:1fr}}
table{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}
th,td{border-bottom:1px solid #edf2f7;padding:6px 8px;text-align:left}
th{color:#718096;font-weight:600}
.rec{background:#ebf8ff;border-left:4px solid #3182ce;padding:10px 14px;
 border-radius:4px;margin:8px 0;font-size:14px}
.coach{background:#fffaf0;border:1px solid #f6e0b5;border-left:4px solid #dd6b20;
 border-radius:8px;padding:6px 18px;font-size:14px;line-height:1.7}
.coach ul,.coach ol{margin:6px 0 12px;padding-left:22px}
.coach li{margin:4px 0}.coach b{color:#9c4221}
.game{border:1px solid #e2e8f0;border-radius:10px;padding:16px;margin:16px 0}
.win{color:#2f855a;font-weight:600}.loss{color:#c53030;font-weight:600}
.score{background:#f7fafc;border:1px solid #e2e8f0;border-radius:8px;
 padding:10px 14px;margin-top:12px}
.score .scl{font-size:12px;font-weight:700;color:#718096;margin-bottom:2px}
.score .scn{font-size:16px;margin-bottom:2px}
.score table{margin-top:6px}
.pill{display:inline-block;background:var(--amber-soft);color:var(--amber-ink);
 border-radius:12px;padding:1px 9px;font-size:12px;margin-left:6px}
.mv{font-variant-numeric:tabular-nums}.big{color:#c53030;font-weight:600}
.diags{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));
 gap:16px}
/* ---- game trajectory ---- */
.cvbox{display:flex;flex-wrap:wrap;align-items:stretch;gap:14px 22px;margin:14px 0;
 padding:14px 18px;background:var(--card);border:1px solid var(--line);border-radius:12px}
.cvgrp{display:flex;gap:22px}
.cvstat{min-width:130px}
.cvstat .cvv{font-size:30px;font-weight:800;line-height:1.1;font-variant-numeric:tabular-nums;
 color:var(--ink)}
.cvstat .cvv.cv-good{color:#2f855a}.cvstat .cvv.cv-mid{color:var(--amber-ink)}
.cvstat .cvv.cv-bad{color:#c53030}
.cvstat .cvl{font-size:12.5px;color:var(--ink-soft);font-weight:700;margin-top:2px}
.cvstat .cvl span{display:block;font-size:11px;color:var(--muted);font-weight:400;margin-top:1px}
.cvnote{flex:1;min-width:220px;align-self:center;font-size:12px;color:var(--muted);
 line-height:1.6;border-left:1px solid var(--line);padding-left:14px}
.tjsum{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
.tjchip{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;
 border-radius:16px;padding:4px 12px;border:1px solid var(--line);cursor:pointer;
 user-select:none;transition:box-shadow .1s,filter .1s}
.tjchip:hover{filter:brightness(.97)}
.tjchip.on{box-shadow:inset 0 0 0 2px currentColor}
.tjchip.tjall{background:#efe9df;color:var(--ink-soft)}
.tjchip b{font-variant-numeric:tabular-nums}
.tjchip.t-win{background:#eaf6ee;border-color:#bfe3cb;color:#276749}
.tjchip.t-come{background:var(--amber-soft);border-color:var(--amber-line);color:var(--amber-ink)}
.tjchip.t-loss{background:#f3f0eb;border-color:var(--line);color:#7a6f62}
.tjchip.t-bad{background:#fdecec;border-color:#f3c0c0;color:#b03535}
.tjchip.t-crash{background:#fbe3e3;border-color:#eba9a9;color:#a02020}
.tjins{margin:6px 0 14px;padding-left:20px;font-size:13px;line-height:1.7;color:var(--ink-soft)}
.tjins b{color:var(--ink)}
.trajgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}
.trajcard{border:1px solid var(--line);border-radius:10px;padding:12px 12px 10px;
 background:var(--card)}
.tjhead{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px}
.tjbadge{font-size:12px;font-weight:700;border-radius:8px;padding:2px 9px}
.tjbadge.t-win{background:#eaf6ee;color:#276749}
.tjbadge.t-come{background:var(--amber-soft);color:var(--amber-ink)}
.tjbadge.t-loss{background:#f3f0eb;color:#7a6f62}
.tjbadge.t-bad{background:#fdecec;color:#b03535}
.tjbadge.t-crash{background:#fbe3e3;color:#a02020}
.tjshape{font-size:14px;letter-spacing:1px}
.tjspark{border:1px solid var(--line-soft);border-radius:7px;overflow:hidden;background:#fff}
.tjmeta{font-size:11.5px;color:var(--muted);margin-top:7px;line-height:1.4}
.diag{position:relative;border:1px solid #e2e8f0;border-radius:8px;padding:10px;
 text-align:center}
.diag.done{opacity:.6}
.diag.done::after{content:'Mastered';position:absolute;top:8px;right:8px;
 background:#276749;color:#fff;font-size:10px;font-weight:700;border-radius:10px;
 padding:2px 8px}
.msbtn{display:inline-block;font:inherit;font-size:11.5px;cursor:pointer;
 border:1px solid #9ae6b4;background:#f0fff4;color:#276749;border-radius:6px;
 padding:4px 9px;margin-top:8px;margin-left:6px}
.msbtn:hover{background:#c6f6d5}
.diag.done .msbtn{border-color:#cbd5e0;background:#edf2f7;color:#4a5568}
.diag svg{max-width:100%;height:auto}
.dcap{font-size:12px;margin-top:6px;text-align:left;line-height:1.45}
.dline{font-size:11.5px;color:#2d3748;text-align:left;margin-top:5px;
 font-variant-numeric:tabular-nums;background:#f7fafc;border-radius:4px;
 padding:3px 6px}
.dname{font-size:12px;font-weight:700;color:#c05621;text-align:left;
 margin-top:8px}
.dtip{font-size:11.5px;color:#4a5568;text-align:left;margin-top:3px;
 line-height:1.45}
.dsub{font-size:11px;color:#718096;text-align:left;margin-top:6px}
.navbar{margin:10px 0 16px}
.navrow{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:6px 0}
.navlbl{font-size:12px;font-weight:700;color:#718096;width:46px;flex:none}
.navbtn{font:inherit;font-size:12px;cursor:pointer;border:1px solid var(--line);
 background:var(--card);color:var(--ink);border-radius:14px;padding:4px 11px}
.navbtn:hover{background:var(--amber-soft);border-color:var(--amber-line)}
.navbtn.on{background:var(--amber);border-color:var(--amber);color:#fff}
.navbtn i{font-style:normal;opacity:.7;font-size:11px;margin-left:3px}
.navbtn.on i{opacity:.9}
.datebar{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:10px 0 14px;
 padding:9px 12px;background:var(--line-soft);border:1px solid var(--line);
 border-radius:10px}
.datebar input[type=date]{font:inherit;font-size:12.5px;border:1px solid #cbd5e0;
 border-radius:8px;padding:3px 7px;color:#2d3748;background:#fff}
.datebar .dfsep{color:#a0aec0;font-size:13px}
.datebar .dfreset{margin-left:auto}
.simbtn{display:inline-block;font:inherit;font-size:11.5px;cursor:pointer;
 border:1px solid #b794f4;background:#faf5ff;color:#6b46c1;border-radius:6px;
 padding:4px 9px;margin-top:8px}
.simbtn:hover{background:#e9d8fd}
.diag.hl{box-shadow:0 0 0 3px #6b46c1}
.delbtn{margin-top:6px;margin-left:6px;border:1px solid #f0c8c0;background:#fff;
 color:#b5462f;border-radius:7px;padding:5px 10px;font-size:12.5px;cursor:pointer}
.delbtn:hover{background:#fbeae6;border-color:#e08a75}
.notebtn{margin-top:6px;margin-left:6px;border:1px solid #cbd5e0;background:#fff;
 color:#4a5568;border-radius:7px;padding:5px 10px;font-size:12.5px;cursor:pointer}
.notebtn:hover{background:#f7fafc;border-color:#6b46c1;color:#6b46c1}
.diag.hasnote{box-shadow:0 0 0 2px #d6bcfa}
.diag.hasnote .notebtn{background:#f3effc;border-color:#9f7aea;color:#6b46c1}
.ndot{color:#6b46c1;font-weight:700}
.notectl{margin:6px 0 14px}
.notectl button{border:1px solid #cbd5e0;background:#fff;border-radius:8px;
 padding:7px 12px;font-size:13px;cursor:pointer;color:#4a5568}
.notectl button:hover{border-color:#6b46c1;color:#6b46c1}
.nmodal{position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:1000;display:none;
 align-items:center;justify-content:center;padding:16px}
.nmodal.open{display:flex}
.nbox{background:#fff;border-radius:12px;max-width:560px;width:100%;max-height:88vh;
 overflow-y:auto;box-shadow:0 12px 40px rgba(0,0,0,.3)}
.nhd{position:sticky;top:0;background:#1a202c;color:#fff;padding:12px 16px;display:flex;
 align-items:center;gap:8px;border-radius:12px 12px 0 0}
.nhd .nmt{font-size:12px;color:#cbd5e1;flex:1;overflow:hidden;text-overflow:ellipsis;
 white-space:nowrap}
.nhd .nx{background:none;border:none;color:#fff;font-size:22px;cursor:pointer;line-height:1}
.nbd{padding:14px 16px}
.nbd label{display:block;font-size:12px;color:#718096;font-weight:600;margin:12px 0 4px}
.nbd select,.nbd input,.nbd textarea{width:100%;box-sizing:border-box;padding:8px 9px;
 border:1px solid #cdd3da;border-radius:8px;font-size:13.5px;font-family:inherit}
.nmeta{font-size:12.5px;color:#4a5568;background:#f7fafc;border-radius:8px;padding:8px 10px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chips .chip{display:inline-flex;align-items:center;gap:4px;border:1px solid #cdd3da;
 border-radius:16px;padding:4px 10px;font-size:12.5px;color:#4a5568;cursor:pointer;margin:0}
.chips .chip input{width:auto;margin:0}
.chips .chip:has(input:checked){background:var(--amber-soft);border-color:var(--amber);
 color:var(--amber-ink);font-weight:600}
.vcpanel{margin:10px 0 14px;padding:14px 16px;border:1px solid var(--amber-line);
 background:var(--amber-soft);border-radius:12px}
.vcrow{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.vcbtn{border:1px solid var(--amber);background:var(--amber);color:#fff;
 border-radius:9px;padding:9px 16px;font-size:14px;font-weight:700;cursor:pointer}
.vcbtn:hover{filter:brightness(1.05)}
.vcbtn.on{background:#c0392b;border-color:#a5281b;animation:recpulse 1s infinite}
.vctimer{font-variant-numeric:tabular-nums;font-weight:700;color:var(--espresso);
 font-size:14px}
.vcstat{font-size:12.5px}
/* transcription heartbeat: real progress through the audio, not a spinner */
.vcbar{display:none;height:6px;border-radius:999px;background:#eadfc6;
 overflow:hidden;margin:0 0 8px}
.vcbar>i{display:block;height:100%;width:0;border-radius:999px;
 background:var(--amber,#b7791f);transition:width .35s ease}
.vcbar>i.idle{width:35%;animation:vcslide 1.1s ease-in-out infinite;
 background:#d8b075}
@keyframes vcslide{0%{margin-left:-35%}100%{margin-left:100%}}
.vchint{margin:8px 0 8px;line-height:1.6}
.vctext{width:100%;box-sizing:border-box;border:1px solid var(--amber-line);
 border-radius:8px;padding:9px 11px;font-size:13.5px;line-height:1.65;
 background:#fff;color:var(--ink);resize:vertical}
.vcsave{border:1px solid var(--amber-line);background:#fff;color:var(--amber-ink);
 border-radius:8px;padding:7px 14px;font-size:13px;font-weight:600;cursor:pointer}
.vcsave:hover{background:#efe0bf}
.clrbtn{border:1px solid #e2c9a0;background:#fff;color:#9a6a2a;border-radius:8px;
 padding:6px 12px;font-size:12.5px;font-weight:600;cursor:pointer}
.clrbtn:hover{background:#fbefd9;border-color:#d8b075}
.vcfloat{display:none;position:fixed;right:18px;bottom:18px;z-index:9999;
 align-items:center;gap:10px;background:#c0392b;color:#fff;border-radius:999px;
 padding:10px 16px;font-size:13.5px;font-weight:700;
 box-shadow:0 6px 20px rgba(0,0,0,.25)}
.vcfloat button{border:0;background:rgba(255,255,255,.22);color:#fff;
 border-radius:999px;padding:6px 12px;font-size:12.5px;font-weight:700;cursor:pointer}
.vcfloat button:hover{background:rgba(255,255,255,.35)}
.vcdot{width:10px;height:10px;border-radius:50%;background:#fff;
 animation:recpulse 1s infinite}
.smdbox{font-size:14.5px;line-height:1.75;color:var(--ink);max-width:920px}
.smdbox h1{font-size:21px;margin:6px 0 12px}
.smdbox h2{font-size:17.5px;margin:20px 0 8px;padding-top:6px;
 border-top:1px solid var(--amber-line)}
.smdbox h3{font-size:15px;margin:14px 0 6px;color:var(--espresso)}
.smdbox h4{font-size:13.5px;margin:10px 0 4px;color:var(--muted)}
.smdbox p{margin:8px 0}
.smdbox ul,.smdbox ol{margin:8px 0;padding-left:22px}
.smdbox li{margin:3px 0}
.smdbox blockquote{margin:10px 0;padding:8px 14px;border-left:3px solid var(--amber);
 background:var(--amber-soft);color:var(--espresso);border-radius:0 8px 8px 0}
.smdbox hr{border:0;border-top:1px solid var(--amber-line);margin:16px 0}
.smdbox code{background:var(--amber-soft);padding:1px 5px;border-radius:4px;font-size:13px}
.smdbox table.smd{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px}
.smdbox table.smd th,.smdbox table.smd td{border:1px solid var(--amber-line);
 padding:7px 9px;text-align:left;vertical-align:top}
.smdbox table.smd thead th{background:var(--amber-soft);color:var(--espresso);font-weight:700}
.smdbox table.smd tbody tr:nth-child(even){background:#fbf7ef}
.recrow{display:flex;gap:10px;align-items:center;margin:2px 0 6px}
.recbtn{border:1px solid var(--amber-line);background:var(--amber-soft);
 color:var(--amber-ink);border-radius:8px;padding:6px 12px;font-size:12.5px;
 font-weight:600;cursor:pointer}
.recbtn:hover{background:#efe0bf}
.recbtn.on{background:#fbe3e3;border-color:#eba9a9;color:#a02020;
 animation:recpulse 1s infinite}
@keyframes recpulse{50%{opacity:.55}}
.addrow{display:flex;gap:8px;margin-top:8px}
.addrow input{flex:1}
.addbtn{flex:none;white-space:nowrap;border:1px solid var(--amber-line);
 background:var(--amber-soft);color:var(--amber-ink);border-radius:8px;
 padding:8px 12px;font-size:12.5px;font-weight:600;cursor:pointer}
.addbtn:hover{background:#efe0bf}
.nbtns{margin-top:14px;display:flex;align-items:center;gap:10px}
.nbtns .nsave{background:#6b46c1;color:#fff;border:none;border-radius:8px;padding:9px 20px;
 font-weight:700;cursor:pointer}
.nbtns .ndel{background:#fff;color:#c53030;border:1px solid #fbb6b6;border-radius:8px;
 padding:9px 14px;cursor:pointer}
.nstat{font-size:12.5px;color:#718096}
.nsg{margin:10px 0}.nsg ul{margin:6px 0 0;padding-left:20px}.nsg li{font-size:13px;margin:2px 0}
.fbbtn{font:inherit;font-size:12px;cursor:pointer;border:1px solid #cbd5e0;
 background:#fff;border-radius:6px;padding:3px 9px}
.fbbtn:hover{background:#f7fafc}
.fbpanel{padding:6px 2px}
.fbtogs{display:flex;gap:14px;margin-bottom:4px}
.fbtog{font-size:12px;color:#4a5568;cursor:pointer;user-select:none}
.fbtog input{vertical-align:middle;margin-right:4px}
.flcount{font-size:12.5px;color:#4a5568;font-weight:600;margin:2px 0 14px}
.flrow{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:2px 0 14px}
.flrow .flcount{margin:0}
/* review-summary history: older versions kept, collapsed under the latest */
.sumexp{border:1px solid var(--amber-line);background:var(--card);
 color:var(--amber-ink);border-radius:8px;padding:7px 14px;font-size:12.5px;
 font-weight:600;cursor:pointer;text-decoration:none;white-space:nowrap}
.sumexp:hover{background:var(--amber-soft)}
.sumhist{margin-top:26px;padding-top:16px;border-top:1px solid var(--line)}
.sumhist-h{font-size:13px;font-weight:700;color:var(--ink-soft);
 margin-bottom:8px;display:flex;align-items:center;gap:8px}
.sumhist-h .nstat{font-weight:600;color:var(--muted);font-size:12px}
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
.dimg{cursor:zoom-in;display:block}
.dimg svg{display:block}
.dhint{font-size:10.5px;color:#a0aec0;margin-top:3px}
.bdmask{display:none;position:fixed;inset:0;z-index:10000;
 background:rgba(0,0,0,.55);align-items:center;justify-content:center;padding:18px}
.bdmask.open{display:flex}
.bdbox{background:#fff;border-radius:12px;max-width:640px;width:100%;
 max-height:92vh;overflow:auto;padding:18px 20px;position:relative;
 box-shadow:0 10px 40px rgba(0,0,0,.3)}
.bdclose{position:absolute;top:8px;right:12px;border:none;background:transparent;
 font-size:26px;line-height:1;cursor:pointer;color:#718096}
.bdtitle{font-size:15px;font-weight:700;margin:0 30px 8px 0}
.bdtogs{display:flex;gap:16px;margin-bottom:8px;flex-wrap:wrap}
.bdtogs label{font-size:13px;color:#4a5568;cursor:pointer;user-select:none}
.bdtogs input{vertical-align:middle;margin-right:5px}
.bdbody{text-align:center}
.bdbody svg{max-width:560px !important;width:100% !important;height:auto}
.bdinfo{font-size:12.5px;color:#2d3748;margin-top:10px;line-height:1.55;
 background:#f7fafc;border-radius:6px;padding:8px 10px;text-align:left}
.bdest{display:none;font-size:13px;font-weight:600;color:#1a202c;
 margin:2px 0 8px;text-align:center}
.bdconn{display:none;font-size:13.5px;color:#1a202c;margin:2px 0 8px;
 text-align:center;background:#ebf3fb;border:1px solid #cfe0f2;
 border-radius:6px;padding:7px 10px;line-height:1.5}
.bdconn b{color:#2b6cb0}
.bdconn .bad{color:#c53030;font-weight:700}
.bdbody.connmode svg{cursor:pointer}
"""


GAMES_JS = """
<script>
(function(){
  var fr='all', fc='all', fb=0, fa=0;
  function apply(){
    var shown=0;
    document.querySelectorAll('#page-games .game').forEach(function(d){
      var okr = fr==='all' || d.getAttribute('data-result')===fr;
      var okc = fc==='all' || d.getAttribute('data-color')===fc;
      var okb = parseInt(d.getAttribute('data-blunders')||'0',10) >= fb;
      var oka = parseFloat(d.getAttribute('data-avg')||'0') >= fa;
      var okdt = (window.GR ? GR.inRange(d.getAttribute('data-date')) : true);
      var vis = okr && okc && okb && oka && okdt;
      d.style.display = vis ? '' : 'none';
      if(vis) shown++;
    });
    var el=document.getElementById('gmcount');
    if(el) el.textContent='Showing '+shown+' game(s)';
  }
  function wire(attr, set){
    document.querySelectorAll('#page-games .navbtn['+attr+']').forEach(function(b){
      b.addEventListener('click', function(){
        set(b.getAttribute(attr));
        document.querySelectorAll('#page-games .navbtn['+attr+']').forEach(
          function(x){ x.classList.toggle('on', x===b); });
        apply();
      });
    });
  }
  wire('data-fr', function(v){ fr=v; });
  wire('data-fc', function(v){ fc=v; });
  wire('data-fb', function(v){ fb=parseInt(v,10); });
  wire('data-fa', function(v){ fa=parseFloat(v); });
  apply();
  document.addEventListener('grdate', apply);
})();
</script>
"""


TOOLTIP_JS = """
<div id="tipbox"></div>
<script>
(function(){
  var box=document.getElementById('tipbox');
  function move(e){
    box.style.left=(e.clientX+12)+'px';
    box.style.top=(e.clientY+12)+'px';
  }
  document.addEventListener('mouseover', function(e){
    var t=e.target;
    if(t && t.classList && t.classList.contains('pt')){
      box.textContent=t.getAttribute('data-tip')||'';
      box.style.display='block';
      move(e);
    }
  });
  document.addEventListener('mousemove', function(e){
    if(box.style.display==='block') move(e);
  });
  document.addEventListener('mouseout', function(e){
    if(e.target && e.target.classList && e.target.classList.contains('pt')){
      box.style.display='none';
    }
  });
})();
</script>
"""


NAV_JS = """
<script>
(function(){
  var links=document.querySelectorAll('.navlink');
  function show(id){
    document.querySelectorAll('.page').forEach(function(s){
      s.classList.toggle('active', s.id==='page-'+id);
    });
    links.forEach(function(l){
      l.classList.toggle('active', l.getAttribute('data-page')===id);
    });
    window.scrollTo(0,0);
    if(location.hash!=='#'+id) history.replaceState(null,'','#'+id);
  }
  links.forEach(function(l){
    l.addEventListener('click', function(){ show(l.getAttribute('data-page')); });
  });
  var h=(location.hash||'').replace('#','');
  if(h && document.getElementById('page-'+h)) show(h);
})();
</script>
"""


TRAJ_JS = r"""
<script>
(function(){
  var LABEL={wire_win:'Led throughout \u00b7 solid win',
    comeback:'Comeback win \u00b7 behind then ahead',
    seesaw_win:'Seesaw \u00b7 narrow win',wire_loss:'Behind throughout',
    blew_lead:'Lead thrown away',
    collapse:'Endgame collapse \u00b7 one step short',
    narrow_loss:'Seesaw \u00b7 narrow loss'};
  var CLS={wire_win:'t-win',comeback:'t-come',seesaw_win:'t-win',
    wire_loss:'t-loss',blew_lead:'t-bad',collapse:'t-crash',narrow_loss:'t-loss'};
  var ORDER=['wire_win','comeback','seesaw_win','wire_loss','blew_lead','collapse','narrow_loss'];
  var active=null;   // selected type, or null = all
  function apply(){
    // counts + lead conversion within the date range (independent of the type filter)
    var counts={}, total=0, lm=0,lmw=0,le=0,lew=0, bm=0,bmw=0,be=0,bew=0;
    document.querySelectorAll('.trajcard').forEach(function(d){
      var ok=(window.GR?GR.inRange(d.getAttribute('data-date')):true);
      if(ok){ counts[d.getAttribute('data-type')]=(counts[d.getAttribute('data-type')]||0)+1; total++;
        var won=d.getAttribute('data-won')==='1';
        if(d.getAttribute('data-ledmid')==='1'){ lm++; if(won) lmw++; }
        if(d.getAttribute('data-ledend')==='1'){ le++; if(won) lew++; }
        if(d.getAttribute('data-behmid')==='1'){ bm++; if(won) bmw++; }
        if(d.getAttribute('data-behend')==='1'){ be++; if(won) bew++; }
      }
    });
    function pct(a,b){ return b? Math.round(a/b*100)+'%':'—'; }
    function cvcolor(a,b){ if(!b) return ''; var r=a/b;
      return r>=0.7?'cv-good':(r<0.5?'cv-bad':'cv-mid'); }
    function set(id,txt){ var el=document.getElementById(id); if(el) el.textContent=txt; }
    function stat(vid,nid,a,b,ntxt){ var el=document.getElementById(vid);
      if(el){ el.textContent=pct(a,b); el.className='cvv '+cvcolor(a,b); } set(nid,b?ntxt:'—'); }
    stat('cvMid','cvMidN',lmw,lm,'led into middlegame '+lm+' \u00b7 held '+lmw);
    stat('cvEnd','cvEndN',lew,le,'led into yose '+le+' \u00b7 held '+lew);
    stat('cbMid','cbMidN',bmw,bm,'behind into middlegame '+bm+' \u00b7 turned it around '+bmw);
    stat('cbEnd','cbEndN',bew,be,'behind into yose '+be+' \u00b7 turned it around '+bew);
    if(active && !counts[active]) active=null;   // type vanished from range
    var sum=document.getElementById('trajSummary');
    if(sum){
      var html="<span class='tjchip tjall"+(active===null?' on':'')+"' data-t='__all__'>"+
        "All <b>"+total+"</b></span>";
      html+=ORDER.filter(function(t){return counts[t];}).map(function(t){
        return "<span class='tjchip "+CLS[t]+(active===t?' on':'')+"' data-t='"+t+
          "'>"+LABEL[t]+" <b>"+counts[t]+"</b></span>"; }).join('');
      sum.innerHTML=html;
    }
    // visibility = in date range AND (no type filter or matching type)
    var shown=0;
    document.querySelectorAll('.trajcard').forEach(function(d){
      var okDate=(window.GR?GR.inRange(d.getAttribute('data-date')):true);
      var okType=(active===null || d.getAttribute('data-type')===active);
      var vis=okDate&&okType; d.style.display=vis?'':'none'; if(vis) shown++;
    });
    var c=document.getElementById('tjcount');
    if(c) c.textContent=(active?'Filtered: ':'Total: ')+shown+' game(s)'+(active?' ('+LABEL[active]+')':'');
  }
  var sum=document.getElementById('trajSummary');
  if(sum) sum.addEventListener('click',function(e){
    var chip=e.target.closest('.tjchip'); if(!chip) return;
    var t=chip.getAttribute('data-t');
    active=(t==='__all__'||t===active)?null:t;
    apply();
  });
  apply();
  document.addEventListener('grdate', apply);
})();
</script>
"""


SUMMARY_SECT_JS = r"""
<script>
(function(){
  function repRel(){ var m=location.pathname.match(/^\/r\/(.+)$/);
    return m?decodeURIComponent(m[1].replace(/\/$/,'')):null; }
  var REL=repRel();
  function setHist(h){
    var el=document.getElementById('rsHist');
    if(el) el.innerHTML=h||'';
  }
  function load(){
    if(!REL) return;
    fetch('/api/summary?report='+encodeURIComponent(REL)+'&t='+Date.now(),{cache:'no-store'})
    .then(function(r){return r.json();}).then(function(d){
      if(d && d.html){ document.getElementById('rsBody').innerHTML=d.html; }
      if(d) setHist(d.history);
    }).catch(function(){});
    var ex=document.getElementById('rsExp');
    if(ex) ex.href='/api/summary_export?report='+encodeURIComponent(REL);
  }
  window.rsGenerate=function(){
    if(!REL){ alert('Open this report inside the app (local server) to generate it.'); return; }
    var b=document.getElementById('rsBtn'), st=document.getElementById('rsStat');
    b.disabled=true; st.textContent='Generating... (DeepSeek analysis, about 20\u201360s -- please stay on this page)';
    fetch('/api/summary',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({report:REL})})
    .then(function(r){return r.json();}).then(function(d){
      b.disabled=false;
      if(d.error){ st.textContent='Failed: '+d.error; return; }
      document.getElementById('rsBody').innerHTML=d.html||'';
      // The version being replaced is archived, not lost \u2014 show it below.
      setHist(d.history);
      st.textContent='Updated \u2713 \u00b7 the previous one is kept below';
    }).catch(function(e){ b.disabled=false; st.textContent='Failed: '+e; });
  };
  load();
})();
</script>
"""
