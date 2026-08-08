# Skill Test diagnostics (101weiqi)

Turns your own 101weiqi **Skill Test** history into a dashboard that answers the
question the site itself does not: *how* are you getting problems wrong?

The site stores, for every question you have ever attempted, the moves you
played, how many seconds you spent, and a **crowd move tree** — every move real
players tried at that position, how many played it, and whether it is correct
(`o`), a known losing move (`f`), or off-book (`c`). Matching your move against
that tree splits your misses into three kinds that need completely different
training:

| Failure | What it means | What fixes it |
|---|---|---|
| **Trap** | You played a losing move that lots of other players also pick | A shared misconception — learn the shape once, a whole family of problems stops costing points |
| **Ran out of reading** | You started down the correct line and left it at move *k* | Read to the end, including the opponent's best resistance, before playing |
| **Off-book** | You played a move not in the answer tree that almost nobody plays | An idiosyncratic misread or a guess — usually moving before reading |

## Setup

Everything is Python 3 standard library — no `pip install`.

The crawler needs your logged-in session, because these are your private
records. **It never asks for your password.** You copy a session cookie out of a
browser where you are already signed in:

1. Sign in to <https://www.101weiqi.com> in your browser.
2. Open DevTools (`⌥⌘I`) → **Application** → **Cookies** → `https://www.101weiqi.com`.
3. Copy the values of `sessionid` and `csrftoken`.
4. Either put them in `tsumego/config.json`:

   ```bash
   cp tsumego/config.example.json tsumego/config.json
   # then edit config.json: "cookie": "sessionid=xxx; csrftoken=yyy"
   ```

   …or keep them off disk entirely:

   ```bash
   export WEIQI101_COOKIE='sessionid=xxx; csrftoken=yyy'
   ```

`config.json` is gitignored. The cookie is never logged, printed, or written
into the cache. It expires on its own; re-copy it when the crawler says the
session has lapsed.

## Use

```bash
python3 -m tsumego fetch --limit 10      # start small (~11 min -- see rate limits below)
python3 -m tsumego report --open
```

Then widen it once you are happy — in chunks, not all at once:

```bash
python3 -m tsumego fetch --limit 100      # ~2 hours; resumable, re-run to continue
python3 -m tsumego fetch --level 3级 --level 4级
python3 -m tsumego report --need 8 --total 10
```

`fetch` is **incremental and resumable** — each run is cached as its own JSON
file, and the crowd move tree is cached per question id, so repeated questions
cost nothing. Re-running only fetches what is new, which makes a weekly top-up
cheap. Interrupt it any time.

