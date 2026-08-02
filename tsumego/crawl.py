"""Walk your Skill Test history and cache it locally.

The crawl is incremental and resumable: every run is written as its own JSON
file under data/runs/, and the per-question crowd move tree is cached under
data/diagrams/ keyed by qid. Re-running only fetches what is missing, so an
interrupted crawl costs nothing to resume and a weekly top-up is cheap.

Only the fields the dashboard needs are kept -- the record pages are ~140 KB of
HTML each, and storing that would be gigabytes for no benefit.
"""

import os
import json

from . import api
from .api import NotLoggedIn

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
RUNS = os.path.join(DATA, "runs")
DIAGRAMS = os.path.join(DATA, "diagrams")

# A run is a fixed-length set of questions; walking stops when a question comes
# back unanswered or missing. The cap is a guard against an unexpected format.
MAX_QUESTIONS = 30


def log_print(*a):
    """Default logger. Flushes, because a crawl is slow by design (the site
    allows ~1 request per 3.5s) and Python block-buffers stdout when it is
    redirected to a file -- without this, a long run looks frozen."""
    print(*a, flush=True)


def _ensure_dirs():
    for d in (DATA, RUNS, DIAGRAMS):
        os.makedirs(d, exist_ok=True)


def _run_path(guanid):
    return os.path.join(RUNS, f"{guanid}.json")


def _diagram_path(qid):
    return os.path.join(DIAGRAMS, f"{qid}.json")


def slim_question(q, n):
    """Keep only what the dashboard reads."""
    an = q.get("myan") or {}
    tr = q.get("taskresult") or {}
    return {
        "n": n,
        "qid": q.get("qid"),
        "publicid": q.get("publicid"),
        "levelname": q.get("levelname"),      # e.g. "3K" -- problem difficulty
        "level": q.get("level"),              # numeric difficulty
        "qtype": q.get("qtype"),
        "qtypename": q.get("qtypename"),      # Tesuji / Life & Death / Fight...
        "blackfirst": q.get("blackfirst"),
        "size": q.get("lu", 19),
        "vote": q.get("vote"),                # crowd difficulty vote
        "yes": q.get("yes_count"),            # global solved
        "no": q.get("no_count"),              # global failed
        "inerror": q.get("inerror"),          # in your error book
        # your attempt
        "result": an.get("result"),           # 1 = correct, 2 = wrong
        "costtime": an.get("costtime"),       # seconds spent
        "at": an.get("lasttime"),             # unix ts
        "answered": an.get("st"),
        "moves": [p.get("p", "") for p in (an.get("pts") or []) if p.get("p")],
        # the model answer(s)
        "ok_answers": q.get("ok_answers") or [],
        "fail_answers": q.get("fail_answers") or [],
        # success rate by player-rank bin (30 buckets, weakest first)
        "rank_ok": tr.get("ok_nums") or [],
        "rank_fail": tr.get("fail_nums") or [],
    }


def fetch_run(client, rec, refresh_diagrams=False, log=log_print):
    """Fetch one run's questions (and their crowd trees). Cached on disk.

    Returns None if the run came back with no questions. That is *not* cached:
    the session cookie expires (it is a normal Django session, not a permanent
    token), and an expired one makes every question page come back without
    `qqdata` -- indistinguishable here from an empty run. Caching those would
    bake permanent holes into the history, so an empty result is left uncached
    and reported upwards instead.
    """
    _ensure_dirs()
    guanid, number = rec["guanid"], rec["number"]
    path = _run_path(guanid)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    # The run index reports totaltime, and it is exactly the sum of the
    # questions' costtime. Using it as the stop condition means we never request
    # the non-existent question after the last one -- which mattered: that extra
    # request is the one most likely to be throttled, and losing it used to
    # discard the entire run we had just spent a minute fetching.
    budget = rec.get("totaltime") or 0
    spent = 0

    questions = []
    for n in range(1, MAX_QUESTIONS + 1):
        q = client.question(number, guanid, n)
        if not q:
            break
        an = q.get("myan") or {}
        # st != 2 means the question was never answered -> run ended earlier
        if an.get("st") != 2 or not an.get("pts"):
            break
        questions.append(slim_question(q, n))
        spent += an.get("costtime") or 0
        # One question is several seconds of enforced waiting, so say so as we
        # go -- otherwise a run looks frozen for well over a minute.
        log(f"    run {guanid} q{n}: "
            f"{'correct' if an.get('result') == 1 else 'wrong'} "
            f"({q.get('qtypename') or '?'}, {an.get('costtime')}s)")
        if budget and spent >= budget:
            break

    if not questions:
        return None

    out = {
        "guanid": guanid,
        "number": number,          # level index: 1 = 15级 ... 13 = 3级
        "oknum": rec.get("oknum"),
        "status": rec.get("status"),
        "t": rec.get("t"),
        "totaltime": rec.get("totaltime"),
        "questions": questions,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)

    log(f"  run {guanid}: {len(questions)} questions "
        f"({sum(1 for q in questions if q['result'] == 1)} correct)")
    return out


