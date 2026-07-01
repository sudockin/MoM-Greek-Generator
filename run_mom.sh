#!/bin/bash
# Headless MoM pipeline: recording -> Greek transcript WITH speaker names -> (optional) English MoM.
#
# Transcription uses whisper.cpp large-v3-turbo on the Metal GPU when a large/turbo
# model is present (≈10x faster than WhisperX CPU), else WhisperX. Speaker names for
# video calls come from on-screen OCR (Google Meet / Teams) — no tokens. The English
# MoM (local Ollama) is OPTIONAL: pass --mom to also generate it.
#
# Usage:  ./run_mom.sh /path/to/recording.mp4 [output_dir] [--mom] [--attendees "Name One, Name Two"]
#
# The heavy lifting lives in server.py so the CLI and the web UI never drift apart.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REC="${1:?Usage: ./run_mom.sh /path/to/recording.mp4 [output_dir] [--mom] [--attendees \"...\"]}"
shift || true
OUT="$SCRIPT_DIR/mom_output"
WANT_MOM=0
ATTENDEES=""
while [ $# -gt 0 ]; do
  case "$1" in
    --mom) WANT_MOM=1; shift ;;
    --attendees) ATTENDEES="${2:-}"; shift 2 ;;
    *) OUT="$1"; shift ;;
  esac
done
mkdir -p "$OUT"

REC="$REC" OUT="$OUT" WANT_MOM="$WANT_MOM" ATTENDEES="$ATTENDEES" \
python3 - "$SCRIPT_DIR" <<'PY'
import os, subprocess, sys, time
sys.path.insert(0, sys.argv[1])
import server

rec = os.environ["REC"]; out = os.environ["OUT"]
want_mom = os.environ.get("WANT_MOM") == "1"
attendees = os.environ.get("ATTENDEES", "")

tools = server.detect_all()
if not tools["ffmpeg"] or not tools["whisper"]:
    sys.exit("Missing tools: " + "; ".join(tools["issues"]))
ff = tools["ffmpeg"]; w = tools["whisper"]
print(f"==> Engine: {w['type']} ({os.path.basename(w.get('model',''))})")

print("==> [1/3] Extracting 16 kHz mono WAV")
wav = os.path.join(out, "audio.wav")
subprocess.run([ff, "-y", "-i", rec, "-vn", "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_s16le", wav], check=True)

print("==> [2/3] Transcribing"); t0 = time.time()
tp = server.transcribe("cli", w, wav, out, "el")
transcript = open(tp, encoding="utf-8", errors="replace").read().strip()
print(f"    done in {time.time()-t0:.0f}s")

if server.is_video(rec):
    print("==> [2.5] Reading on-screen speaker names (OCR, no token)…"); t0 = time.time()
    named, roster, speakers = server.ocr_name_transcript(
        rec, os.path.join(out, "audio.json"), ff, roster=attendees)
    if named:
        transcript = named
        open(tp, "w", encoding="utf-8").write(transcript + "\n")
        print(f"    speakers: {', '.join(speakers)}  ({time.time()-t0:.0f}s)")
    else:
        print("    (no on-screen names found — transcript left unlabelled)")

if want_mom and tools["ollama"]["models"]:
    model = tools["default_model"]
    print(f"==> [3/3] Generating MoM with {model}")
    md = server.summarize_once(transcript, model, attendees)
    open(os.path.join(out, "MoM.md"), "w", encoding="utf-8").write(md + "\n")
elif want_mom:
    print("==> [3/3] Skipped MoM — Ollama not available")

print()
print(f"Done. Outputs in: {out}")
print("  - transcript.txt   (Greek, with speaker names for Gemini)")
if want_mom and os.path.exists(os.path.join(out, "MoM.md")):
    print("  - MoM.md           (English Minutes of Meeting)")
PY
