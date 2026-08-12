#!/bin/bash
#
# Extract a video's audio track as Opus in a .webm container:
#
#     ffmpeg -i input.mov -vn -c:a libopus -b:a 128k output.webm
#
# The two file choices are native macOS dialogs rather than arguments, because
# the Working Desktop card has nowhere to type: the browser only ever sends an
# id, never a command, and it must stay that way -- a card that accepted paths
# from the page would be a card that accepts anything from the page.
#
# This lives in a script instead of inside apps.json because the command would
# otherwise be escaped three times over (JSON, then shell, then AppleScript),
# which is unreadable and one stray quote away from silently not running.
set -u

# The launcher inherits whatever PATH Terminal gave it, which on a fresh login
# may not include Homebrew, so find ffmpeg rather than assuming it.
FFMPEG=""
for c in "$(command -v ffmpeg 2>/dev/null || true)" \
         /opt/homebrew/bin/ffmpeg /usr/local/bin/ffmpeg; do
  if [ -n "$c" ] && [ -x "$c" ]; then FFMPEG="$c"; break; fi
done
if [ -z "$FFMPEG" ]; then
  echo "ffmpeg not found -- install it with: brew install ffmpeg"
  exit 1
fi

# Values reach AppleScript as argv, never spliced into the source text: these
# are the user's own filenames, which are routinely Chinese and may hold quotes
# or backslashes that would otherwise end the AppleScript string early.
choose_input() {
  osascript <<'APPLESCRIPT'
on run argv
  try
    tell application "System Events" to activate
    set f to choose file with prompt "Choose the video to extract audio from"
    return POSIX path of f
  on error number -128
    return ""
  end try
end run
APPLESCRIPT
}

choose_output() {
  osascript - "$1" "$2" <<'APPLESCRIPT'
on run argv
  try
    tell application "System Events" to activate
    set f to choose file name with prompt "Save the audio as" ¬
      default name (item 1 of argv) ¬
      default location (POSIX file (item 2 of argv))
    return POSIX path of f
  on error number -128
    return ""
  end try
end run
APPLESCRIPT
}

IN=$(choose_input)
if [ -z "$IN" ]; then
  echo "Cancelled -- no video chosen."
  exit 1
fi
if [ ! -f "$IN" ]; then
  echo "Not a file: $IN"
  exit 1
fi

# Offer the video's own name and folder, which is nearly always what is wanted;
# the dialog is there for when it is not.
name=$(basename "$IN")
OUT=$(choose_output "${name%.*}.webm" "$(dirname "$IN")")
if [ -z "$OUT" ]; then
  echo "Cancelled -- no destination chosen."
  exit 1
fi
# The dialog will accept any name typed over the default, and ffmpeg picks the
# container from the extension -- a missing .webm would leave it guessing.
case "$OUT" in
  *.webm) ;;
  *) OUT="$OUT.webm" ;;
esac

# -y: the save dialog has already asked about overwriting, so asking again here
# would hang, there being no terminal to answer from.
# -nostdin: the launcher runs actions with stdin closed.
out=$("$FFMPEG" -hide_banner -nostdin -y -i "$IN" \
        -vn -c:a libopus -b:a 128k "$OUT" 2>&1)
code=$?
if [ "$code" -ne 0 ]; then
  # The card shows the *first* line of output as its message, so the useful
  # sentence has to come before anything else -- echoing the command up front
  # would put a truncated ffmpeg invocation on the card instead.
  echo "Could not extract audio from $name -- see the log."
fi
echo "\$ $FFMPEG -i \"$IN\" -vn -c:a libopus -b:a 128k \"$OUT\""
echo "$out"
[ "$code" -eq 0 ] || exit "$code"

if [ ! -s "$OUT" ]; then
  echo "ffmpeg reported success but wrote nothing to $OUT"
  exit 1
fi

# Show where it landed: the card can only say that the run worked, not where the
# file went, and "decide where to save it" deserves a confirmation.
open -R "$OUT" 2>/dev/null || true
echo "Saved $(du -h "$OUT" | cut -f1 | tr -d ' ') to $OUT"
