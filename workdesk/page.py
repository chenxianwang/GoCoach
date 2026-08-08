"""The Working Desktop page: one card per app, status polled live."""

import html

CSS = """
*{box-sizing:border-box}
body{margin:0;min-height:100vh;color:#e9edf5;
  background:radial-gradient(1200px 600px at 20% -10%,#1e293b 0%,#0b1220 60%),#0b1220;
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,
  "PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:44px 22px 80px}
h1{font-size:27px;margin:0 0 4px;letter-spacing:-.3px}
.sub{color:#8b98ad;font-size:13.5px;margin:0 0 26px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}
.card{background:#131c2b;border:1px solid #243044;border-radius:14px;padding:18px 20px;
  display:flex;flex-direction:column;gap:10px}
.card.up{border-color:#2f6f4a;box-shadow:0 0 0 1px #2f6f4a33}
/* A one-shot action looks like a card but does not behave like one -- say so,
   so a green border here is not read as "this app is running". */
.card.act{background:#111a27}
.card.act .nm::after{content:'action';margin-left:8px;padding:2px 6px;
  font-size:10px;font-weight:600;letter-spacing:.7px;text-transform:uppercase;
  color:#8b98ad;background:#20293a;border-radius:5px;vertical-align:2px}
.top{display:flex;align-items:flex-start;gap:12px}
.emoji{font-size:26px;line-height:1.1}
.nm{font-weight:650;font-size:16px}
.note{color:#8b98ad;font-size:12.8px;margin-top:2px}
.dot{width:9px;height:9px;border-radius:50%;background:#4a5568;flex:none;margin-top:7px}
.dot.on{background:#37b24d;box-shadow:0 0 0 4px #37b24d22}
.state{font-size:12px;color:#8b98ad;min-height:16px}
.state.on{color:#51cf66}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:auto;padding-top:4px}
button,a.btn{font:inherit;font-size:13.5px;border:0;border-radius:9px;padding:8px 14px;
  cursor:pointer;text-decoration:none;display:inline-block}
.go{background:#2f6f4a;color:#fff}.go:hover{background:#38855a}
.st{background:#2b3547;color:#cbd5e1}.st:hover{background:#374357}
.open{background:#1c4f8f;color:#fff}.open:hover{background:#2361ad}
button[disabled]{opacity:.4;cursor:default}
.lg{background:none;color:#7c8aa0;padding:8px 6px;text-decoration:underline}
pre.log{display:none;white-space:pre-wrap;word-break:break-word;background:#080d16;
  border:1px solid #243044;border-radius:10px;color:#b9c6d6;margin:6px 0 0;padding:12px 14px;
  max-height:260px;overflow:auto;font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
pre.log.on{display:block}
.foot{color:#5d6b80;font-size:12px;margin-top:34px;text-align:center}
.foot code{color:#8b98ad}
.offline{display:none;background:#3a1d22;border:1px solid #7d2c38;color:#ffc9d1;
  border-radius:12px;padding:12px 16px;margin:0 0 20px;font-size:13.5px;line-height:1.5}
.offline.on{display:block}
.offline code{color:#fff;background:#00000038;padding:1px 5px;border-radius:4px}
body.offline-mode .card{opacity:.55}
"""

