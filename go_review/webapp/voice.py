"""Voice-review recording, local Whisper transcription, and the English Coach library handoff."""

import os
import re
import time
import tempfile
import datetime

from .config_jobs import _safe_cfg


# ---------------------------------------------------------------------------
# Voice notes: transcription with a local faster-whisper model
# ---------------------------------------------------------------------------

_WHISPER = None


_WHISPER_ERR = None


def _get_whisper():
    global _WHISPER, _WHISPER_ERR
    if _WHISPER is not None:
        return _WHISPER
    if _WHISPER_ERR is not None:
        return None
    path = os.path.expanduser((_safe_cfg().get("whisper_model") or "").strip())
    if not path or not os.path.isdir(path):
        _WHISPER_ERR = ("Speech model folder not found (whisper_model in "
                        "config.json): " + (path or "not configured"))
        return None
    try:
        from faster_whisper import WhisperModel
    except Exception as e:  # noqa: BLE001
        _WHISPER_ERR = f"faster-whisper is not installed (pip install faster-whisper): {e}"
        return None
    try:
        print("Loading the speech model (slow the first time)...")
        _WHISPER = WhisperModel(path, device="cpu", compute_type="int8")
        print("Speech model ready.")
    except Exception as e:  # noqa: BLE001
        _WHISPER_ERR = f"Could not load the speech model: {e}"
        return None
    return _WHISPER


DEFAULT_VOICE_AUDIO_DIR = "~/Desktop/English Coach/VideoAudioFiles"


def voice_audio_dir():
    """Where recordings are kept, from config's `voice_audio_dir`.

    Recordings are deliberately stored OUTSIDE the report folders so another
    project (the English-coaching one) can consume them without reaching into
    go_review.  Set the key to "" to go back to discarding audio after
    transcription."""
    raw = _safe_cfg().get("voice_audio_dir", DEFAULT_VOICE_AUDIO_DIR)
    raw = (raw or "").strip()
    return os.path.expanduser(raw) if raw else ""


