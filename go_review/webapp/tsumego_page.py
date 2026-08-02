"""The 101weiqi Skill Test page.

The analysis itself lives in the sibling `tsumego` package at the repo root
(one level above go_review/, the same way pipeline.py reaches up to
`My games/fox_full_downloader.py`). This module only:

  * locates and imports that package,
  * renders its dashboard into the shell as its own page, and
  * exposes a bounded "refresh from 101weiqi" job.

The dashboard ships its own complete stylesheet, so it is served as a whole
document and shown in the shell's iframe -- no CSS bleed in either direction.
A toolbar is injected just after <body> to carry the cache status, the refresh
button, and (when opened outside the shell) a link back to the dashboard.
"""

import os
import sys
import datetime

from .paths import HERE

REPO_ROOT = os.path.dirname(HERE)
DEFAULT_REFRESH_LIMIT = 25   # a top-up, not a full re-crawl


def _import_tsumego():
    """Import the sibling package, or return None with a reason."""
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    try:
        from tsumego import analyze, crawl, report  # noqa: WPS433
        return {"analyze": analyze, "crawl": crawl, "report": report}, None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


# -- chrome injected into the dashboard document -------------------------
BAR_CSS = """
.tzbar{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:12px;
  flex-wrap:wrap;background:#101828;color:#fff;padding:9px 18px;font-size:13px}
.tzbar .t{font-weight:650}
.tzbar .s{color:#98a2b3}
.tzbar .sp{flex:1}
.tzbar a,.tzbar button{font:inherit;color:#fff;background:#344054;border:0;
  border-radius:7px;padding:6px 12px;cursor:pointer;text-decoration:none}
.tzbar button:hover,.tzbar a:hover{background:#475467}
.tzbar button[disabled]{opacity:.55;cursor:default}
.tzlog{display:none;white-space:pre-wrap;font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
  background:#0b1220;color:#cbd5e1;padding:12px 18px;max-height:240px;overflow:auto}
.tzlog.on{display:block}
"""

BAR_JS = """
<script>
(function(){
  var btn=document.getElementById('tzRefresh');
  if(!btn) return;
  var stat=document.getElementById('tzStat'), log=document.getElementById('tzLog');
  function poll(jid, since){
    fetch('/api/job/'+jid+'?since='+since,{cache:'no-store'})
      .then(function(r){return r.json();})
      .then(function(d){
        if(d.text){ log.classList.add('on'); log.textContent+=d.text; log.scrollTop=log.scrollHeight; }
        if(d.done){
          stat.textContent = d.ok ? 'Done -- reloading...' : 'Failed (see log)';
          btn.disabled=false;
          if(d.ok) setTimeout(function(){ location.reload(); }, 700);
          return;
        }
        setTimeout(function(){ poll(jid, d.n); }, 900);
      })
      .catch(function(e){ stat.textContent='Lost contact: '+e; btn.disabled=false; });
  }
  btn.onclick=function(){
    btn.disabled=true; stat.textContent='Fetching...';
    log.textContent=''; log.classList.add('on');
    fetch('/api/tsumego_refresh',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({})})
      .then(function(r){return r.json().then(function(d){return {ok:r.ok,d:d};});})
      .then(function(res){
        if(!res.ok||!res.d.job){ stat.textContent=res.d.error||'Could not start.';
          btn.disabled=false; return; }
        poll(res.d.job, 0);
      })
      .catch(function(e){ stat.textContent='Could not start: '+e; btn.disabled=false; });
  };
})();
</script>
"""


def _bar_html(status, embed, can_refresh=True):
    back = ("" if embed else
            "<a href='/'>&larr; Back to dashboard</a>")
    refresh = ("<button id='tzRefresh' title='Fetch the most recent runs you have "
               "not cached yet'>&#10227; Refresh from 101weiqi</button>"
               if can_refresh else "")
    return (f"<div class='tzbar'><span class='t'>101weiqi Skill Test</span>"
            f"<span class='s'>{status}</span><span class='sp'></span>"
            f"{refresh}<span class='s' id='tzStat'></span>{back}</div>"
            f"<pre class='tzlog' id='tzLog'></pre>")


def _inject(doc, bar):
    """Put the toolbar just inside <body>, its CSS just before </style>, and the
    toolbar's script just before </body>."""
    if "</style>" in doc:
        doc = doc.replace("</style>", BAR_CSS + "</style>", 1)
    if "<body>" in doc:
        doc = doc.replace("<body>", "<body>" + bar, 1)
    else:
        doc = bar + doc
    if "</body>" in doc:
        doc = doc.replace("</body>", BAR_JS + "</body>", 1)
    else:
        doc += BAR_JS
    return doc


