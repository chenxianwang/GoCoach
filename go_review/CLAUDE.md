# Mirror of Go - KataGo Game Review — Project Notes (handoff)

Personal Go (围棋) game-review web app. It turns Fox (野狐) / LizzieYZY SGF games
into KataGo-powered review reports, viewed in a local browser app. Pure Python
**stdlib only** (`http.server`), no web framework. This file is the handoff for a
new session — read it first.

> The user prefers **English replies**. Keep responses concise.
> **The whole UI is English.** It was translated from Chinese in July 2026; do not
> reintroduce Chinese strings. Go terminology follows standard English Go usage:
> **Fuseki / Middlegame / Yose**, **blunder**, **Lead conversion** (was 守成率),
> **Comeback rate** (was 逆转率), **Blunder Set** (was 失误集), points (was 目).

## How to run / restart

- Start the app (opens a browser to the sidebar shell):
  `cd /Users/chenxianwang/Desktop/ClaudeCode-Go/go_review && python3 web_app.py`
- **`report.py` and `web_app.py` are now packages** (`report/`, `webapp/`), split by
  concern in 2026-08 — each used to be a single 3-4k line file. `web_app.py` itself
  is now just a thin launcher (`sys.path` bootstrap + `from webapp.server import
  main`); all routes/pages/jobs live under `webapp/*.py`. Every name that used to be
  `report.X` or reachable from `web_app.py` is unchanged from the outside — only the
  internal file layout moved. See "Layout & key files" below for the new module map.
- **The server is long-running. It does NOT hot-reload.**
  - Edited any `webapp/*.py` (routes/pages/APIs/form defaults) → **restart the server**.
  - Edited any `report/*.py` (report HTML/JS/CSS) → **rebuild the affected report(s)**;
    served reports are static `review_report.html` files read from disk.
    `_reload_app_modules` (in `webapp/config_jobs.py`, used by the Analyse/Import
    flow) reloads every `report.*` submodule in dependency order, then the `report`
    package itself, before rebuilding — reloading just `sys.modules["report"]` would
    only re-run `report/__init__.py` and miss edits inside the submodules.
  - Changed `config.json` → no restart needed (`_safe_cfg()` re-reads it each call).
- Rebuild a report from the shell:
  ```
  cd /Users/chenxianwang/Desktop/ClaudeCode-Go/go_review
  python3 -c "import report, import_lizzie, pipeline; \
    gd=pipeline.load_config()['games_dirs']; \
    import_lizzie.rebuild_report('yehu_4d', gd)"
  ```
  Or just use the app's **Analyse / import** flow (it rebuilds).

## Standing constraints (important)

- **Reply in English only.** All user-facing strings, logs and comments are English.
  The only intentional CJK left in the source are two lookup patterns: the
  `黑/白 … 胜` result strings in `analyze.user_won` and the `野狐` alternative in
  `report.source_label_from_path`'s regex (both match text produced by the Fox
  server, not text shown to the user). Opponent nicknames in the game data are
  Chinese and stay that way.
- `config.json` holds **plaintext secrets** (ikatago cloud username/password, the
  DeepSeek API key). It is gitignored. **Never commit or print those secrets.**
- **Do NOT run KataGo locally** — analysis goes through the **ikatago cloud** only.
- Keep the folder private. Don't expose internal sandbox paths to the user; use the
  real Mac paths (`/Users/chenxianwang/Desktop/ClaudeCode-Go/...`).

## Layout & key files

