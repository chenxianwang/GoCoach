#!/usr/bin/env python3
"""One command to analyse your recent games and build the report.

Usage (run on your Mac, where ikatago can log in):

    python3 run_review.py              # analyse new games, then build the report
    python3 run_review.py --force      # re-analyse ALL games (captures the new
                                       # blunder ownership / AI territory data)
    python3 run_review.py --selfcheck  # list the games that WOULD be analysed
                                       # (no engine, no cloud — instant)
    python3 run_review.py --report-only  # rebuild the HTML from existing JSON

Edit config.json to change credentials, number of games, or analysis strength.
"""

import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import analyze
import report


def main():
    argv = sys.argv[1:]

    if "--selfcheck" in argv:
        return analyze.main(["--selfcheck"])

    if "--report-only" in argv:
        return report.main([])

    # Forward analysis flags (e.g. --force / --reanalyze to re-do every game,
    # --scores-only to refresh just the final-position score).
    pass_through = [a for a in argv
                    if a in ("--force", "--reanalyze",
                             "--scores-only", "--score-only")]
    rc = analyze.main(pass_through)
    if rc != 0:
        return rc
    return report.main([])


if __name__ == "__main__":
    sys.exit(main())