def _shell(inner, embed, title="101weiqi Skill Test"):
    """A minimal standalone document for the empty / error states, styled to
    match the dashboard rather than the go_review shell."""
    back = ("" if embed else
            "<p style='margin-top:22px'><a href='/' style='color:#1c7ed6'>"
            "&larr; Back to dashboard</a></p>")
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{title}</title><style>"
        "body{margin:0;background:#f6f7f9;color:#1a202c;font:15px/1.6 -apple-system,"
        "BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}"
        ".w{max-width:760px;margin:0 auto;padding:44px 22px}"
        "h1{font-size:23px;margin:0 0 8px}"
        ".card{background:#fff;border:1px solid #e4e7ec;border-radius:10px;padding:20px 22px;margin-top:16px}"
        "code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px}"
        "pre{background:#0b1220;color:#cbd5e1;padding:14px 16px;border-radius:8px;overflow:auto}"
        "p{margin:10px 0}.sub{color:#667085;font-size:13.5px}"
        + BAR_CSS +
        f"</style></head><body><div class='w'>{inner}{back}</div>{BAR_JS}</body></html>")


def _setup_help(reason=None, embed=False, can_refresh=False):
    why = (f"<p class='sub'>Import failed: <code>{reason}</code></p>"
           if reason else "")
    bar = _bar_html("not set up yet", embed, can_refresh=can_refresh)
    return _shell(
        bar +
        "<h1>101weiqi Skill Test</h1>"
        "<p class='sub'>Turns your own Skill Test history into a diagnosis of "
        "<i>how</i> you get problems wrong -- traps you share with the crowd, "
        "lines where your reading ran out, and off-book guesses.</p>"
        "<div class='card'><h2 style='font-size:17px;margin:0 0 6px'>Nothing cached yet</h2>"
        + why +
        "<p>The crawler needs a session cookie from a browser where you are "
        "already signed in to 101weiqi. It never asks for your password, and the "
        "cookie is gitignored and never logged.</p>"
        "<p>1. Copy <code>sessionid</code> and <code>csrftoken</code> from DevTools "
        "&rarr; Application &rarr; Cookies &rarr; <code>101weiqi.com</code>.</p>"
        "<p>2. Then, from the repo root:</p>"
        "<pre>cp tsumego/config.example.json tsumego/config.json\n"
        "# edit config.json: \"cookie\": \"sessionid=xxx; csrftoken=yyy\"\n\n"
        "python3 -m tsumego fetch --limit 40</pre>"
        "<p class='sub'>Full details in <code>tsumego/README.md</code>. Once a "
        "cookie is configured, the <b>Refresh from 101weiqi</b> button above can "
        "top the cache up without leaving this page.</p></div>", embed)


def _status_line(agg, runs):
    last = max((r.get("t") or 0) for r in runs) if runs else 0
    when = (datetime.datetime.fromtimestamp(last).strftime("%Y-%m-%d")
            if last else "unknown")
    return (f"{agg['n']:,} questions &middot; {agg['n_runs']:,} runs "
            f"&middot; newest {when}")


def tsumego_page(embed=False, need=8, total=10):
    """The Skill Test dashboard, or a setup/empty state explaining what to do."""
    mods, err = _import_tsumego()
    if not mods:
        return _setup_help(reason=err, embed=embed, can_refresh=False)

    crawl, analyze, report = mods["crawl"], mods["analyze"], mods["report"]
    can_refresh = _cookie_configured()

    try:
        runs = crawl.load_runs()
    except Exception as e:  # noqa: BLE001
        return _setup_help(reason=f"could not read the cache: {e}",
                           embed=embed, can_refresh=can_refresh)
    if not runs:
        return _setup_help(embed=embed, can_refresh=can_refresh)

    agg = analyze.analyse(runs, crawl.load_diagram)
    doc = report.build_html(agg, need=need, total=total)
    return _inject(doc, _bar_html(_status_line(agg, runs), embed,
                                  can_refresh=can_refresh))


def _cookie_configured():
    mods, _ = _import_tsumego()
    if not mods:
        return False
    try:
        from tsumego.api import load_config
        return bool((load_config().get("cookie") or "").strip())
    except Exception:  # noqa: BLE001
        return False


def do_tsumego_refresh(job, body):
    """Top up the local cache with the most recent runs. Bounded on purpose:
    the shell's job slot is shared with KataGo analysis, and a full history is
    thousands of requests against a small site."""
    mods, err = _import_tsumego()
    if not mods:
        raise RuntimeError(f"The tsumego package could not be imported ({err}).")
    from tsumego.api import Client, NotLoggedIn

    limit = int((body or {}).get("limit") or DEFAULT_REFRESH_LIMIT)
    print(f"Refreshing the {limit} most recent Skill Test runs...")
    try:
        client = Client()
    except NotLoggedIn as e:
        raise RuntimeError(
            f"{e}\nSee tsumego/README.md -- copy a session cookie into "
            f"tsumego/config.json, then try again.")
    mods["crawl"].crawl(client, limit=limit, log=print)
    print("Cache updated.")
