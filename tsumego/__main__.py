"""Command line entry point.

    python3 -m tsumego fetch            # crawl (resumable; safe to re-run)
    python3 -m tsumego fetch --limit 40 --level 3级
    python3 -m tsumego report           # build the dashboard from the cache
    python3 -m tsumego report --open
"""

import os
import sys
import json
import argparse
import webbrowser

from . import crawl, report
from .analyze import analyse, LEVEL_NAMES
from .api import Client, NotLoggedIn

NAME_TO_NUMBER = {v: k for k, v in LEVEL_NAMES.items()}


def _levels_arg(values):
    if not values:
        return None
    out = set()
    for v in values:
        v = v.strip()
        if v in NAME_TO_NUMBER:
            out.add(NAME_TO_NUMBER[v])
        elif v.isdigit():
            out.add(int(v))
        else:
            raise SystemExit(f"Unknown level {v!r}. Try one of: "
                             + ", ".join(LEVEL_NAMES.values()))
    return out


def cmd_fetch(args):
    try:
        client = Client(delay=args.delay)
    except NotLoggedIn as e:
        raise SystemExit(f"{e}\n\nSee tsumego/README.md for how to get the cookie.")
    crawl.crawl(client, limit=args.limit, levels=_levels_arg(args.level))


def cmd_report(args):
    runs = crawl.load_runs()
    if not runs:
        raise SystemExit("No cached runs yet -- run `python3 -m tsumego fetch` first.")
    agg = analyse(runs, crawl.load_diagram)
    out = args.out or os.path.join(crawl.HERE, "dashboard.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(report.build_html(agg, need=args.need, total=args.total))
    print(f"{agg['n']:,} questions from {agg['n_runs']:,} runs "
          f"-> {agg['accuracy'] * 100:.1f}% accuracy")
    print("misses: " + ", ".join(f"{k}={v}" for k, v in agg["kinds"].most_common()))
    print(f"Dashboard written: {out}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in agg.items() if k != "attempts"},
                      f, ensure_ascii=False, indent=2, default=str)
        print(f"Stats JSON written: {args.json}")
    if args.open:
        webbrowser.open("file://" + os.path.abspath(out))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tsumego",
                                 description="101weiqi Skill Test diagnostics")
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="crawl your records into the local cache")
    f.add_argument("--limit", type=int, help="only the N most recent runs")
    f.add_argument("--level", action="append",
                   help="restrict to a level, e.g. --level 3级 (repeatable)")
    f.add_argument("--delay", type=float, default=0.7,
                   help="seconds between requests (default 0.7)")
    f.set_defaults(func=cmd_fetch)

    r = sub.add_parser("report", help="build the dashboard from the cache")
    r.add_argument("--out", help="output path (default tsumego/dashboard.html)")
    r.add_argument("--json", help="also dump the aggregate stats as JSON")
    r.add_argument("--open", action="store_true", help="open it in a browser")
    r.add_argument("--need", type=int, default=8,
                   help="questions needed to pass a run (default 8)")
    r.add_argument("--total", type=int, default=10,
                   help="questions per run (default 10)")
    r.set_defaults(func=cmd_report)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