`--need` / `--total` control the pass-rate projection ("what accuracy buys
you"). Set them to match the level you are chasing.

## Working through the misses

Each of the four cards under **How you get them wrong** is clickable: it opens
the list of problems in that category, grouped by problem (meeting the same
trap five times is one lesson, not five rows) and showing what actually
happened — the move you played, the correct one, how many other players pick
yours, and how often everyone else solves it.

Press **Understood** on a problem you have properly learned and it drops out of
the list. The mark is stored in `data/hidden.json`, keyed by the site's question
id, so it survives a rebuild and applies the next time you meet that problem.
**Bring back** undoes it.

Hiding a problem does **not** change any count. The cards keep reporting what
actually happened — the diagnosis of your last 500 questions is history and
should not quietly rewrite itself — so a card reads e.g. `158` with a footer of
`152 problems to work through · 6 understood`.

The **To work through / Understood / All** switch beside the heading says which of
them the lists show. It starts on *To work through*, which is the drill list; flip
to *Understood* to revise what you have already ticked off, or *All* to see the
raw history. It only filters the lists — the counts stay put, for the same reason.

The buttons need the server, so they appear on the Skill Test page in the app.
A dashboard built with `python3 -m tsumego report` has nothing to POST to, so it
shows the same lists read-only rather than buttons that would silently fail — but
it does now honour `hidden.json`, which it previously ignored altogether.

## One problem in detail

```bash
python3 -m tsumego explain 453591     # the Q-number the site shows
```

The dashboard says *which* problems beat you. This says what happened inside
one of them — and it surfaces the fact the site's own review does not: **where
the problem is actually decided.**

A tsumego is not uniformly hard. Walk the correct line and ask, at each of your
turns, what share of the players who got that far found the right move. It is
usually 80–90% for move 1 and then falls off a cliff at exactly one turn:

```
ANSWER   B N18 W O18 B N17 W M17 B M19 W N19 B O19

WHERE IT IS DECIDED  (of the players still on the correct line)
  move 1:  N18   found by 84%   others: O18 7% off-book, M19 2% loses …
  move 2:  N17   found by 57%   others: M19 17% off-book, N19 15% loses …
  move 3:  M19   forced -- no other move exists
  -> the problem is move 2 (N17): 43% of the players who got this far go wrong here.

YOUR ATTEMPTS
  run 8139708 q3 (3级, 46s) -- ran out of time
      B N18  W O18  B N17  W M17
      2 correct move(s), then the clock ran out
```

The share at each turn is out of the players who **reached that turn**, not out
of everyone who attempted the problem — otherwise the numbers shrink down the
line and two turns stop being comparable, which is the only thing they are for.
A turn with a single legal continuation is reported as *forced* rather than as
"100% found it": those are different facts and only one of them is a compliment.

There is a `tsumego` [skill](../.claude/skills/tsumego/SKILL.md) that wraps this
into a step-by-step solving protocol — ask Claude to walk you through a problem
and it uses this command rather than trying to read stones off a screenshot.

## Rate limiting — read this before a big crawl

**The site allows roughly one request every 3 seconds.** When you go faster it
does not return 429 — it returns **HTTP 200 with a 35-byte body**:

```
please wait 3 seconds,and try again
```

That is invisible to the status code, so a naive client records empty results
instead of failing. Push harder still and the throttle escalates to **HTTP 500
for a while** — that is not a bug on their side, and it clears on its own after
a minute or two rather than after a few seconds.

Worse, the limit is **not a fixed rate**. Three seconds works from cold, but
under sustained traffic it tightens, and once it has escalated to 500 it stays
unhappy for a while.

So the client **self-tunes** rather than trusting any hard-coded number. It
starts at a 6s floor, and every time it is refused it widens its own spacing by
1.5× (up to 30s) and keeps the wider spacing for the rest of the session — it
never speeds back up, because probing is what triggers the throttle in the first
place. On a 500 it also waits 20s → 45s → 90s → 180s instead of retrying in
seconds. In practice a long crawl settles at whatever the site currently
tolerates:

```
Fetching 2 new runs -- roughly 1 min at 4.0s/request
    HTTP 500; waiting 20s (spacing now 6.0s)
    HTTP 500; waiting 45s (spacing now 9.0s)
```

**If the site has already been pushed hard, it stays unhappy for a while** —
tens of minutes, not seconds. When every request is coming back 500 no matter
how patient the client is, stop, leave it alone for half an hour, and start
again with a small `--limit`. Retrying through it only extends the penalty.

A run whose questions all came back empty is **never cached**, so a session
that expires (or a throttle storm) mid-crawl cannot bake permanent holes into
your history — those runs are simply refetched next time.

**If a crawl does die with `RateLimited`, nothing is lost.** Wait a few minutes
and run the same command again; it skips everything already cached and picks up
where it stopped.

What that means in practice, at ~10 questions per run plus one crowd-tree fetch
per question id you have not seen before:

| Scope | Roughly |
|---|---|
| `--limit 10` | ~11 min |
| `--limit 40` | ~45 min |
| `--limit 100` | ~2 hours |
| all 483 runs | **~9 hours** (do it over several days) |

So do it in chunks. `fetch` is resumable and skips everything already cached, so
running `--limit 100` five times over a few days costs the same as one long
crawl — and you can build the dashboard at any point from whatever you have.
Prefer `--level` if you only care about one level. This reads only your own
account's data.

## Layout

```
tsumego/
  api.py        session + endpoints + the qqdata/coordinate parsing
  crawl.py      resumable crawl into data/ (runs/, diagrams/)
  analyze.py    the failure taxonomy and every aggregate the dashboard shows
  explain.py    one problem in detail: the answer, the crux, what you played
  report.py     the HTML/SVG dashboard
  __main__.py   the CLI
  tests/        real captured payloads, one per failure kind
  data/         local cache (gitignored)
  dashboard.html  generated (gitignored)
```

## Data notes

- `GET /guan/my/` → `records`: one entry per run — `{guanid, number, oknum, t, totaltime}`,
  where `number` is the level index (1 = 15级 … 13 = 3级).
- `GET /guan/record/<number>/<guanid>/<n>/` → `qqdata`: one question, including
  `myan` (your moves, `costtime`, `result` — 1 correct, 2 wrong).
- `POST /tools/getdiagram/ {qid}` → the crowd move tree.
- Coordinates are two letters, column then row, both `a`–`s` from the top-left;
  `pt_to_gtp` converts them to the usual `N14` form.
- A run is **not** sudden-death: you answer a fixed set (~10) and need enough
  correct, so pass probability is a binomial tail — see
  `analyze.pass_probability`.

## Tests

```bash
python3 -m tsumego.tests.test_analyze
python3 -m tsumego.tests.test_explain
```

The fixtures are four real attempts from one run (3级, 2026-08-02), one per
failure kind, kept because they pin down the classifier against payloads the
site actually served. `test_explain` reuses them to pin down the "the problem
is decided at move N" arithmetic, which is the strongest claim either module
makes.
