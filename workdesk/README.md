# Working Desktop

A page for launching your local apps without opening a terminal. Double-click
**`~/Desktop/Working Desktop.command`**, or from anywhere:

```bash
python3 -m workdesk
```

It opens <http://127.0.0.1:8600/> with one card per app: Launch, Open, Stop, and
the app's log.

## The launcher lives on the Desktop

`Working Desktop.command` sits on the Desktop for one-click access while the
code stays here under version control, so it holds an **absolute path** to this
repo rather than `cd "$(dirname "$0")"`:

```bash
REPO="/Users/chenxianwang/Desktop/ClaudeCode-Go"
```

If you move or rename the repo, open that file and update `REPO` — it checks
the path first and says exactly that rather than failing obscurely. To recreate
it from scratch, a two-line version is enough:

```bash
cd /Users/chenxianwang/Desktop/ClaudeCode-Go && python3 -m workdesk
```

## Adding an app

Edit [`apps.json`](apps.json) and reload the page — no restart needed.

```json
{
  "id": "my-app",
  "name": "My App",
  "emoji": "🚀",
  "note": "One line describing it.",
  "command": "python serve.py",
  "cwd": "~/Desktop/My App",
  "probe": {"type": "port", "port": 5000},
  "url": "http://127.0.0.1:5000/"
}
```

| Field | Meaning |
|---|---|
| `id` | Stable key. The browser sends *this*, never a command. |
| `command` | Run through the shell, so quoting, `&&` and `\|` work as in Terminal. |
| `cwd` | Where to run it. `~` is expanded. Defaults to your home directory. |
| `probe` | How to tell it is running: `{"type":"port","port":N}` or `{"type":"process","match":"substring"}`. |
| `url` | Optional. Shows an **Open** button while the app is up. |

`cwd` matters more than it looks: LizzieYZY reads `config.txt` and `persist`
from its working directory, so pointing it somewhere else silently gives it a
different engine setup. The entry is set to `~`, matching what you get running
the command from a fresh Terminal.

## Status is probed, not remembered

An app can be running without this launcher having started it — you may have
started it from Terminal, or restarted the launcher since. So the page does not
trust its own bookkeeping: it connects to the port (or looks for the process)
every few seconds. That is why an app you started elsewhere still shows as
running, with **Open** available. The card says where it came from
("started here" vs "started elsewhere"), but either way it can be stopped.

## Stopping

Stop works on anything the page shows as running, not just apps launched from
this window. The record of what this process started dies with the process, so
relying on it meant Stop went dead every time the launcher window was reopened.
Instead the app is located exactly the way it is probed — by port (`lsof`) or
process name (`pgrep`) — and that is what gets signalled: TERM, then KILL if it
lingers, then the probe is re-checked to confirm it really went away.

Signalling covers the whole process group, because `command` goes through a
shell: killing the shell alone would leave the real app orphaned and the port
still bound. Aiming that broadly needs care, so `procs.py` will never target
this launcher, pid 1, or any of its ancestors — a loose `"match"` could
otherwise sweep in the Terminal that started everything. When an app happens to
share a process group with the launcher, only its own pid is signalled, since a
group-wide kill there would take the launcher down too.

Closing the launcher does **not** stop the apps you launched.

`tests/test_stop.py` covers all of this:

```bash
python3 workdesk/tests/test_stop.py
```

## When the port is busy

Closing a Terminal window does not always kill what was running in it, so an
old launcher can outlive its window and keep port 8600. Starting a new one then
used to fail with `OSError: [Errno 48] Address already in use` and a traceback.

Now it checks what is on the port. If it is another Working Desktop, it just
opens that one. If it is something else, it says so and suggests another port.

To clear out a stale launcher by hand:

```bash
pkill -f "python3 -m workdesk"
```

Note that reusing an old launcher also means running whatever version of the
code it started with — after editing anything here, kill it and start fresh.

## Logs

Each app's output goes to `logs/<id>.log` (gitignored), shown by the **log**
link on its card. A command that dies immediately is reported on the card
rather than silently appearing to have worked:

```
Exited immediately with code 3 -- see the log.
```

## A note on safety

This page starts processes, so it is built to be uninteresting to attack:

- It binds to **127.0.0.1** only.
- **The browser never sends a command.** It sends an `id`, which is looked up in
  `apps.json`. There is no code path that executes a string from a request, so
  the worst case is starting something you had already listed yourself.
- Launch/stop are POST and are refused when the request carries a foreign
  `Origin`, so a random site you happen to visit cannot quietly poke this port.

Anything in `apps.json` runs with your privileges — treat it like your shell
history, and keep it to commands you would type yourself.

## Icons

`emoji` covers most apps. When no emoji fits, use a named inline icon instead:

```json
{ "id": "lizzie", "name": "LizzieYZY", "icon": "goban" }
```

| Name | Looks like |
|---|---|
| `goban` | A wooden Go board with black and white stones |

Unicode has no Go symbol — 🀄 is a mahjong tile and ♟ is chess — which is why
this exists. Add more in `ICONS` in [`page.py`](page.py); an unknown name
renders a visible “?” rather than silently disappearing.
