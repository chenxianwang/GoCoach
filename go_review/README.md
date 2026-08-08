# Go Review — analyze your games with KataGo (via ikatago)

This tool reads your saved SGF games, asks your **ikatago** cloud KataGo to
evaluate every position, finds your biggest mistakes, and writes an HTML report
with per-game graphs and an overall "what to work on" summary.

It must run **on your Mac** (the same machine where Lizzie logs into ikatago),
because ikatago needs your account and a normal internet connection.

## Run it

Open Terminal and run:

```bash
cd "/Users/chenxianwang/Desktop/ClaudeCode-Go/go_review"
python3 run_review.py --selfcheck     # 1) instant sanity check, no cloud
python3 run_review.py                  # 2) the real analysis + report
```

Step 1 lists the games it picked and which color it thinks you played — no
engine is started, so it's instant and free. If the list looks right, run step 2.

When it finishes, open:

```
/Users/chenxianwang/Desktop/ClaudeCode-Go/go_review/output/review_report.html
```

## Settings (`config.json`)

| key | meaning |
|-----|---------|
| `ikatago_command` | the exact command Lizzie uses to start ikatago (path + your username/password). Already filled in from your Lizzie config. |
| `games_dirs` | folders to scan for `.sgf` files (searched recursively). |
| `user_names` | how you appear in the SGF — your yikeweiqi name, `cxw1990` on Fox. |
| `num_games` | how many of your most recent games to analyse (default 30). |
| `max_visits` | KataGo strength per move. Higher = more accurate but slower. 300 is a good review setting; raise to 800–1000 for deeper checks. |
| `max_time_per_move` | safety cap in seconds per position. |
| `max_moves_per_game` | set to e.g. `60` for a quick test run, `0` = whole game. |
| `mistake_threshold` / `blunder_threshold` | points-lost cutoffs for flagging a move. |
| `whisper_model` | path to a local [faster-whisper](https://github.com/SYSTRAN/faster-whisper) model, used to transcribe voice notes. Needs `pip install faster-whisper`. Leave blank to disable the record button. |
| `whisper_language` | force a language (`en`, `zh`, ...), or leave blank to auto-detect. Set to `en` by default. |
| `voice_audio_dir` | the **English Coach library** recordings are filed into. Defaults to `~/Desktop/English Coach/VideoAudioFiles`, deliberately outside the report folders so that project can consume them. Set to `""` to discard audio after transcription (the old behaviour). You do not have to edit this by hand — **📁 Save to…** in the voice panel writes it for you. |
| `deepseek_api_key` | DeepSeek API key for the **Review summary** page. Kept local (in gitignored `config.json`); leave blank to disable. |
| `deepseek_base_url` / `deepseek_model` | default `https://api.deepseek.com` / `deepseek-v4-flash`. Must be `deepseek-v4-pro` or `deepseek-v4-flash`. |

### Voice review & the review summary

At the top of the **Blunder Set** press **🎤 Start voice review** and just talk while
you scroll through your blunders — one continuous recording covers as many positions
as you like (a floating "Recording" pill stays on screen). Press **Stop & transcribe**
and the whole batch is transcribed on your Mac by the local whisper model (nothing
leaves the machine).

Each take is filed into the English Coach library using that project's own
`<stem>/<stem>.{webm,txt}` convention:

```
~/Desktop/English Coach/VideoAudioFiles/
  Recording 20260726-224624 yehu_3d_r2/
    Recording 20260726-224624 yehu_3d_r2.webm     <- the audio
    Recording 20260726-224624 yehu_3d_r2.txt      <- the plain transcript
```

The `Recording <date>-<time>` prefix keeps it sorting with your other takes, and
the report suffix records which Go project it came from. Because English Coach
derives its stem from the audio filename, running one of these through that app
writes `.result.json` / `.polished.txt` **into the same folder** instead of making
a duplicate.

The transcript is *also* appended to `<report>/review_voice.md` (that is what the
review summary reads), under a header naming the folder:
`[7/26/2026, 10:46:47 PM]  recording: Recording 20260726-224624 yehu_3d_r2`.

The audio is written *before* transcription runs, so even if whisper fails or the
model is missing, the take is never lost — the status line tells you which folder
it landed in. The text box below the button is editable and saves automatically.

**Choosing where takes go.** The button next to the timer shows the folder in
force — **📁 Save to: VideoAudioFiles** — and opens a browser for picking another
one, with a path box, **Create folder**, and **Save here**. Nothing changes until
you press Save here; browsing is just browsing.

It is a *server-side* picker rather than the native macOS dialog, and that is not
a shortcut: a web page cannot hand a **server** a folder you picked natively.
`showDirectoryPicker()` returns a handle only the browser can write through, and
`<input webkitdirectory>` returns file names, not a location — while Python is
what actually writes the `.webm`. So the listing comes from the app itself.

Folders that are *themselves* recordings are counted, not listed ("2 recordings
already in this folder"). Descending into a take and saving inside it would break
the flat `<stem>/<stem>.webm` pairing the English Coach library reads. Ordinary
sub-folders are navigable as usual.

Each report has its own **Review summary** section (in the report's own nav, next to
the blunder set), and there's also a **📓 Review summary · diagnostic profile** page in
the sidebar. Either one sends that transcript — plus the report's lead conversion and
comeback rate, blunder stats, and a
reference list of its worst moves — to DeepSeek, which **discovers your weakness
categories from the notes themselves** (not a fixed taxonomy) and returns one
**concise** holistic summary: overall verdict, a "weakness profile" naming each
emergent theme (root cause, a representative move or two, whether it's an ability
gap or a habit), the principles you keep repeating to yourself, and a prioritized
list of concrete drills — no long per-move table, no batch/comparison framing.
New recordings just add to the pool.

**Nothing is overwritten.** The latest diagnosis is cached to
`<report>/review_summary.md`, and *every* version is also kept as its own file in
`<report>/summaries/<date>_<time>.md`. The Review summary view shows the newest in
full with **Previous summaries** collapsed underneath, and **⇩ Export all versions**
downloads the whole history of that project as one Markdown file — handy for handing
to an AI at the end of a project and asking for a comprehensive summary.

### Changing the prompt

**⚙️ Review prompt setting** in the sidebar shows the system prompt behind that
diagnosis and lets you edit it — ask for shorter summaries, a different tone, more
attention to a phase you're working on. The same page previews the report data
that gets sent with it, for any report you pick, so you can see exactly what the
model is being asked about.

The shipped prompt stays in the code and your edit is an **override**, saved to
`prompts/review_summary_system.md` (gitignored — it is your preference, not
everyone's). So **Restore built-in default** is simply a delete: there is no
half-edited default to get stuck in, and improvements to the shipped prompt still
reach you as long as you have never saved one of your own. A **Customised** badge
appears when yours is in force. Clearing the box and pressing **Save prompt** will
not wipe it; only Restore does that.

## Quick test before the long run

Analysing 30 full games over the cloud takes a while. To prove the pipeline
end-to-end on one short game first, temporarily set in `config.json`:

```json
"num_games": 1,
"max_moves_per_game": 40
```

run `python3 run_review.py`, confirm the report opens, then restore the values.

## How "points lost" works

For each of your moves, KataGo's evaluation of its own best move is compared with
its evaluation of the move you actually played. The difference, in points of
score, is how much that move cost you. Averages are broken down by game phase
(fuseki / middlegame / yose) so you can see where your points leak.

## Files

Two entry points, and the two big pieces are packages rather than single files —
`report.py` and `web_app.py` grew past the point where one file was readable and
were split. `web_app.py` is still there as a 35-line launcher so the old command
keeps working.

- `run_review.py` — command-line entry point (`--selfcheck`, then the real run).
- `web_app.py` → `webapp/` — the local web app: `server.py` and `handler.py` (routes),
  `pages_misc.py` (the settings pages, including the review prompt), `voice.py`
  (recording, whisper, the save-to folder picker), `summary_engine.py` (DeepSeek),
  `jobs.py` / `config_jobs.py` (background runs), `assets.py` + `shell.py` (the
  sidebar and its CSS/JS), `static_export.py` (the offline `index.html`).
- `report/` — builds `review_report.html`: `core.py` (assembly), `charts.py` (hand-written
  SVG), `pages.py`, `board.py`, `trends.py`, `summary.py`, `assets.py` (the report's own
  CSS/JS, voice panel included).
- `analyze.py` — selects games, drives ikatago, writes per-game JSON.
- `gtp_engine.py` — launches ikatago and runs `kata-analyze`.
- `import_lizzie.py` — reads LizzieYZY's already-analysed SGF, no engine needed.
- `pipeline.py` — download → config → analyse → report, in order.
- `sgfparse.py` — SGF reader (main line only). `estimate_score.py` — final territory.
- `appconfig.py` — config loading with `${ENV}` and `~` expansion.
- `config.json` — your settings (gitignored). `prompts/` — the prompt texts, plus your
  saved override if you edit one.
- `output/` — JSON results + the HTML report (created on first run).

`CLAUDE.md` in this folder goes module by module, and lists the traps — chiefly that
`webapp/*.py` edits need a **server restart** while `report/*.py` edits need a
**report rebuild**, because reports are static files read from disk.

## Note on credentials

`config.json` contains your ikatago username and password in plain text, the same
way Lizzie's `config.txt` already stores them on this machine. Keep the folder
private; don't share `config.json`.