- `web_app.py` — thin entry point only: puts `go_review/` on `sys.path`, then
  `from webapp.server import main`. All real server code lives in `webapp/`
  (imported as plain sibling modules — `pipeline`, `report`, `import_lizzie`,
  `go_terms` — since `go_review/` is already on `sys.path` by the time any
  `webapp/*.py` runs):
  - `webapp/paths.py` — `HERE` (resolved as `dirname(dirname(this file))` since
    `webapp/` sits one level below `go_review/`; every other module gets `HERE`
    from here, not by recomputing `__file__`).
  - `webapp/htmlutil.py` — `_esc`, kept dependency-free at the bottom of the
    import graph (both `shell` and `static_export` need it, and `static_export`
    sits below `shell` — see `config_jobs`/`shell` note below).
  - `webapp/jobs.py` — `Job`, `JobManager`, the `JOBS` singleton.
  - `webapp/listing.py` — `list_reports`, `list_games_dirs`, `report_dir_from_rel`,
    `report_summary` (+ its `_SUMMARY_CACHE`).
  - `webapp/assets.py` — the CSS/JS string constants (`PAGE_CSS`, `SHELL_CSS`,
    `SHELL_JS`, `ANALYSIS_MODULE`, `TERMS_CSS`, `TERMS_JS`, `SUMMARY_CSS`,
    `SUMMARY_JS`, `COMPARE_CSS`, `STATIC_CSS`).
  - `webapp/shell.py` — sidebar shell (`dashboard_page`), `analyze_page`,
    `_analysis_module_html`, `_page`.
  - `webapp/compare.py` — `compare_page`, `_report_metrics`.
  - `webapp/pages_misc.py` — `summary_page`, `terms_page` (`/terms`).
  - `webapp/static_export.py` — `write_static_index` / `build_static_index` (the
    offline `index.html` viewer).
  - `webapp/report_serve.py` — `render_report` (`/r/<rel>`).
  - `webapp/config_jobs.py` — `_safe_cfg`, `_reload_app_modules`, `do_analyze`,
    `do_import`, `set_default_config`. **`_reload_app_modules` reloads every
    `report.*` submodule (in dependency order) before the `report` package
    itself** — see the hot-reload note above; this is the one place that
    matters if the reload logic ever needs to change again.
  - `webapp/board_api.py` — `render_board_svg` (`/api/board`, lazy full-board SVG).
  - `webapp/voice.py` — voice recording, local Whisper (`transcribe_audio`,
    `_get_whisper`), the English Coach filing convention.
  - `webapp/state.py` — per-report `notes.json` / `review_voice.md` /
    `practice_hidden.json` load/save.
  - `webapp/summary_engine.py` — DeepSeek call (`_call_deepseek`,
    `_summary_system`, `_summary_input`, `build_review_summary`), the summary
    archive (`archive_summary`, `list_summaries`, `summary_history_html`,
    `export_summaries_md`), markdown→HTML (`_md_to_html`).
  - `webapp/backup.py` — `backup_manifest`, `build_backup_zip`, `delete_report`.
  - `webapp/handler.py` — the `Handler` class: every GET/POST route, delegating
    to the modules above.
  - `webapp/server.py` — `QuietServer`, `main` (CLI args, `--rebuild-reports`,
    `--export-static`).
- `go_terms.py` — **data only, no imports**: `CATEGORIES` + `TERMS`, a list of
  `(category, english, chinese, pinyin, say, meaning)` tuples (191 terms in 11
  categories), plus `count()` and `by_category()`. `meaning` may contain `<b>`/`<i>`;
  `terms_page` strips tags before building the search haystack, so searching "b"
  does not match every bolded entry. To add a term, append a tuple — the page
  picks it up on next load (and `_reload_app_modules` reloads `go_terms` too).