def _audio_stem(rel):
    """`Recording <YYYYMMDD-HHMMSS> <report>` — the English Coach library keys a
    recording on its folder name ("stem") and names every file inside after it.
    Keeping their `Recording <date>-<time>` prefix makes these sort in with the
    user's own takes; the report suffix says which Go project it came from."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = (rel or "").replace("/", "_").replace("\\", "_").strip()
    base = re.sub(r"[^\w-]", "_", base)        # no dots: keeps ".." out of names
    base = re.sub(r"_{2,}", "_", base).strip("_")
    return f"Recording {stamp} {base}" if base else f"Recording {stamp}"


def save_voice_audio(data, rel):
    """Write the raw recording into its own folder, English Coach style:

        VideoAudioFiles/Recording 20260726-224624 yehu_3d_r2/
            Recording 20260726-224624 yehu_3d_r2.webm

    The matching `.txt` transcript is added by `save_voice_text` once whisper
    has run, giving that project the `<stem>/<stem>.{webm,txt}` pair it expects.
    (`.polished.txt`, `.result.json` and `history.json` are that app's business,
    so we never write them.)

    Returns (path, error).  A failure here must never lose the user's take, so
    the caller falls back to a temp file and still transcribes."""
    d = voice_audio_dir()
    if not d:
        return None, None                      # retention switched off on purpose
    try:
        stem = _audio_stem(rel)
        folder = os.path.join(d, stem)
        if os.path.isdir(folder):    # same report, same second — never clobber
            i = 2
            while os.path.isdir(f"{folder}-{i}"):
                i += 1
            folder, stem = f"{folder}-{i}", f"{stem}-{i}"
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, stem + ".webm")
        with open(path, "wb") as f:
            f.write(data)
        return path, None
    except Exception as e:                      # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def save_voice_text(audio_path, text):
    """Drop `<stem>.txt` next to the recording — plain transcript prose, no
    header, matching what the English Coach library already stores."""
    if not (audio_path and text and text.strip()):
        return None
    try:
        path = os.path.splitext(audio_path)[0] + ".txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write(text.strip() + "\n")
        return path
    except Exception as e:                      # noqa: BLE001
        print(f"  ! could not write the transcript next to the recording: {e}")
        return None


# ---------------------------------------------------------------------------
# Transcription progress.  The POST blocks until the whole take is done, which
# on a long recording is a minute or more of silence; the browser polls this
# while it waits.  faster-whisper hands back a *generator* of segments plus the
# audio duration, so this is genuine progress through the audio, not a spinner.
# ---------------------------------------------------------------------------

_PROGRESS = {"active": False, "stage": "", "pct": 0, "pos": 0.0,
             "duration": 0.0, "elapsed": 0.0, "label": ""}


def _mmss(sec):
    sec = int(max(0, sec or 0))
    return f"{sec // 60}:{sec % 60:02d}"


def _progress(stage, pct=None, pos=None, duration=None, started=None,
              active=True):
    p = _PROGRESS
    p["active"] = active
    p["stage"] = stage
    if pct is not None:
        p["pct"] = max(0, min(100, int(pct)))
    if pos is not None:
        p["pos"] = float(pos)
    if duration is not None:
        p["duration"] = float(duration)
    if started:
        p["elapsed"] = time.time() - started
    bits = [stage]
    if p["duration"] and stage.startswith("Transcribing"):
        bits = [f"Transcribing {p['pct']}%",
                f"{_mmss(p['pos'])} of {_mmss(p['duration'])}"]
        # Rough ETA from the throughput so far — better than no number at all.
        if p["pos"] > 1 and p["elapsed"] > 1:
            rate = p["pos"] / p["elapsed"]
            if rate > 0:
                left = (p["duration"] - p["pos"]) / rate
                if left >= 1:
                    bits.append(f"about {_mmss(left)} left")
    elif p["elapsed"] >= 3:
        bits.append(f"{_mmss(p['elapsed'])} elapsed")
    p["label"] = " · ".join(bits)
    return p


def transcribe_audio(data, rel=None):
    """Save the recording, then transcribe it with faster-whisper.

    Returns (text, error, stem) where `stem` is the English Coach folder name
    the take was filed under.  The audio is kept permanently in
    `voice_audio_dir()`; only the fallback temp copy is deleted."""
    started = time.time()
    _progress("Saving the recording", pct=0, pos=0, duration=0,
              started=started)
    saved, save_err = save_voice_audio(data, rel)
    if save_err:
        print(f"  ! could not save the recording to "
              f"{voice_audio_dir()}: {save_err}")
    # The folder name is the useful identifier — the .webm and .txt inside both
    # carry it, and it is what the other project keys on.
    stem = (os.path.basename(os.path.dirname(saved)) if saved else None)

    _progress("Loading the speech model", pct=0, started=started)
    m = _get_whisper()
    if not m:
        # No model, but the audio is already safe on disk — say so, so the user
        # knows the take was not lost.
        err = _WHISPER_ERR or "Voice transcription is unavailable."
        if saved:
            err += (f" The recording itself was saved to \"{stem}\" "
                    f"(transcript missing, so add the .txt by hand or re-run "
                    f"once the model is installed).")
        _progress("", active=False)
        return None, err, stem

    lang = (_safe_cfg().get("whisper_language") or "").strip() or None
    tmp = None
    if saved:
        src = saved
    else:
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(data)
            tmp = f.name
        src = tmp
    try:
        _progress("Analysing the audio", pct=0, started=started)
        segments, info = m.transcribe(src, language=lang, vad_filter=True)
        total = float(getattr(info, "duration", 0) or 0)
        _progress("Transcribing", pct=0, pos=0, duration=total, started=started)
        parts, n = [], 0
        # `segments` is a generator: whisper only does the work as we iterate,
        # so this loop IS the transcription and each step is real progress.
        for s in segments:
            parts.append(s.text)
            n += 1
            end = float(getattr(s, "end", 0) or 0)
            pct = (end / total * 100) if total else 0
            _progress("Transcribing", pct=min(99, pct), pos=end,
                      duration=total, started=started)
            if n % 5 == 0:
                print(f"    ... transcribed {_mmss(end)} of {_mmss(total)}",
                      flush=True)
        text = "".join(parts).strip()
        _progress("Saving the transcript", pct=100, started=started)
        # Pair the transcript with the audio, the way the English Coach library
        # stores every other recording.
        save_voice_text(saved, text)
        return text, None, stem
    except Exception as e:  # noqa: BLE001
        return None, f"Transcription failed: {e}", stem
    finally:
        _progress("", active=False)
        if tmp:                                 # only the fallback copy goes away
            try:
                os.remove(tmp)
            except OSError:
                pass
