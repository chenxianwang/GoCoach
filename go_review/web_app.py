#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mirror of Go - KataGo game review, local web app.

Starts a tiny server bound to 127.0.0.1 only and opens a browser:

    /            dashboard: the analyse / import module + every analysed report
    /analyze     the standalone "Analyse / Import" page
    /r/<report>  one report (with a top bar to go back or switch reports)

Analysis still runs through the local ikatago client (cloud KataGo); your
credentials never leave this machine.

Launch by double-clicking "Mirror of Go.command" in the repo root, or:
    python3 go_review/web_app.py            # port 8765, opens a browser
    python3 go_review/web_app.py --port 9000 --no-browser

The implementation lives in webapp/ (split by concern: pages, jobs, voice
transcription, the DeepSeek summary, backup, the HTTP handler, ...). This
file just puts go_review/ on sys.path -- so webapp/*.py and the sibling
pipeline.py / report / import_lizzie.py / go_terms.py modules can find each
other -- and calls into it.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from webapp.server import main  # noqa: E402

if __name__ == "__main__":
    main()