- `report/` — report HTML generator (was a single `report.py`, split by concern;
  `report/__init__.py` re-exports everything so `import report; report.build_html(...)`
  etc. are unchanged). `report/core.py`'s `build_html(games, agg, recs,
  report_dir=None)` assembles the inner-nav pages: **Overview** (`report/pages.py`'s
  `_home_page` + `report/trends.py`'s `trends_section` + move hist),
  **Trajectory** (`report/trajectory.py`'s `trajectory_section`), **Blunders**
  (`report/practice.py`'s `practice_section`), **Review summary**
  (`report/summary.py`'s `summary_section`), **Game by game**
  (`report/pages.py`'s `_games_page`). `report/board.py` has the go-board
  reconstruction, SVG diagrams and blunder-shape similarity. `report/legacy.py`
  holds `coach_review` and `_blunders_page`/`_recs_page` — still re-exported but
  **not wired into `build_html`** — dead code paths, kept for reference. The big
  `CSS`, `PRACTICE_JS`, `VOICE_JS`, `VOICE_PANEL`, `FLOAT_REC`, `PRACTICE_CLEAR_JS`,
  `SUMMARY_SECT_JS` string constants live in `report/assets.py`.
- `import_lizzie.py` — `rebuild_report(out_dir, games_dirs=None)` → `report.build_html`.
  SGF import, filename dedup, `_norm_winrate`, main-line-only node scan.
- `sgfparse.py` — `main_line_text()` / `parse_sgf()` (main line only).
- `analyze.py`, `pipeline.py` — the ikatago analysis pipeline + config loading.
- `appconfig.py`, `config.json` (secrets, gitignored), `config.example.json`.
- `prompts/go_review_diagnostics_skill.md`, `prompts/worked_example.md` — the
  originally-uploaded skill. **No longer used for the summary** (it moved to a
  data-driven prompt), kept for reference.
- `tests/test_parsing.py`, `demo/`, `README.md`, `LICENSE`, `.gitignore`.

## Reports & per-report data

Each report is a subfolder under `go_review/` (e.g. `yehu_4d/`, `yehu_3d/`,
`yehu_3d_r2/`) containing per-game `*.json` + `review_report.html`. Per-report state:

- `notes.json` — legacy structured per-position notes (the per-position note UI was
  removed; file is still read as *supplementary* input to the summary).
- `practice_hidden.json` — blunder keys (`filename#move`) the user deleted, either
  one at a time or via **Delete all blunder positions**. Delete-all writes the keys
  that exist *at that moment* (`web_app.set_all_hidden`), so a game analysed later
  has keys nobody deleted and its blunders appear normally. This replaced a sticky
  `practice_cleared` marker that suppressed the section forever, including for new
  games — do not reintroduce a blanket flag. Restore-all empties the file.
- `review_voice.md` — batch voice-review transcript (the current note source).
  Each block is headed `[<local time>]  recording: <stem>`, naming the English
  Coach folder the take was filed into.
- `review_summary.md` — the **latest** DeepSeek diagnosis (kept for compatibility;
  everything that reads "the summary" reads this).
- `summaries/<YYYY-MM-DD_HHMMSS>.md` — **every** generated version, one file each.
  Regenerating no longer destroys the previous diagnosis. `_adopt_legacy_summary`
  folds a pre-archive `review_summary.md` in on first read, dated by its mtime, so
  older reports keep their history. `list_summaries` (newest first),
  `summary_history_html` (collapsible `<details>`, newest excluded because it is
  already rendered in full), `export_summaries_md` (all versions, oldest first).
- `practice_cleared` — **retired** marker from the old blanket-clear design.
  `practice_section` still honours it so an un-migrated folder renders sensibly, and
  `set_all_hidden` deletes it on the next delete-all/restore. All three current
  reports have been migrated already.

Game-glob sites exclude `index.json`, `notes.json`, `practice_hidden.json`; the other
state files are `.md` / markerless so `*.json` globs skip them (keep it that way).

## Backup (`/api/backup`, sidebar "Back up project")

`backup_manifest()` / `build_backup_zip()` produce an in-memory zip that is
**restorable on another Mac**. Rooted at the *repo* folder, not `go_review`, because
the launcher (`一目弈镜.command`) and `My games/fox_full_downloader.py` (imported by
`pipeline._load_downloader`) live one level up — a `go_review`-only zip could not be
launched. Includes: all source, docs, `config.example.json`, the launcher, the
downloader module, and per report the `*.sgf.json` analysis **plus** `review_voice.md`,
`review_summary.md`, `summaries/*.md`, `practice_hidden.json`, `notes.json`.
**Excluded on purpose:** `config.json` and repo-root `config.txt` (both hold the
ikatago password in plaintext — the zip must stay safe for cloud storage),
`review_report.html` / `index.html` (regenerated), the 114 MB of downloaded SGFs, and
the engine binaries. ~19 MB raw → ~3.4 MB zip.