JS = """
<script>
var APPS = __APPS__;

// ids with a request in flight. Without this the 4s poll overwrites
// "Running…" with a stale result -- very visible for an action sitting on a
// password dialog, which can wait there a good while.
var BUSY = {};

function el(id){ return document.getElementById(id); }

// A tab often outlives the launcher that served it: close the Working Desktop
// window and every button here silently starts failing. Say so plainly instead
// of leaving stale green "Running" text and a cryptic fetch error on click.
function setOffline(on){
  var b=el('offline'); if(b) b.classList.toggle('on', on);
  document.body.classList.toggle('offline-mode', on);
  if(!on) return;
  APPS.forEach(function(id){
    var st=el('state-'+id);
    if(st){ st.classList.remove('on'); st.textContent='Launcher not running'; }
    var dot=el('dot-'+id); if(dot) dot.classList.remove('on');
    var card=el('card-'+id); if(card) card.classList.remove('up');
    var go=el('go-'+id); if(go) go.disabled=true;
    var stop=el('stop-'+id); if(stop) stop.disabled=true;
    var run=el('run-'+id); if(run) run.disabled=true;
  });
}

function refresh(){
  fetch('/api/status',{cache:'no-store'}).then(function(r){return r.json();})
  .then(function(d){
    setOffline(false);
    (d.apps||[]).forEach(function(s){
      var card=el('card-'+s.id); if(!card || BUSY[s.id]) return;
      var st=el('state-'+s.id);

      // An action has no "running" -- it either has been run or it has not.
      if(s.action){
        var good = !!(s.last && s.last.ok);
        card.classList.toggle('up', good);
        el('dot-'+s.id).classList.toggle('on', good);
        st.classList.toggle('on', good);
        st.textContent = s.last ? s.last.message : 'Ready';
        var run=el('run-'+s.id); if(run) run.disabled=false;
        return;
      }

      card.classList.toggle('up', s.running);
      el('dot-'+s.id).classList.toggle('on', s.running);
      st.classList.toggle('on', s.running);
      if(s.running){
        st.textContent = s.started_here ? 'Running (started here)'
                                        : 'Running (started elsewhere)';
      } else if (s.exit_code !== null && s.exit_code !== undefined) {
        st.textContent = 'Stopped \\u00b7 last exit code ' + s.exit_code;
      } else {
        st.textContent = 'Not running';
      }
      var go=el('go-'+s.id), stop=el('stop-'+s.id), open=el('open-'+s.id);
      if(go) go.disabled = s.running;
      // Anything running can be stopped -- the server finds it by port or
      // process name, so this survives reopening the launcher window.
      if(stop){
        stop.disabled = !s.running;
        stop.title = s.running && !s.started_here
          ? 'Started outside this window \\u2014 Stop will still find and stop it'
          : '';
      }
      if(open) open.style.display = s.running ? 'inline-block' : 'none';
    });
  }).catch(function(){ setOffline(true); });
}

function act(id, what){
  var st=el('state-'+id), run=el('run-'+id);
  var word = what==='launch' ? 'Launching' : (what==='stop' ? 'Stopping' : 'Running');
  BUSY[id]=1;
  st.textContent = word+'\\u2026';
  if(run) run.disabled=true;                 // a second click would run it twice
  function done(){ delete BUSY[id]; if(run) run.disabled=false; }
  fetch('/api/'+what,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({id:id})})
  .then(function(r){return r.json();})
  .then(function(d){
    done();
    if(!d.ok){ st.textContent = d.message || 'Failed'; showLog(id, true); }
    setTimeout(refresh, 700);
    setTimeout(refresh, 2500);
  })
  .catch(function(){ done(); setOffline(true); });
}

function showLog(id, force){
  var pre=el('log-'+id);
  if(!force && pre.classList.contains('on')){ pre.classList.remove('on'); return; }
  fetch('/api/log?id='+encodeURIComponent(id),{cache:'no-store'})
    .then(function(r){return r.json();})
    .then(function(d){
      pre.textContent = d.text || '(nothing logged yet)';
      pre.classList.add('on');
      pre.scrollTop = pre.scrollHeight;
    });
}

refresh();
setInterval(refresh, 4000);
</script>
"""


