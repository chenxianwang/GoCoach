# Working Desktop

A page for launching your local apps without opening a terminal. Double-click
**`Working Desktop.command`** in the repo root, or:

```bash
python3 -m workdesk
```

It opens <http://127.0.0.1:8600/> with one card per app: Launch, Open, Stop, and
the app's log.

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
running, with **Open** available and **Stop** greyed out — stopping something
this process did not start is not something it can do cleanly, so it says so
rather than pretending.

## Stopping

Apps started here run in their own process group and are stopped by signalling
the whole group (TERM, then KILL). This matters because `command` goes through
a shell: killing the shell alone would leave the real app orphaned and the port
still bound.

Closing the launcher does **not** stop the apps you launched.

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