def fetch_diagram(client, qid, refresh=False):
    """Crowd move tree for one question. Cached by qid, which is why repeated
    questions across runs cost nothing extra."""
    _ensure_dirs()
    path = _diagram_path(qid)
    if os.path.exists(path) and not refresh:
        return
    dia = client.diagram(qid)
    if dia is not None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dia, f, ensure_ascii=False)


def crawl(client=None, limit=None, levels=None, since=None, log=log_print):
    """Fetch runs newest-first.

    limit  -- stop after this many runs (default: all)
    levels -- only these level indices, e.g. {13} for 3级
    since  -- only runs at/after this unix timestamp
    """
    _ensure_dirs()
    client = client or api.Client()

    log("Fetching level summary...")
    levels_data = client.levels()
    with open(os.path.join(DATA, "levels.json"), "w", encoding="utf-8") as f:
        json.dump(levels_data, f, ensure_ascii=False)

    log("Fetching run index...")
    recs = client.records()
    with open(os.path.join(DATA, "records.json"), "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False)
    log(f"  {len(recs)} runs on record")

    if levels:
        recs = [r for r in recs if r.get("number") in levels]
    if since:
        recs = [r for r in recs if (r.get("t") or 0) >= since]
    recs.sort(key=lambda r: r.get("t") or 0, reverse=True)
    if limit:
        recs = recs[:limit]

    todo = [r for r in recs if not os.path.exists(_run_path(r["guanid"]))]
    mins = len(todo) * 11 * client.delay / 60.0
    log(f"Fetching {len(todo)} new runs ({len(recs) - len(todo)} already cached)"
        + (f" -- roughly {mins:.0f} min at {client.delay:.1f}s/request"
           if todo else ""))

    empty_streak = 0
    for i, rec in enumerate(recs, 1):
        got = fetch_run(client, rec, log=log)
        if got is None:
            # Not cached, so it will be retried next time. A few in a row means
            # something systemic -- almost always an expired session cookie.
            empty_streak += 1
            if empty_streak >= 3:
                raise NotLoggedIn(
                    "Three runs in a row came back with no questions. The "
                    "session cookie has almost certainly expired -- copy a "
                    "fresh one into tsumego/config.json and run this again. "
                    "Nothing already cached was lost.")
        else:
            empty_streak = 0
        if i % 10 == 0:
            log(f"  ...{i}/{len(recs)}")

    fetch_missing_diagrams(client, log=log)
    log("Done.")
    return load_runs()


def missing_diagram_qids():
    """Question ids we have an attempt for but no crowd move tree yet."""
    have = {fn[:-5] for fn in os.listdir(DIAGRAMS)} if os.path.isdir(DIAGRAMS) else set()
    want = []
    for run in load_runs():
        for q in run.get("questions", []):
            qid = q.get("qid")
            if qid and str(qid) not in have and qid not in want:
                want.append(qid)
    return want


def fetch_missing_diagrams(client, limit=None, log=log_print):
    """Second pass: the crowd move trees.

    Kept separate from the run walk because `POST /tools/getdiagram/` is
    throttled far harder than the record pages -- ten question pages sail
    through and then the very first diagram POST starts returning 500. Running
    it as its own pass means a throttle storm here costs only the trees, never
    the runs, which are already safely on disk. Whatever is missed is simply
    picked up next time.
    """
    todo = missing_diagram_qids()
    if limit:
        todo = todo[:limit]
    if not todo:
        return 0
    log(f"Fetching {len(todo)} crowd move trees "
        f"(these are throttled harder than the record pages)")
    done = 0
    for qid in todo:
        try:
            fetch_diagram(client, qid)
            done += 1
        except api.RateLimited as e:
            log(f"  stopped after {done}/{len(todo)} trees: {e}")
            log("  The runs are safe; re-run the same command later to finish "
                "the trees. Until then those attempts show as unclassified.")
            break
    return done


def load_runs():
    """Every cached run, oldest first."""
    if not os.path.isdir(RUNS):
        return []
    runs = []
    for fn in os.listdir(RUNS):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(RUNS, fn), "r", encoding="utf-8") as f:
            runs.append(json.load(f))
    runs.sort(key=lambda r: r.get("t") or 0)
    return runs


def load_diagram(qid):
    path = _diagram_path(qid)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_levels():
    path = os.path.join(DATA, "levels.json")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