Restore is: unzip → `python3 go_review/web_app.py --rebuild-reports` → launch. That
flag rebuilds every report from the JSON and rewrites `index.html`, needing no engine,
network or `config.json` (`appconfig` falls back to `config.example.json`). Verified by
extracting to an empty folder and running it: all three reports came back with their
diagrams, transcripts and summary history. `extractall` does **not** restore the
launcher's `+x` bit (Finder's unzip does) — `BACKUP_README.txt` at the zip root covers
that plus which config keys to refill.

## Domain conventions (don't silently change)

- **Blunder** = `points_lost ≥ 6` **OR** `winrate_lost ≥ 15%` (union).
  `PTS_BLUNDER=6`, `WR_BLUNDER=0.15`.
- Win-rate curve is **black perspective 0..1** (`timeline[].black_winrate`), flipped to
  the user's perspective. Per-move `winrate_lost` is a fraction (0..1) in game JSON but a
  **percentage number** in `notes.json`.
- **守成率** (lead-hold): `LEAD_TH=0.90`, checked entering middlegame (1/3) and endgame
  (2/3). **逆转率** (comeback): `BEHIND_TH=0.10`.
- Move counts use the **SGF main line only** (fixed a variation-inflation bug).
- `_norm_winrate` handles integer per-ten-thousand candidate win-rates (÷10000).

## Feature map

- **Blunder Set** (`practice_section`): every blunder as a card with a local-shape
  board image + lazy full-board zoom (`/api/board`); filters Phase / Type / Points
  lost / Win-rate drop / Status; mark-mastered (localStorage, key
  `go_review_mastered`); delete → `practice_hidden.json`. Header has the **batch
  voice-record panel** (🎤 Start voice review → MediaRecorder → POST
  `/api/transcribe` → appended to `review_voice.md`; floating "Recording" pill).
  **Delete all blunder positions** (on the count line under the filters) and
  **Restore N deleted** call `/api/practice_clear`, which rewrites
  `practice_hidden.json` and rebuilds. When nothing is left to show,
  `practice_section` must NOT return `""` — `build_html` drops empty modules, which
  would take the whole Blunders page and its voice panel with it; it returns the
  heading, the voice panel and a Restore button instead.
- **Review summary** (in-report section *and* sidebar page, same engine): DeepSeek turns the
  report's `review_voice.md` (+ any `notes.json`, + 守成率/逆转率/blunder stats + a
  worst-moves table) into a **data-driven, concise** diagnosis. Categories **emerge from
  the notes** (the model names them itself — no fixed taxonomy). **No batch / cumulative /
  cross-batch / comparison framing** (removed per user). Cached to `review_summary.md`.
- **Go terms** (`terms_page`, `/terms`, sidebar): Chinese→English Go glossary,
  one card per category, columns English (with a pronunciation respelling for the
  Japanese loanwords) / Chinese (with pinyin) / meaning. Live search over English +
  Chinese + pinyin + definition — **pinyin is why you can search 手筋 as `shoujin`
  with no IME** — plus category filter chips. All filtering is client-side, Esc
  clears the box. Server-only (not in the offline `index.html`).
- **Compare reports** (`compare_page`): numeric metrics only (points lost per move,
  blunder rate, lead conversion, comeback rate, distributions). The AI cross-report
  diagnostic comparison was **removed** per user.
- **Trajectory** (`trajectory_section`): win-rate shape classes (Led throughout /
  Comeback win / Lead thrown away / Endgame collapse …) + lead conversion and
  comeback rate.
- Overview label shows **`project <folder name>`** (the project/report folder name),
  set in `build_html` when `report_dir` is known (via `agg["source_label"]`).

## Config (`config.json`, gitignored)

- `ikatago_command` (cloud creds), `games_dirs`, `user_names`, `default_fox_uid`,
  `default_games_subdir`, `default_import_target`, `lizzie_jar`, `output_dir`,
  `num_games`, `max_visits`, `max_time_per_move`, `mistake_threshold`,
  `blunder_threshold`, …
- `whisper_model` = `~/Desktop/models/faster-whisper-medium`, `whisper_language`
  is now **`en`** (was blank/auto) — voice reviews are expected in English. Needs
  `faster-whisper` installed on the Mac.