#: Named inline icons, for apps no emoji describes well. Unicode has no Go
#: symbol -- 🀄 is a mahjong tile and ♟ is chess -- so a board gets drawn.
#: Use with `"icon": "goban"` in apps.json; `emoji` still works for the rest.
ICONS = {
    "goban": (
        "<svg viewBox='0 0 32 32' width='27' height='27' aria-hidden='true'>"
        "<rect x='2' y='2' width='28' height='28' rx='4' fill='#dcb277'/>"
        "<g stroke='#7d5c30' stroke-width='1.3' stroke-linecap='round'>"
        "<path d='M9 8.5v15M16 8.5v15M23 8.5v15'/>"
        "<path d='M8.5 9h15M8.5 16h15M8.5 23h15'/></g>"
        "<circle cx='16' cy='16' r='3.3' fill='#15181d'/>"
        "<circle cx='23' cy='9' r='3.3' fill='#fbfcfd'/>"
        "<circle cx='9' cy='23' r='3.3' fill='#15181d'/>"
        "</svg>"),
}


def esc(x):
    return html.escape(str(x if x is not None else ""))


def icon_html(app):
    """An app's icon: a named inline SVG if it asks for one, else its emoji."""
    name = app.get("icon")
    if name:
        svg = ICONS.get(name)
        if svg:
            return svg
        # A typo in apps.json should be visible, not silently blank.
        return f"<span title='unknown icon {esc(name)}'>&#10067;</span>"
    return esc(app.get("emoji") or "•")


def _head(app, aid):
    """The dot / icon / name block every card shares."""
    return (f"<div class='top'><div class='dot' id='dot-{aid}'></div>"
            f"<div class='emoji'>{icon_html(app)}</div>"
            f"<div><div class='nm'>{esc(app.get('name') or app['id'])}</div>"
            f"<div class='note'>{esc(app.get('note') or '')}</div></div></div>")


def _card(app):
    aid = esc(app["id"])

    # An action gets one button and no Open/Stop: there is no lifetime here to
    # open into or stop. Its dot means "the last run worked", not "it is up".
    if (app.get("type") or "").lower() == "action":
        return (
            f"<div class='card act' id='card-{aid}'>"
            f"{_head(app, aid)}"
            f"<div class='state' id='state-{aid}'>Ready</div>"
            f"<div class='row'>"
            f"<button class='go' id='run-{aid}' onclick=\"act('{aid}','run')\">Run</button>"
            f"<button class='lg' onclick=\"showLog('{aid}')\">log</button>"
            f"</div><pre class='log' id='log-{aid}'></pre></div>")

    url = app.get("url")
    open_btn = (f"<a class='btn open' id='open-{aid}' href='{esc(url)}' "
                f"target='_blank' rel='noopener' style='display:none'>Open</a>"
                if url else "")
    return (
        f"<div class='card' id='card-{aid}'>"
        f"{_head(app, aid)}"
        f"<div class='state' id='state-{aid}'>Checking&hellip;</div>"
        f"<div class='row'>"
        f"<button class='go' id='go-{aid}' onclick=\"act('{aid}','launch')\">Launch</button>"
        f"{open_btn}"
        f"<button class='st' id='stop-{aid}' onclick=\"act('{aid}','stop')\">Stop</button>"
        f"<button class='lg' onclick=\"showLog('{aid}')\">log</button>"
        f"</div><pre class='log' id='log-{aid}'></pre></div>")


def build_html(apps, config_path):
    ids = "[" + ",".join(f'"{esc(a["id"])}"' for a in apps) + "]"
    cards = "".join(_card(a) for a in apps)
    body = (
        "<div class='wrap'>"
        "<h1>Working Desktop</h1>"
        "<p class='sub'>Launch your local apps without opening a terminal. "
        "Status is checked live, so anything you started elsewhere still shows "
        "up here.</p>"
        "<div class='offline' id='offline'>This page has lost its launcher &mdash; "
        "the Working Desktop window was closed, so nothing here can be started or "
        "stopped. Double-click <code>Working Desktop.command</code> again, then "
        "reload. Apps already running are unaffected.</div>"
        f"<div class='grid'>{cards}</div>"
        f"<p class='foot'>Add or edit apps in <code>{esc(config_path)}</code> "
        f"and reload this page.</p>"
        "</div>")
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Working Desktop</title>"
            f"<style>{CSS}</style></head><body>{body}"
            + JS.replace("__APPS__", ids) +
            "</body></html>")
