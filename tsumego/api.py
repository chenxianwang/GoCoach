"""Thin client for the parts of 101weiqi.com that hold your own Skill Test data.

Everything here is read-only and scoped to the logged-in account's own records.
Auth is a browser session cookie supplied by the user (see README); it is read
from a gitignored config.json / env var and is never logged or written to the
cache.

Endpoints used (all discovered from the site's own pages):

    GET  /guan/                       -> `var guandata` : per-level aggregates
    GET  /guan/my/                    -> `var records`  : every test run
    GET  /guan/record/<lvl>/<run>/<n>/-> `var qqdata`   : one question + my answer
    POST /tools/getdiagram/ {qid}     -> crowd move tree with counts
"""

import os
import re
import json
import time
import gzip
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://www.101weiqi.com"
HERE = os.path.dirname(os.path.abspath(__file__))

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")


class NotLoggedIn(RuntimeError):
    """The cookie is missing or has expired."""


def load_config(path=None):
    """Config lives in tsumego/config.json (gitignored). The cookie may also be
    supplied via the WEIQI101_COOKIE env var so it never touches disk."""
    p = path or os.path.join(HERE, "config.json")
    cfg = {}
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    env = os.environ.get("WEIQI101_COOKIE")
    if env:
        cfg["cookie"] = env
    return cfg


def _csrf_from_cookie(cookie):
    m = re.search(r"csrftoken=([^;\s]+)", cookie or "")
    return m.group(1) if m else ""


class Client:
    """One logged-in session. `delay` seconds are slept between requests so a
    full crawl stays polite -- this is someone's small site, not an API."""

    def __init__(self, cookie=None, delay=0.7, timeout=30):
        cfg = load_config()
        self.cookie = (cookie or cfg.get("cookie") or "").strip()
        if not self.cookie:
            raise NotLoggedIn(
                "No session cookie. Put one in tsumego/config.json "
                "(see config.example.json) or set WEIQI101_COOKIE.")
        self.csrf = _csrf_from_cookie(self.cookie)
        self.delay = cfg.get("delay", delay)
        self.timeout = timeout
        self._last = 0.0

    # -- plumbing ----------------------------------------------------------
    def _throttle(self):
        wait = self.delay - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()

    def _open(self, req):
        self._throttle()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw.decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise NotLoggedIn(f"Server said {e.code} -- cookie expired?")
            raise

    def get(self, path):
        req = urllib.request.Request(
            BASE + path,
            headers={"Cookie": self.cookie, "User-Agent": UA,
                     "Accept-Language": "en,zh-CN;q=0.8"})
        return self._open(req)

    def post(self, path, data):
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(
            BASE + path, data=body,
            headers={"Cookie": self.cookie, "User-Agent": UA,
                     "Content-Type": "application/x-www-form-urlencoded",
                     "X-CSRFToken": self.csrf,
                     "X-Requested-With": "XMLHttpRequest",
                     "Referer": BASE + "/"})
        return self._open(req)

    # -- endpoints ---------------------------------------------------------
    def levels(self):
        """Per-level aggregates: your pass/fail counts and the global ones."""
        html = self.get("/guan/")
        data = extract_js_var(html, "guandata")
        if data is None:
            raise NotLoggedIn("Could not read guandata -- probably not logged in.")
        return data.get("guankas", [])

    def records(self):
        """Every Skill Test run you have taken, newest first.

        Each item: {guanid, number, oknum, status, t, totaltime} where `number`
        is the level index (1 = 15级 ... 13 = 3级) and `guanid` the run id."""
        html = self.get("/guan/my/")
        recs = extract_js_var(html, "records")
        if recs is None:
            raise NotLoggedIn("Could not read records -- probably not logged in.")
        return recs

    def question(self, number, guanid, n):
        """One question of one run, or None once the run has no nth question."""
        html = self.get(f"/guan/record/{number}/{guanid}/{n}/")
        return extract_js_var(html, "qqdata")

    def diagram(self, qid):
        """The crowd's move tree for a question: every move real players tried,
        with how many played it and whether it is right (`o`), a known wrong
        line (`f`), or off-book (`c`)."""
        txt = self.post("/tools/getdiagram/", {"qid": qid})
        try:
            return json.loads(txt).get("diagram")
        except ValueError:
            return None


# -- parsing -------------------------------------------------------------
def extract_js_var(html, name):
    """Pull `var <name> = {...};` out of a page.

    The payloads contain braces inside strings, so a brace counter that is
    string- and escape-aware is needed; a regex would truncate at the first
    `}` inside a nickname or comment.
    """
    m = re.search(r"var\s+%s\s*=\s*" % re.escape(name), html)
    if not m:
        return None
    s = html[m.end():].lstrip()
    if not s or s[0] not in "[{":
        return None
    open_ch = s[0]
    close_ch = "]" if open_ch == "[" else "}"
    depth = 0
    in_str = False
    esc = False
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[:i + 1])
                except ValueError:
                    return None
    return None


# -- coordinates ---------------------------------------------------------
GTP_COLS = "ABCDEFGHJKLMNOPQRST"   # no 'I', same convention as go_review


def pt_to_gtp(pt, size=19):
    """'mf' -> 'N14'. Two letters, column then row, both a..s from the top-left
    (the site's own encoding); display rows count up from the bottom."""
    if not pt or len(pt) < 2:
        return ""
    col = ord(pt[0]) - ord("a")
    row = ord(pt[1]) - ord("a")
    if not (0 <= col < size and 0 <= row < size):
        return ""
    return f"{GTP_COLS[col]}{size - row}"


def my_moves(qqdata):
    """The move sequence you actually played, as raw 'mf'-style points."""
    an = (qqdata or {}).get("myan") or {}
    return [p.get("p", "") for p in (an.get("pts") or []) if p.get("p")]
