#!/bin/bash
# Double-click to open the Working Desktop: a page for launching your local
# apps without a terminal. Starts a small server on 127.0.0.1 only.
# Closing this window stops the launcher; apps you started keep running.

cd "$(dirname "$0")" || exit 1

PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  echo "python3 not found. Install Python 3 (python.org or Xcode command line tools)."
  echo "Press return to close..."; read -r _; exit 1
fi

"$PY" -m workdesk
code=$?
if [ $code -ne 0 ]; then
  echo ""
  echo "Exited with code $code."
  echo "If the port is busy: python3 -m workdesk --port 8601"
  echo "Press return to close..."; read -r _
fi
