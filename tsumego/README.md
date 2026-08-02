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
python3 -m tsumego fetch --limit 40      # start small: 40 most recent runs
python3 -m tsumego report --open
```

Then widen it once you are happy:

```bash
python3 -m tsumego fetch                 # everything (see "Be polite" below)
python3 -m tsumego fetch --level 3级 --level 4级
python3 -m tsumego report --need 8 --total 10
```

`fetch` is **incremental and resumable** — each run is cached as its own JSON
file, and the crowd move tree is cached per question id, so repeated questions
cost nothing. Re-running only fetches what is new, which makes a weekly top-up
cheap. Interrupt it any time.

`--need` / `--total` control the pass-rate projection ("what accuracy buys
you"). Set them to match the level you are chasing.

## Be polite

A full history is a few thousand page loads against a small site. The client
sleeps `delay` seconds between requests (0.7s default) and caches aggressively
so you only ever pay once. Please leave the throttle on, and prefer `--limit` /
`--level` over re-crawling everything. This reads only your own account's data.

## Layout

```
tsumego/
  api.py        session + endpoints + the qqdata/coordinate parsing
  crawl.py      resumable crawl into data/ (runs/, diagrams/)
  analyze.py    the failure taxonomy and every aggregate the dashboard shows
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
```

The fixtures are four real attempts from one run (3级, 2026-08-02), one per
failure kind, kept because they pin down the classifier against payloads the
site actually served.