- `voice_audio_dir` = `~/Desktop/English Coach/VideoAudioFiles` — the **English
  Coach library**. Recordings are filed using *that project's* convention, which is
  `<stem>/<stem>.{webm,txt}`: one folder per take, every file inside named after the
  folder. Our stem is `Recording <YYYYMMDD-HHMMSS> <report>` (`_audio_stem`), which
  keeps the user's `Recording <date>-<time>` prefix. **This matters:**
  `english_coach_gui.py` derives its stem from the audio *filename* and calls
  `rec_dir_for(stem)`, so a matching name means that app enriches the same folder
  (`.result.json`, `.polished.txt`, `.json`) instead of creating a duplicate. Never
  write those files, or `history.json`, ourselves — they belong to English Coach.
  `""` restores the old discard-after-transcription behaviour.
- `save_voice_audio` runs **before** transcription and never raises: on failure it
  logs and `transcribe_audio` falls back to a temp file, so a take is never lost to
  a bad path or a missing model. `save_voice_text` then writes `<stem>.txt` (bare
  prose, no header — matching the library). `transcribe_audio` returns a **3-tuple**
  `(text, error, stem)` and `/api/transcribe` takes `?report=<rel>` to name the folder.
- `deepseek_api_key`, `deepseek_base_url` = `https://api.deepseek.com`, `deepseek_model`.
  **Model must be `deepseek-v4-pro` or `deepseek-v4-flash`** — `deepseek-chat` is rejected
  by this account (400). `flash` = faster/cheaper, `pro` = deeper.
- **Analyze form defaults** (in `webapp/assets.py`'s `ANALYSIS_MODULE`, not config):
  "Recent games to download" = **1**, "Games to analyse" = **1**, visits = 300.

## Current state (as of this handoff)

- Reports present: `yehu_3d_r2` (new, full), `yehu_4d`, `yehu_3d`.
- `yehu_4d` and `yehu_3d` have their **blunder set cleared** (`practice_cleared` present) — the user
  finished reviewing them; restore via the ↻ button if needed.
- All reports rebuilt after the English translation; `index.html` regenerated.
- **Stale Chinese data:** `yehu_3d_r2/review_summary.md` and
  `yehu_4d/review_summary.md` are cached DeepSeek output from *before* the prompt
  was switched to English, so they still render in Chinese on the Review summary
  page. Press **Generate / refresh review summary** to replace them. The
  `review_voice.md` transcripts are the user's own Chinese spoken notes — input
  data, leave them alone (the English prompt reads Chinese fine).

## Common gotchas

- **Escaping inside the JS blobs.** `PRACTICE_CLEAR_JS`, `VOICE_JS` etc. are Python
  **raw** strings, so `\\'` reaches the browser as a literal backslash plus a quote
  and kills the whole `<script>` with a SyntaxError — the symptom is a button that
  silently does nothing, because `window.practiceClear` never gets defined. Prefer a
  double-quoted JS string over escaping an apostrophe. After touching any inline JS,
  validate it: extract every `<script>` body from the built reports and run
  `node --check` over them. That catches exactly this class of bug, which no Python
  test would.
- **`BrokenPipeError` in the terminal is not a failure.** It means the browser tab
  went away before a slow reply arrived (the DeepSeek summary takes 20-60s). The work
  had already been done and saved by then. `Handler._send` guards the whole
  write — headers included, because `end_headers()` is usually where it raises — and
  `QuietServer.handle_error` swallows the disconnect so the traceback stays out of
  the log.
- Forgot to **restart the server** after a `webapp/*.py` edit → old behavior persists.
- Forgot to **rebuild** after a `report/*.py` edit → the served HTML is stale.
- DeepSeek 400 "supported API model names…" → wrong `deepseek_model` (use v4-pro/flash).
  Note `_call_deepseek` still falls back to `"deepseek-chat"` if the key is missing
  from config — that value is rejected by this account.
- `report.source_label_from_path` joins platform + rank **with a space** ("Fox 3 dan");
  it used to concatenate directly, which was fine for 野狐3段 but wrong in English.
- Transcription/summary can't be tested in a Linux sandbox (no model, no key, network
  blocked); implement carefully and verify structure, they run on the user's Mac.
