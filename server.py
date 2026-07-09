#!/usr/bin/env python3
"""Local no-token MoM generator — web UI.

A single-file, stdlib-only web app that turns a meeting recording into an
English Minutes-of-Meeting, fully locally:

    recording -> ffmpeg (16kHz mono WAV) -> Whisper (transcript) -> Ollama (MoM)

No API tokens are spent. No pip installs are required (Python standard library
only). All heavy tools (ffmpeg / Whisper / Ollama) are auto-detected so the same
file works on any colleague's Mac once they've run setup.sh.

Run:  python3 server.py          (opens http://127.0.0.1:8765 in your browser)
"""

import html
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
PORT = int(os.environ.get("MOM_PORT", "8765"))
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
OLLAMA_URL = f"http://{OLLAMA_HOST}"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_BASE = os.path.expanduser("~/Documents/MoM Outputs")
CONFIG_DIR = os.path.expanduser("~/.cache/mom-generator")
VENV_BIN = os.path.join(CONFIG_DIR, "venv", "bin")
VENV_PY = os.path.join(VENV_BIN, "python")
OCR_SCRIPT = os.path.join(APP_DIR, "ocr_speakers.py")
GEMINI_PROMPT_FILE = os.path.join(APP_DIR, "Gemini MoM Prompt.md")
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


def gemini_prompt(transcript=""):
    """The reusable Gemini styling prompt (between the ===== markers in the .md),
    with the transcript spliced in. Falls back to a tiny built-in if the file is
    missing so the button never breaks."""
    body = ""
    try:
        with open(GEMINI_PROMPT_FILE, encoding="utf-8") as f:
            doc = f.read()
        # The prompt lives between two lines that are exactly "=====" (full-line
        # delimiters — inline mentions of ===== in the prose are ignored).
        m = re.search(r"(?m)^=====\s*$\n(.*?)\n^=====\s*$", doc, re.S)
        if m:
            body = m.group(1).strip()
    except OSError:
        pass
    if not body:
        body = ("Turn the transcript below into a polished English Minutes-of-Meeting "
                "follow-up email as one block of inline-styled HTML for Gmail. Translate "
                "any Greek. Never invent names or facts.\n\nTRANSCRIPT:\n<<<TRANSCRIPT>>>")
    return body.replace("<<<TRANSCRIPT>>>", transcript or "<paste transcript here>")

# YouTube/link download is an OPTIONAL, personal-use add-on kept in a separate
# module that the shared build omits. If youtube.py is absent, the feature is off.
try:
    import youtube as youtube_dl
    HAS_YOUTUBE = True
except Exception:
    youtube_dl = None
    HAS_YOUTUBE = False
WHISPERX_MODEL = os.environ.get("WHISPERX_MODEL", "large-v3")
# Fast Greek transcription on Apple Silicon: whisper.cpp runs large-v3 on the
# Metal GPU (~10x faster than WhisperX's CPU-only int8). We prefer a large/turbo
# ggml model when present; small/base fall back to WhisperX (better Greek).
def find_whispercpp_dir():
    """Locate a whisper.cpp checkout/install for its bundled `main` binary and
    `models/` dir. Discovery order: WHISPERCPP_DIR env var → common Homebrew/cache
    locations → the directory of a whisper-cli/whisper-cpp on PATH. Returns "" if
    none is found (never a user-specific absolute path)."""
    env = os.environ.get("WHISPERCPP_DIR")
    if env:
        return os.path.expanduser(env)
    for c in [
        os.path.expanduser("~/.cache/whisper-cpp"),
        os.path.expanduser("~/whisper.cpp"),
        "/opt/homebrew/share/whisper-cpp",
        "/usr/local/share/whisper-cpp",
        "/opt/homebrew/opt/whisper-cpp",
    ]:
        if os.path.isdir(c):
            return c
    cli = shutil.which("whisper-cli") or shutil.which("whisper-cpp") or shutil.which("main")
    if cli:
        return os.path.dirname(os.path.realpath(cli))
    return ""


WHISPERCPP_DIR = find_whispercpp_dir()
# Models that are "high quality" enough to beat WhisperX-on-CPU for Greek.
HQ_CPP_MODEL_RE = re.compile(r"(large|turbo|medium)", re.I)
# pyannote.audio 4.x routes diarization through the self-contained community-1
# pipeline (even "3.1" pulls its components), so that's the one gated repo to accept.
DIARIZE_MODEL = os.environ.get("DIARIZE_MODEL", "pyannote/speaker-diarization-community-1")


def load_config():
    path = os.path.join(CONFIG_DIR, "config.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def hf_token():
    return os.environ.get("HF_TOKEN") or load_config().get("hf_token") or ""

# ----------------------------------------------------------------------------
# The MoM prompt (kept in sync with summarize_mom.py)
# Built via build_prompt() so transcript/attendee text is inserted literally
# (no str.format, which would choke on stray { } in a transcript).
# ----------------------------------------------------------------------------
PROMPT_TEMPLATE = """Create a Google Gemini-style MoM (Minutes of Meeting) from this transcript.

The transcript may be in Greek. Write the MoM in clear internal English for efood/Foody and DH stakeholders.

__ATTENDEES_BLOCK__

Rules:
- Preserve local vs DH central ownership.
- Do not commit to DH-owned capabilities unless explicitly confirmed.
- ATTRIBUTION & NO INVENTION (critical):
  - A valid owner is a name that literally appears in the transcript text, or a name from the Attendees list above. NEVER write any other name — do not fill in plausible-sounding names, and do not reuse any example names from these instructions.
  - Attribute an action/decision to a person only when the transcript explicitly ties that named person to it. Use that exact name as the owner.
  - If an action item's owner is not clearly stated, set Owner to "⚠️ owner not stated". Do not guess.
  - Never invent decisions, commitments, dates, numbers, names, or owners. If something is only implied, put it under Open Questions or label it "(assumption)".
- Flag assumptions explicitly.
- Use these sections, in this order: Attendees, Executive Summary, Key Decisions, Ownership Split, Action Items, Open Questions, Risks, Next Decision.
- Format the whole MoM as GitHub-flavoured Markdown: a single "# Minutes of Meeting" title, then each section title as a "## " heading (e.g. "## Executive Summary"); use bullet lists and **bold** for inline labels.
- Attendees section: list the provided attendees; mark anyone never clearly referenced in the transcript as "(listed; not clearly identified in audio)". If no list was provided, write "No attendee list provided."
- Use red/yellow/green status signals (🔴/🟡/🟢) for risk and priority.
- Action Items MUST be a markdown table with columns: Action | Owner | Due | Status. Owner must be a name from the Attendees list or "⚠️ owner not stated".
- Be faithful to the transcript; do not invent.

Transcript:
__TRANSCRIPT__
"""


def build_prompt(transcript, attendees_text=""):
    names = [n.strip() for part in (attendees_text or "").replace("\n", ",").split(",")
             for n in [part] if part.strip()]
    if names:
        block = ("Attendees (the ONLY names you may use as owners):\n"
                 + "\n".join(f"- {n}" for n in names))
    else:
        block = ("No attendee list was provided. Use a person's name as an owner only "
                 "when it is explicitly spoken in the transcript; otherwise write "
                 "\"⚠️ owner not stated\". Never invent a name.")
    if "SPEAKER_" in transcript:
        block += (
            "\n\nThe transcript is labelled with diarized speakers (SPEAKER_00, SPEAKER_01, …). "
            "Refer to them as 'Speaker 1', 'Speaker 2', etc. Replace a label with a real name ONLY "
            "if that speaker explicitly identifies themselves (e.g. says 'I am <name>') or is "
            "directly addressed by name. A speaker merely MENTIONING someone else's name does NOT "
            "identify that speaker. Most speakers stay unidentified — that is expected; never guess "
            "or invent a mapping. Under Attendees, include a short 'Speaker mapping' "
            "(SPEAKER_xx → name, or 'unidentified').")
    return PROMPT_TEMPLATE.replace("__ATTENDEES_BLOCK__", block).replace(
        "__TRANSCRIPT__", transcript)

# ----------------------------------------------------------------------------
# Tool auto-detection
# ----------------------------------------------------------------------------

def find_ffmpeg():
    candidates = [
        shutil.which("ffmpeg"),
        "/Applications/MediaHuman Audio Converter.app/Contents/Resources/ffmpeg",
        "/opt/homebrew/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def find_whisperx():
    for c in [os.path.join(VENV_BIN, "whisperx"), shutil.which("whisperx")]:
        if c and os.path.exists(c):
            return c
    return None


def find_whisper_cpp_bin():
    cpp_bins = [
        shutil.which("whisper-cli"),
        shutil.which("whisper-cpp"),
        os.path.join(WHISPERCPP_DIR, "main") if WHISPERCPP_DIR else None,
        shutil.which("main"),
        "/opt/homebrew/bin/whisper-cli",
        "/usr/local/bin/whisper-cli",
    ]
    return next((c for c in cpp_bins if c and os.path.exists(c)), None)


def find_whisper():
    """Return dict describing the available transcriber, or None.

    Priority: whisper.cpp large/turbo on Metal (fast + good Greek) > WhisperX >
    whisper.cpp small > openai-whisper. whisper.cpp wins only with a high-quality
    (large/turbo/medium) model; otherwise WhisperX gives better Greek."""
    cpp_bin = find_whisper_cpp_bin()
    cpp_model = find_whisper_cpp_model(cpp_bin) if cpp_bin else None
    cpp_is_hq = bool(cpp_model and HQ_CPP_MODEL_RE.search(os.path.basename(cpp_model)))

    if cpp_bin and cpp_is_hq:
        return {"type": "cpp", "bin": cpp_bin, "model": cpp_model}
    wx = find_whisperx()
    if wx:
        return {"type": "whisperx", "bin": wx, "model": WHISPERX_MODEL,
                "diarize": bool(hf_token())}
    if cpp_bin and cpp_model:
        return {"type": "cpp", "bin": cpp_bin, "model": cpp_model}
    owhisper = shutil.which("whisper")
    if owhisper:
        return {"type": "openai", "bin": owhisper}
    return None


def find_whisper_cpp_model(cpp_bin):
    base_models = os.path.join(os.path.dirname(cpp_bin or ""), "models")
    # Highest quality first so the fast Metal path is chosen when available.
    candidates = [
        os.environ.get("WHISPER_MODEL", ""),
        os.path.join(WHISPERCPP_DIR, "models", "ggml-large-v3-turbo-q5_0.bin"),
        os.path.join(WHISPERCPP_DIR, "models", "ggml-large-v3-turbo.bin"),
        os.path.join(WHISPERCPP_DIR, "models", "ggml-large-v3.bin"),
        os.path.expanduser("~/.cache/whisper-cpp/ggml-large-v3-turbo-q5_0.bin"),
        os.path.expanduser("~/.cache/whisper-cpp/ggml-large-v3-turbo.bin"),
        os.path.expanduser("~/.cache/whisper-cpp/ggml-large-v3.bin"),
        os.path.join(base_models, "ggml-large-v3-turbo-q5_0.bin"),
        os.path.join(base_models, "ggml-large-v3.bin"),
        os.path.join(WHISPERCPP_DIR, "models", "ggml-small.bin"),
        os.path.join(base_models, "ggml-small.bin"),
        os.path.expanduser("~/.cache/whisper-cpp/ggml-small.bin"),
        os.path.expanduser("~/.cache/whisper-cpp/ggml-medium.bin"),
        os.path.expanduser("~/.cache/whisper-cpp/ggml-base.bin"),
        "/opt/homebrew/share/whisper-cpp/ggml-small.bin",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def find_ollama():
    candidates = [
        shutil.which("ollama"),
        "/Applications/Ollama.app/Contents/Resources/ollama",
        "/opt/homebrew/bin/ollama",
        "/usr/local/bin/ollama",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def ensure_ollama(ollama_bin):
    """Make sure the Ollama server is up; start it if needed. Return model list."""
    models = ollama_models()
    if models is not None:
        return models
    if ollama_bin:
        env = dict(os.environ, OLLAMA_HOST=OLLAMA_HOST)
        try:
            subprocess.Popen(
                [ollama_bin, "serve"],
                stdout=open("/tmp/ollama_serve.log", "ab"),
                stderr=subprocess.STDOUT,
                env=env,
            )
        except Exception:
            return None
        for _ in range(20):
            time.sleep(1)
            models = ollama_models()
            if models is not None:
                return models
    return None


def ollama_models():
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as r:
            data = json.loads(r.read().decode())
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return None


def detect_all():
    ffmpeg = find_ffmpeg()
    whisper = find_whisper()
    ollama_bin = find_ollama()
    models = ensure_ollama(ollama_bin) if ollama_bin else None
    issues, notes = [], []
    if not ffmpeg:
        issues.append("ffmpeg not found — run ./setup.sh (installs ffmpeg)")
    if not whisper:
        issues.append("Transcriber not found — run ./setup.sh")
    # Ollama is OPTIONAL now: the main deliverable is the speaker-labelled Greek
    # transcript (to feed into Gemini). The local English MoM is a bonus that only
    # runs if Ollama is present, so a missing Ollama is a note, not a blocker.
    if not ollama_bin:
        notes.append("Local English-MoM step is off (Ollama not installed) — the transcript export still works.")
    elif models is None:
        notes.append("Ollama isn't running — open the Ollama app if you want the optional local MoM.")
    elif not models:
        notes.append("No Ollama model — run: ollama pull qwen2.5:7b for the optional local MoM.")

    diarize = False
    if whisper:
        if whisper["type"] == "cpp":
            mdl = os.path.basename(whisper["model"])
            fast = "⚡ Metal GPU" if HQ_CPP_MODEL_RE.search(mdl) else "for best Greek install a large model"
            notes.insert(0, f"Engine: whisper.cpp ({mdl}) · {fast} · 🗣️ speaker names from Google Meet (OCR)")
        elif whisper["type"] == "whisperx":
            notes.insert(0, f"Engine: WhisperX ({whisper['model']}) · 🗣️ speaker names from the video (Google Meet / Teams)")
        else:
            notes.insert(0, "Engine: openai-whisper")
    # YouTube/link support is an optional personal add-on (separate youtube.py +
    # yt-dlp + Deno). Absent from the shared build; the URL field only shows if present.
    ytdlp = HAS_YOUTUBE and youtube_dl.available()
    return {
        "ffmpeg": ffmpeg,
        "whisper": whisper,
        "whisper_type": whisper["type"] if whisper else None,
        "diarize": diarize,
        "ytdlp": ytdlp,
        "ollama": {"bin": ollama_bin, "models": models or []},
        "issues": issues,
        "notes": notes,
        "ready": not issues,
        "default_model": "qwen2.5:7b" if (models and "qwen2.5:7b" in models) else (models[0] if models else None),
    }


# ----------------------------------------------------------------------------
# Job management
# ----------------------------------------------------------------------------
JOBS = {}
JOBS_LOCK = threading.Lock()


def new_job(filename):
    jid = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        JOBS[jid] = {
            "id": jid,
            "filename": filename,
            "events": [],
            "status": "queued",
            "markdown": None,
            "transcript": None,
            "outdir": None,
            "error": None,
        }
    return jid


def emit(jid, ev):
    with JOBS_LOCK:
        job = JOBS.get(jid)
        if job is not None:
            job["events"].append(ev)


def safe_name(name):
    base = os.path.splitext(os.path.basename(name))[0]
    keep = "".join(c if (c.isalnum() or c in " -_") else "_" for c in base).strip()
    return keep[:60] or "recording"


def pretty_label(folder):
    """Human label for an output folder named '<name>-YYYYMMDD-HHMMSS'."""
    return re.sub(r"-\d{8}-\d{6}$", "", folder) or folder


def is_real_result(d):
    """A finished result has at least a transcript (the primary product) or a MoM."""
    return (os.path.exists(os.path.join(d, "transcript.txt"))
            or os.path.exists(os.path.join(d, "MoM.md")))


def cleanup_incomplete_outputs():
    """Remove output folders that produced neither a transcript nor a MoM
    (failed/abandoned runs), so ~/Documents/MoM Outputs only keeps real results.
    Skips active jobs' folders."""
    with JOBS_LOCK:
        active = {j.get("outdir") for j in JOBS.values() if j.get("status") in ("queued", "running")}
    try:
        for name in os.listdir(OUTPUT_BASE):
            if name.startswith("."):
                continue
            d = os.path.join(OUTPUT_BASE, name)
            if os.path.isdir(d) and d not in active and not is_real_result(d):
                shutil.rmtree(d, ignore_errors=True)
    except FileNotFoundError:
        pass


def run_pipeline(jid, src_path, language, model, attendees="", from_url=False):
    job = JOBS[jid]
    try:
        tools = detect_all()
        if not tools["ffmpeg"] or not tools["whisper"]:
            raise RuntimeError("Required tools missing: " + "; ".join(tools["issues"]))

        stamp = time.strftime("%Y%m%d-%H%M%S")
        outdir = os.path.join(OUTPUT_BASE, f"{safe_name(job['filename'])}-{stamp}")
        os.makedirs(outdir, exist_ok=True)
        job["outdir"] = outdir

        # ---- Preflight: tell the user up-front what's possible for THIS run ----
        # (engine, whether on-screen speaker naming can run, whether audio-only
        # diarization is available) — before a long transcription starts.
        wtype = tools["whisper"]["type"]
        engine = {"cpp": "whisper.cpp", "whisperx": "WhisperX", "openai": "openai-whisper"}.get(wtype, wtype)
        if wtype == "cpp":
            engine += f" ({os.path.basename(tools['whisper']['model'])})"
        ocr_py, ocr_reason = ocrmac_python()
        ocr_cap = "✅ yes" if ocr_py else f"❌ no — {ocr_reason}"
        diar_cap = "✅ yes" if (wtype == "whisperx" and hf_token()) else "❌ no (video uses OCR names; audio-only needs WhisperX + HF token)"
        emit(jid, {"type": "log", "line": f"⚙ Capabilities — engine: {engine} · "
                   f"on-screen speaker names (OCR): {ocr_cap} · audio diarization: {diar_cap}"})

        # ---- Step 0: download from URL (YouTube etc.) ----
        if from_url:
            if not (HAS_YOUTUBE and youtube_dl.available()):
                raise RuntimeError("YouTube/link support isn't installed in this build.")
            emit(jid, {"type": "stage", "stage": "download", "msg": "Downloading audio from the link…"})
            src_path = youtube_dl.download_media(src_path, outdir, jid, run_stream, emit, tools["ffmpeg"])

        # ---- Step 1: ffmpeg -> WAV ----
        emit(jid, {"type": "stage", "stage": "audio", "msg": "Extracting audio (16 kHz mono WAV)…"})
        wav = os.path.join(outdir, "audio.wav")
        run_stream(jid, [tools["ffmpeg"], "-y", "-i", src_path, "-vn", "-ac", "1",
                         "-ar", "16000", "-c:a", "pcm_s16le", wav])
        if not os.path.exists(wav):
            raise RuntimeError("ffmpeg did not produce audio.wav")
        is_upload_temp = (os.sep + ".uploads" + os.sep) in src_path
        # For AUDIO uploads the temp copy is done once we have the WAV. For VIDEO
        # we keep it — the OCR speaker-naming step (step 2.5) reads its frames —
        # and delete it after naming instead.
        if is_upload_temp and not is_video(src_path):
            try:
                os.remove(src_path)
            except OSError:
                pass

        # ---- Step 2: Whisper -> transcript ----
        # Token-free speaker naming: for video calls we read names off-screen (OCR),
        # so WhisperX transcribes WITHOUT diarization. Diarization (pyannote, needs a
        # HuggingFace token) is only used as an optional extra for AUDIO-only files
        # when a token happens to be configured.
        is_vid = is_video(src_path)
        is_whisperx = tools["whisper"]["type"] == "whisperx"
        # Audio-only diarization (anonymous SPEAKER_xx) is a WhisperX-only extra.
        diarize = (not is_vid) and is_whisperx and bool(hf_token())

        emit(jid, {"type": "stage", "stage": "transcribe", "msg": "Transcribing with Whisper…"})
        transcript_path = transcribe(jid, tools["whisper"], wav, outdir, language, diarize=diarize)
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            transcript = f.read().strip()
        if not transcript:
            raise RuntimeError("Transcript was empty — the audio may be silent or unsupported.")
        job["transcript"] = transcript
        emit(jid, {"type": "transcript", "text": transcript})

        # ---- Step 2.5: name the speakers ----
        # For ANY video (regardless of transcription engine) we OCR the on-screen
        # active-speaker name and label each segment — token-free. The attendee
        # list is used as a roster to lock OCR onto real names (Google Meet).
        speakers, roster, speaker_map = [], {}, {}
        if is_vid:
            emit(jid, {"type": "stage", "stage": "names", "msg": "Reading on-screen speaker names…"})
            named, roster, speakers = ocr_name_transcript(
                src_path, os.path.join(outdir, "audio.json"), tools["ffmpeg"],
                jid=jid, roster=attendees, ocr_python=ocr_py)
            # Only overwrite the segmented transcript when names were ACTUALLY
            # applied (speakers non-empty). A zero-name OCR run returns the
            # space-joined nameless fallback — keep the original segmentation.
            if named and speakers:
                transcript = named
                with open(transcript_path, "w", encoding="utf-8") as f:
                    f.write(transcript + "\n")
                job["transcript"] = transcript
                emit(jid, {"type": "transcript", "text": transcript})
                speaker_map = {s: s for s in speakers}  # identity; user can correct in the panel
            # Video frames no longer needed — drop the uploaded temp copy now.
            if is_upload_temp and os.path.exists(src_path):
                try:
                    os.remove(src_path)
                except OSError:
                    pass
        elif diarize:
            speakers = speaker_labels(transcript)  # audio-only diarization fallback

        job["raw_transcript"] = transcript if speakers else None
        job["speaker_map"] = speaker_map
        job["model"] = model
        job["attendees"] = attendees

        # ---- Step 3: optional local English MoM (Ollama) ----
        # The speaker-labelled transcript is the primary product (for Gemini).
        # Only generate the local MoM if the user asked AND Ollama is available.
        markdown = ""
        want_mom = bool(model) and model.lower() not in ("none", "skip", "")
        if want_mom and tools["ollama"]["models"]:
            emit(jid, {"type": "stage", "stage": "mom", "msg": f"Generating MoM with {model}…"})
            markdown = summarize_stream(jid, transcript, model, attendees)
            with open(os.path.join(outdir, "MoM.md"), "w", encoding="utf-8") as f:
                f.write(markdown + "\n")
        elif want_mom:
            emit(jid, {"type": "log", "line": "⚠ Ollama unavailable — skipping the local MoM; the transcript is ready for Gemini."})
        job["markdown"] = markdown or None

        roster_sorted = sorted(roster, key=lambda n: -roster[n])
        job["speakers"] = speakers
        job["roster"] = roster_sorted
        job["status"] = "done"
        emit(jid, {"type": "done", "markdown": markdown, "outdir": outdir,
                   "transcript": transcript, "speakers": speakers,
                   "speaker_map": speaker_map, "roster": roster_sorted})
    except Exception as e:  # noqa: BLE001
        job["status"] = "error"
        job["error"] = str(e)
        emit(jid, {"type": "error", "error": str(e)})
        # Don't leave a half-baked output folder lying around.
        od = job.get("outdir")
        if od and os.path.isdir(od) and not is_real_result(od):
            shutil.rmtree(od, ignore_errors=True)


def run_stream(jid, cmd, env=None, on_line=None):
    """Run a command, streaming stderr/stdout lines to the job log.

    on_line(line) is called per output line (used to parse progress)."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1, env=env)
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            emit(jid, {"type": "log", "line": line})
            if on_line:
                try:
                    on_line(line)
                except Exception:
                    pass
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {os.path.basename(cmd[0])}")


def wav_duration(wav):
    """Length of a WAV file in seconds (0 if unreadable)."""
    try:
        import wave
        with wave.open(wav, "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 0.0


def whisperx_json_to_text(jpath):
    """Turn WhisperX JSON into a transcript, with SPEAKER_xx prefixes when diarized."""
    with open(jpath, "r", encoding="utf-8") as f:
        data = json.load(f)
    blocks, cur, parts = [], "__start__", []
    for s in data.get("segments", []):
        t = (s.get("text") or "").strip()
        if not t:
            continue
        spk = s.get("speaker") or ""
        if spk != cur:
            if parts:
                blocks.append((cur if cur != "__start__" else "", " ".join(parts)))
            cur, parts = spk, [t]
        else:
            parts.append(t)
    if parts:
        blocks.append((cur if cur != "__start__" else "", " ".join(parts)))
    return "\n".join(f"{spk}: {txt}" if spk else txt for spk, txt in blocks).strip()


def whispercpp_json_to_segments(jpath):
    """whisper.cpp -oj JSON -> WhisperX-shaped segments (start/end in seconds).

    Lets the OCR speaker-naming step (which reads audio.json) work unchanged."""
    with open(jpath, "r", encoding="utf-8") as f:
        data = json.load(f)
    segs = []
    for s in data.get("transcription", []):
        txt = (s.get("text") or "").strip()
        if not txt:
            continue
        off = s.get("offsets", {}) or {}
        segs.append({"start": off.get("from", 0) / 1000.0,
                     "end": off.get("to", 0) / 1000.0, "text": txt})
    return segs


def segments_to_text(segs):
    """Plain transcript from segments (no speaker labels; OCR adds names later)."""
    return "\n".join(s["text"].strip() for s in segs if s.get("text")).strip()


def transcribe(jid, whisper, wav, outdir, language, diarize=False):
    out_prefix = os.path.join(outdir, "transcript")
    if whisper["type"] == "whisperx":
        token = hf_token()
        base = [whisper["bin"], wav, "--model", whisper["model"],
                "--output_dir", outdir, "--output_format", "json",
                "--device", "cpu", "--compute_type", "int8"]
        if language and language != "auto":
            base += ["--language", language]
        # WhisperX shells out to ffmpeg to decode audio — make sure ours is on PATH.
        env = dict(os.environ)
        ff = find_ffmpeg()
        if ff:
            env["PATH"] = os.path.dirname(ff) + os.pathsep + env.get("PATH", "")
        if token:
            env["HF_TOKEN"] = token
        want_diar = bool(diarize and token)
        diar_args = ["--diarize", "--diarize_model", DIARIZE_MODEL, "--hf_token", token]
        # Progress: WhisperX prints "[start --> end] text" per segment; end/duration ≈ progress.
        dur = wav_duration(wav)
        seen = {"max": 0.0}
        ts_re = re.compile(r"-->\s*([0-9]+\.?[0-9]*)")

        def on_line(line):
            m = ts_re.search(line)
            if m and dur:
                end = float(m.group(1))
                if end > seen["max"]:
                    seen["max"] = end
                    emit(jid, {"type": "progress", "stage": "transcribe",
                               "pct": max(0.0, min(0.99, end / dur))})
        try:
            run_stream(jid, base + (diar_args if want_diar else []), env=env, on_line=on_line)
        except RuntimeError:
            if not want_diar:
                raise
            # Diarization failed (e.g. token lacks accepted model terms) — still
            # deliver a transcript without speaker labels rather than failing.
            emit(jid, {"type": "log", "line": "⚠ Diarization failed — check the HuggingFace token and that you accepted the pyannote model terms. Continuing without speaker labels."})
            run_stream(jid, base, env=env, on_line=on_line)
        jpath = os.path.join(outdir, os.path.splitext(os.path.basename(wav))[0] + ".json")
        if not os.path.exists(jpath):
            raise RuntimeError("WhisperX produced no JSON output")
        text = whisperx_json_to_text(jpath)
        with open(out_prefix + ".txt", "w", encoding="utf-8") as f:
            f.write(text + "\n")
        return out_prefix + ".txt"
    if whisper["type"] == "cpp":
        # Fast path: whisper.cpp on Metal. Emit JSON so we can (a) build the
        # transcript and (b) hand timestamped segments to the OCR speaker-namer.
        cpp_prefix = os.path.join(outdir, "whispercpp")
        lang = language if (language and language != "auto") else "auto"
        cmd = [whisper["bin"], "-m", whisper["model"], "-f", wav,
               "-l", lang, "-t", "8", "-oj", "-of", cpp_prefix]
        dur = wav_duration(wav)
        seen = {"max": 0.0}
        # whisper.cpp prints "[00:00:11.000 --> 00:00:14.000]  text" per segment.
        ts_re = re.compile(r"-->\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})")

        def on_line(line):
            m = ts_re.search(line)
            if m and dur:
                h, mn, s, ms = (int(g) for g in m.groups())
                end = h * 3600 + mn * 60 + s + ms / 1000.0
                if end > seen["max"]:
                    seen["max"] = end
                    emit(jid, {"type": "progress", "stage": "transcribe",
                               "pct": max(0.0, min(0.99, end / dur))})

        run_stream(jid, cmd, on_line=on_line)
        cpp_json = cpp_prefix + ".json"
        if not os.path.exists(cpp_json):
            raise RuntimeError("whisper.cpp produced no JSON output")
        segs = whispercpp_json_to_segments(cpp_json)
        # Write a WhisperX-shaped audio.json so OCR speaker-naming works as-is.
        with open(os.path.join(outdir, "audio.json"), "w", encoding="utf-8") as f:
            json.dump({"segments": segs}, f, ensure_ascii=False)
        with open(out_prefix + ".txt", "w", encoding="utf-8") as f:
            f.write(segments_to_text(segs) + "\n")
        return out_prefix + ".txt"
    else:  # openai-whisper
        cmd = [whisper["bin"], wav, "--language",
               ("auto" if language == "auto" else language),
               "--output_format", "txt", "--output_dir", outdir, "--model", "small"]
        run_stream(jid, cmd)
        produced = os.path.join(outdir, os.path.splitext(os.path.basename(wav))[0] + ".txt")
        if os.path.exists(produced) and produced != out_prefix + ".txt":
            shutil.move(produced, out_prefix + ".txt")
        return out_prefix + ".txt"


def summarize_stream(jid, transcript, model, attendees=""):
    prompt = build_prompt(transcript, attendees)
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {"num_ctx": 16384, "temperature": 0.2},
    }
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    chunks = []
    with urllib.request.urlopen(req, timeout=1800) as resp:
        for raw in resp:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw.decode())
            except Exception:
                continue
            piece = obj.get("response", "")
            if piece:
                chunks.append(piece)
                emit(jid, {"type": "partial", "text": piece})
            if obj.get("done"):
                break
    return "".join(chunks).strip()


def summarize_once(transcript, model, attendees=""):
    """Non-streaming summarize — used when regenerating after a name edit."""
    payload = {"model": model, "prompt": build_prompt(transcript, attendees),
               "stream": False, "options": {"num_ctx": 16384, "temperature": 0.2}}
    req = urllib.request.Request(f"{OLLAMA_URL}/api/generate",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as resp:
        return json.loads(resp.read().decode()).get("response", "").strip()


# ----------------------------------------------------------------------------
# Offline styled MoM: local model -> structured JSON -> the exact email template.
# The styling is 100% deterministic (no model), so it always renders pixel-perfect;
# only the CONTENT comes from the local model. Zero tokens, fully offline.
# ----------------------------------------------------------------------------
MOM_JSON_INSTRUCTIONS = """You are a precise meeting-notes assistant for the efood / DH Pay teams.
The transcript below may be in Greek and lines may be prefixed with the speaker's name.
Produce a Minutes-of-Meeting as a SINGLE JSON object (no prose, no markdown fences).

Write ALL values in clear, professional ENGLISH (translate any Greek).
NEVER invent facts, names, numbers, dates or decisions — use only what is in the transcript.
Owners of action items must be a person named in the transcript or the attendee list;
if the owner is unclear write "⚠️ owner not stated" — never guess a name.
Preserve the efood/Foody (local) vs DH/Central (global) ownership nuance.

JSON schema (use exactly these keys; omit nothing — use [] or "" when empty):
{
  "title": "short meeting title",
  "subtitle": "one-line subtitle, e.g. 'X - Minutes of Meeting'",
  "attendees": ["Full Name", ...],
  "latest_status": [ {"headline": "short bold lead", "detail": "1-2 sentences"} ],
  "agenda": ["agenda point", ...],
  "discussion": [ {"topic": "topic name", "summary": "what was discussed", "decision": "decision if any, else ''"} ],
  "action_items": [ {"text": "the task", "assignee": "name or team or '⚠️ owner not stated'", "status": "done|in_progress|blocked|pending", "note": "optional context or blocker, else ''"} ]
}
Keep it concise and skimmable. Base 'latest_status' on the newest blockers/updates (may be []).
"""


def best_mom_model(models):
    """Pick the highest-quality installed model for offline MoM drafting.
    Prefers a known-good ranking, else the qwen2.5 with the largest param count,
    else the first installed model."""
    prefer = ["qwen2.5:32b", "qwen2.5:14b", "qwen2.5:7b"]
    for p in prefer:
        if p in models:
            return p

    def size_key(m):
        mm = re.search(r":(\d+)b", m.lower())
        return int(mm.group(1)) if mm else 0
    ranked = sorted(models, key=size_key, reverse=True)
    return ranked[0] if ranked else "qwen2.5:7b"


def build_json_prompt(transcript, attendees_text=""):
    names = [n.strip() for part in (attendees_text or "").replace("\n", ",").split(",")
             for n in [part] if n.strip()]
    block = ""
    if names:
        block = ("\nAttendees (the ONLY names allowed as owners): " + ", ".join(names) + "\n")
    return MOM_JSON_INSTRUCTIONS + block + "\nTranscript:\n" + (transcript or "")


def ollama_json_mom(transcript, model, attendees=""):
    """Ask the local model for the MoM as strict JSON (Ollama format=json)."""
    # Big context so a full ~40-min meeting isn't truncated (Greek tokenizes
    # less efficiently). Fits easily in 24 GB for a 7B/14B model.
    payload = {"model": model, "prompt": build_json_prompt(transcript, attendees),
               "stream": False, "format": "json",
               "options": {"num_ctx": 32768, "temperature": 0.1}}
    req = urllib.request.Request(f"{OLLAMA_URL}/api/generate",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as resp:
        raw = json.loads(resp.read().decode()).get("response", "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Salvage the outermost {...} if the model wrapped it in stray text.
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            return json.loads(m.group(0))
        raise


# Status card palette — matches the reference email exactly.
_STATUS = {
    "done":        dict(emoji="✅", bg="rgb(240,253,244)", bd="rgb(187,247,208)",
                        title="rgb(22,101,52)", strike=True, sub="rgb(21,128,61)",
                        badge_bg="rgb(220,252,231)", badge_fg="rgb(22,163,74)",
                        badge_bd="rgb(134,239,172)", label="Done"),
    "in_progress": dict(emoji="\U0001f504", bg="rgb(248,250,252)", bd="rgb(226,232,240)",
                        title="rgb(15,23,42)", strike=False, sub="rgb(100,116,139)",
                        badge_bg="rgb(255,251,235)", badge_fg="rgb(217,119,6)",
                        badge_bd="rgb(252,211,77)", label="In Progress"),
    "blocked":     dict(emoji="\U0001f6d1", bg="rgb(254,242,242)", bd="rgb(254,202,202)",
                        title="rgb(153,27,27)", strike=False, sub="rgb(185,28,28)",
                        badge_bg="rgb(254,226,226)", badge_fg="rgb(239,68,68)",
                        badge_bd="rgb(252,165,165)", label="Blocked"),
    "pending":     dict(emoji="⬜", bg="rgb(248,250,252)", bd="rgb(226,232,240)",
                        title="rgb(15,23,42)", strike=False, sub="rgb(100,116,139)",
                        badge_bg="", badge_fg="rgb(100,116,139)",
                        badge_bd="rgb(203,213,225)", label="Pending"),
}


def mom_json_to_email_html(d, greeting=""):
    """Render the MoM JSON into the exact styled email HTML (inline styles only,
    so it survives a paste into Gmail). Deterministic — no model involved."""
    e = html.escape
    out = ['<div style="font-family:Inter,Helvetica,Arial,sans-serif;color:rgb(51,65,85)">']
    if greeting:
        for para in [p for p in greeting.split("\n") if p.strip()]:
            out.append(f'<p style="color:rgb(16,16,16);font-size:14px;margin:0 0 12px">{e(para)}</p>')
    # Title + subtitle
    if d.get("title"):
        out.append(f'<h1 style="margin:0;color:rgb(37,99,235);font-size:26px;font-weight:bold;letter-spacing:-0.5px">{e(d["title"])}</h1>')
    if d.get("subtitle"):
        out.append(f'<p style="margin:6px 0 0;color:rgb(100,116,139);font-size:15px">{e(d["subtitle"])}</p>')
    # Attendees pills
    att = d.get("attendees") or []
    if att:
        out.append('<p style="margin:18px 0 8px;color:rgb(15,23,42);font-size:18px">Attendees</p>')
        out.append('<div style="font-size:14px;line-height:2.2;margin-bottom:28px">')
        for a in att:
            out.append(f'<span style="background-color:rgb(239,246,255);color:rgb(29,78,216);border:1px solid rgb(191,219,254);padding:6px 12px;border-radius:16px;margin:0 6px 6px 0;display:inline-block">{e(a)}</span>')
        out.append('</div>')
    # Latest status (amber box)
    ls = d.get("latest_status") or []
    if ls:
        out.append('<h2 style="font-size:18px;color:rgb(180,83,9);margin:0 0 12px"><span style="font-size:20px;margin-right:8px">⚠️</span>Latest Status Updates</h2>')
        out.append('<div style="background-color:rgb(255,251,235);border:1px solid rgb(253,230,138);padding:20px;border-radius:10px;margin-bottom:32px">')
        out.append('<ul style="color:rgb(146,64,14);font-size:14px;line-height:1.6;margin:0;padding-left:20px">')
        for it in ls:
            head = e(it.get("headline", "")); det = e(it.get("detail", ""))
            lead = f'<strong>{head}:</strong> ' if head else ""
            out.append(f'<li style="margin-bottom:8px">{lead}{det}</li>')
        out.append('</ul></div>')
    # Agenda
    ag = d.get("agenda") or []
    if ag:
        out.append('<h2 style="font-size:18px;color:rgb(15,23,42);border-left:4px solid rgb(59,130,246);padding-left:12px;margin:0 0 15px">Agenda</h2>')
        out.append('<ol style="color:rgb(71,85,105);font-size:15px;line-height:1.7;padding-left:20px;margin:0 0 32px">')
        for a in ag:
            out.append(f'<li style="margin-bottom:6px">{e(a)}</li>')
        out.append('</ol>')
    # Discussion points (purple cards)
    disc = d.get("discussion") or []
    if disc:
        out.append('<h2 style="font-size:18px;color:rgb(15,23,42);border-left:4px solid rgb(59,130,246);padding-left:12px;margin:0 0 20px">Discussion Points</h2>')
        for i, dp in enumerate(disc, 1):
            out.append(f'<h3 style="margin:0 0 6px;font-size:16px;color:rgb(76,29,149)">{i}. {e(dp.get("topic",""))}</h3>')
            out.append('<div style="border-left:3px solid rgb(139,92,246);background-color:rgb(250,245,255);padding:15px 18px;margin-bottom:15px;border-radius:0 8px 8px 0">')
            if dp.get("summary"):
                out.append(f'<p style="margin:0;color:rgb(71,85,105);line-height:1.6;font-size:14px">{e(dp["summary"])}</p>')
            if dp.get("decision"):
                out.append(f'<p style="margin:8px 0 0;color:rgb(71,85,105);line-height:1.6;font-size:14px"><strong>Decision:</strong> {e(dp["decision"])}</p>')
            out.append('</div>')
    # Action items (status cards)
    ai = d.get("action_items") or []
    if ai:
        out.append('<h2 style="font-size:18px;color:rgb(15,23,42);border-left:4px solid rgb(59,130,246);padding-left:12px;margin:24px 0 20px">Action Items</h2>')
        for it in ai:
            s = _STATUS.get((it.get("status") or "pending").lower().replace(" ", "_"), _STATUS["pending"])
            deco = ";text-decoration:line-through" if s["strike"] else ""
            out.append(f'<table width="100%" cellpadding="12" cellspacing="0" border="0" style="margin-bottom:12px;background-color:{s["bg"]};border:1px solid {s["bd"]};border-radius:8px"><tbody><tr>')
            out.append(f'<td width="30" valign="top" style="font-size:18px">{s["emoji"]}</td><td valign="top">')
            out.append(f'<div style="font-size:15px;font-weight:bold;color:{s["title"]};margin-bottom:4px{deco}">{e(it.get("text",""))}</div>')
            if it.get("assignee"):
                out.append(f'<div style="font-size:13px;color:{s["sub"]}">Assignee: <span style="color:rgb(99,102,241)">{e(it["assignee"])}</span></div>')
            if it.get("note"):
                out.append(f'<div style="font-size:13px;color:rgb(148,163,184);margin-top:5px;font-style:italic">{e(it["note"])}</div>')
            badge_bg = f'background-color:{s["badge_bg"]};' if s["badge_bg"] else ""
            out.append(f'</td><td width="100" valign="top" align="right"><span style="{badge_bg}color:{s["badge_fg"]};font-size:12px;font-weight:600;padding:4px 10px;border-radius:12px;border:1px solid {s["badge_bd"]}">{s["label"]}</span></td>')
            out.append('</tr></tbody></table>')
    out.append('<p style="color:rgb(51,65,85);font-size:14px;margin:20px 0 0">Thank you,</p>')
    out.append('</div>')
    return "\n".join(out)


def is_video(path):
    return os.path.splitext(path)[1].lower() in VIDEO_EXTS


def is_url(s):
    return s.strip().lower().startswith(("http://", "https://"))


def speaker_labels(transcript):
    labels = set()
    for line in transcript.split("\n"):
        if ":" in line:
            lab = line.split(":", 1)[0].strip()
            if lab.startswith("SPEAKER_"):
                labels.add(lab)
    return sorted(labels)


def apply_speaker_map(transcript, mapping):
    """Replace 'SPEAKER_xx:' line prefixes with the mapped real name."""
    out = []
    for line in transcript.split("\n"):
        if ":" in line:
            lab, rest = line.split(":", 1)
            if lab.strip() in mapping and mapping[lab.strip()]:
                line = mapping[lab.strip()] + ":" + rest
        out.append(line)
    return "\n".join(out)


_OCR_PY_CACHE = {}


def ocrmac_python():
    """Find a Python interpreter that can import `ocrmac` (Apple Vision OCR).

    OCR needs `ocrmac`, NOT WhisperX — so this is decoupled from the WhisperX venv:
    we probe the WhisperX venv python first (setup.sh installs ocrmac there), then
    the system python3 / this interpreter. Returns (python_path, reason). On success
    reason == "ok"; on failure python_path is None and reason is an install hint.
    Memoized (import loads the Vision framework, ~1 s)."""
    if "result" in _OCR_PY_CACHE:
        return _OCR_PY_CACHE["result"]
    result = (None, "ocrmac not installed in any Python — install with: "
                    "pip3 install ocrmac  (or re-run ./setup.sh)")
    tried = []
    for py in (VENV_PY, shutil.which("python3"), sys.executable):
        if not py or py in tried or not os.path.exists(py):
            continue
        tried.append(py)
        try:
            r = subprocess.run([py, "-c", "import ocrmac"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=60)
        except Exception:
            continue
        if r.returncode == 0:
            result = (py, "ok")
            break
    _OCR_PY_CACHE["result"] = result
    return result


def ocr_name_transcript(video, audio_json, ffmpeg, step=4.0, jid=None, roster="",
                        ocr_python=None):
    """Token-free OCR speaker naming: label each transcript segment by the on-screen
    active-speaker name. Runs the OCR module (ocr_speakers.py) via whichever Python
    has ocrmac (Apple Vision) — see ocrmac_python().

    `roster` is the optional attendee list — passed through to lock OCR onto real
    names (kills doc/UI false positives in Google Meet screen-shares).

    Returns (transcript_text, roster_dict, speakers_list). Every failure/skip mode
    emits an explicit log line so naming never fails silently; it always degrades
    gracefully (the caller keeps the segmented transcript). Streams "OCR i/n"."""
    def log(msg):
        if jid:
            emit(jid, {"type": "log", "line": msg})

    # --- explicit, distinct reasons for skipping (never silent) ---
    if not os.path.exists(OCR_SCRIPT):
        log(f"⚠ Speaker naming skipped: OCR module missing ({OCR_SCRIPT}).")
        return "", {}, []
    if not os.path.exists(audio_json):
        log(f"⚠ Speaker naming skipped: timestamped segments missing "
            f"({os.path.basename(audio_json)}).")
        return "", {}, []
    py = ocr_python
    if not py:
        py, reason = ocrmac_python()
        if not py:
            log(f"⚠ Speaker naming skipped: {reason}")
            return "", {}, []

    cmd = [py, OCR_SCRIPT, video, audio_json, "--name-transcript", "--step", str(step)]
    if ffmpeg:
        cmd += ["--ffmpeg", ffmpeg]
    if roster and roster.strip():
        cmd += ["--roster", roster]
    err_lines = []
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, bufsize=1)
        ocr_re = re.compile(r"OCR (\d+)/(\d+)")

        def pump():
            for line in proc.stderr:
                err_lines.append(line)
                m = ocr_re.search(line)
                if m and jid and int(m.group(2)):
                    emit(jid, {"type": "progress", "stage": "names",
                               "pct": int(m.group(1)) / int(m.group(2))})
        t = threading.Thread(target=pump, daemon=True)
        t.start()
        out = proc.stdout.read()
        proc.wait(timeout=1800)
        t.join(timeout=1)
    except Exception as e:  # noqa: BLE001
        log(f"⚠ Speaker naming failed to run ({e.__class__.__name__}: {e}). "
            f"Keeping the transcript without names.")
        return "", {}, []

    if proc.returncode != 0:
        tail = " ".join(l.strip() for l in err_lines[-3:] if l.strip())
        log(f"⚠ Speaker naming exited with code {proc.returncode}"
            + (f" — {tail}" if tail else "") + ". Keeping the transcript without names.")
        return "", {}, []
    lines = [l for l in (out or "").strip().splitlines() if l.strip()]
    if not lines:
        log("⚠ Speaker naming produced no output. Keeping the transcript without names.")
        return "", {}, []
    try:
        data = json.loads(lines[-1])
    except Exception as e:  # noqa: BLE001
        log(f"⚠ Could not parse speaker-naming output ({e}). "
            f"Keeping the transcript without names.")
        return "", {}, []
    transcript = data.get("transcript", "")
    roster_d = data.get("roster", {})
    speakers = data.get("speakers", [])
    if not speakers:
        log("🗣️ Speaker naming ran but matched 0 on-screen names — keeping the "
            "segmented transcript. Tip: add an attendee list to lock onto names, "
            "or tune the MOM_OCR_* env gates for an unusual meeting layout.")
    return transcript, roster_d, speakers


# ----------------------------------------------------------------------------
# HTTP handler
# ----------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # quiet

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        if path == "/":
            self._send(200, INDEX_HTML, "text/html; charset=utf-8")
        elif path == "/health":
            self._send(200, json.dumps(detect_all()))
        elif path == "/events":
            self.handle_events(qs.get("job", [""])[0])
        elif path == "/download":
            self.handle_download(qs.get("job", [""])[0])
        elif path == "/job":
            self.handle_job(qs.get("job", [""])[0])
        elif path == "/jobs":
            self.handle_jobs()
        elif path == "/result_file":
            self.handle_result_file(qs.get("dir", [""])[0])
        elif path == "/gemini_prompt":
            self.handle_gemini_prompt(qs.get("job", [""])[0])
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/upload":
            self.handle_upload(urllib.parse.parse_qs(parsed.query))
        elif parsed.path == "/local":
            self.handle_local()
        elif parsed.path == "/styled_mom":
            self.handle_styled_mom(urllib.parse.parse_qs(parsed.query))
        elif parsed.path == "/open_folder":
            self.handle_open_folder()
        elif parsed.path == "/fetch":
            self.handle_fetch()
        elif parsed.path == "/rename":
            self.handle_rename(urllib.parse.parse_qs(parsed.query))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def handle_local(self):
        """Process a file already on this Mac — no upload copy. The user pastes a
        local path (e.g. ~/Downloads/meeting.mp4). We read it in place, so the
        original is never moved or deleted."""
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode() or "{}")
        raw = (body.get("path") or "").strip()
        # Tolerate quotes/file:// and the drag-into-Terminal escaping.
        raw = raw.strip('"').strip("'")
        if raw.startswith("file://"):
            raw = urllib.parse.unquote(raw[7:])
        raw = raw.replace("\\ ", " ").replace("\\~", "~")
        path = os.path.expanduser(raw)
        if not path or not os.path.isfile(path):
            self._send(400, json.dumps({"error": f"No file found at: {raw or '(empty)'}"}))
            return
        language = body.get("language", "el")
        model = body.get("model", "qwen2.5:7b")
        attendees = body.get("attendees", "")
        jid = new_job(os.path.basename(path))
        t = threading.Thread(target=run_pipeline,
                             args=(jid, path, language, model, attendees), daemon=True)
        t.start()
        self._send(200, json.dumps({"job": jid}))

    def handle_open_folder(self):
        """Reveal an output folder in Finder. Restricted to folders under
        OUTPUT_BASE so the button can't open arbitrary paths."""
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode() or "{}") if length else {}
        d = os.path.realpath(os.path.expanduser(body.get("dir", "")))
        base = os.path.realpath(OUTPUT_BASE)
        if not (d == base or d.startswith(base + os.sep)) or not os.path.isdir(d):
            self._send(400, json.dumps({"error": "not an output folder"}))
            return
        try:
            subprocess.Popen(["open", d])
            self._send(200, json.dumps({"ok": True}))
        except Exception as ex:  # noqa: BLE001
            self._send(500, json.dumps({"error": str(ex)}))

    def handle_styled_mom(self, qs):
        """Offline styled MoM: local model -> JSON -> the exact email template.
        Zero tokens. Works on any job that already has a transcript."""
        jid = qs.get("job", [""])[0]
        with JOBS_LOCK:
            job = JOBS.get(jid)
        if not job or not (job.get("transcript") or "").strip():
            self._send(404, json.dumps({"error": "no transcript for this job yet"}))
            return
        models = ollama_models()
        if not models:
            self._send(400, json.dumps({"error": "No local model found. Install one (e.g. run: ollama pull qwen2.5:7b)."}))
            return
        # Prefer the job's chosen model; else the best installed for MoM quality.
        jm = job.get("model", "")
        model = jm if jm in models else best_mom_model(models)
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode() or "{}") if length else {}
        greeting = body.get("greeting", "")
        try:
            data = ollama_json_mom(job["transcript"], model, job.get("attendees", ""))
            # Attendees are user-provided ground truth — use them for the pills
            # deterministically rather than trusting the model to echo all names.
            provided = [n.strip() for part in (job.get("attendees", "") or "").replace("\n", ",").split(",")
                        for n in [part] if n.strip()]
            if provided:
                data["attendees"] = provided
            htmlout = mom_json_to_email_html(data, greeting=greeting)
        except Exception as ex:  # noqa: BLE001
            self._send(500, json.dumps({"error": f"Local MoM failed: {ex}"}))
            return
        job["styled_html"] = htmlout
        job["mom_json"] = data
        if job.get("outdir"):
            try:
                with open(os.path.join(job["outdir"], "MoM.html"), "w", encoding="utf-8") as f:
                    f.write(htmlout + "\n")
            except OSError:
                pass
        self._send(200, json.dumps({"html": htmlout, "model": model}))

    def handle_gemini_prompt(self, jid):
        """Return the reusable Gemini styling prompt with this job's transcript
        embedded, so the UI's 'Copy Gemini prompt' button gives a paste-ready blob."""
        transcript = ""
        with JOBS_LOCK:
            job = JOBS.get(jid)
        if job:
            transcript = job.get("transcript") or ""
        self._send(200, json.dumps({"prompt": gemini_prompt(transcript)}))

    def handle_fetch(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode() or "{}")
        url = (body.get("url") or "").strip()
        if not (HAS_YOUTUBE and youtube_dl.available()):
            self._send(400, json.dumps({"error": "Link/YouTube support isn't enabled in this build."}))
            return
        if not is_url(url):
            self._send(400, json.dumps({"error": "Please paste a valid http(s) link."}))
            return
        language = body.get("language", "auto")
        model = body.get("model", "qwen2.5:7b")
        attendees = body.get("attendees", "")
        jid = new_job(url)
        t = threading.Thread(target=run_pipeline,
                             args=(jid, url, language, model, attendees, True), daemon=True)
        t.start()
        self._send(200, json.dumps({"job": jid}))

    def handle_rename(self, qs):
        jid = qs.get("job", [""])[0]
        with JOBS_LOCK:
            job = JOBS.get(jid)
        if not job or not job.get("raw_transcript"):
            self._send(404, json.dumps({"error": "no speaker-labelled transcript for this job"}))
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode() or "{}")
        mapping = body.get("mapping", {})
        transcript = apply_speaker_map(job["raw_transcript"], mapping)
        job["transcript"] = transcript
        # The corrected transcript is the primary product — always persist it.
        if job.get("outdir"):
            with open(os.path.join(job["outdir"], "transcript.txt"), "w", encoding="utf-8") as f:
                f.write(transcript + "\n")
        # Re-draft the local MoM only if one was generated / Ollama is available.
        markdown = ""
        model = job.get("model", "")
        want_mom = bool(model) and model.lower() not in ("none", "skip", "") and ollama_models()
        if want_mom:
            try:
                markdown = summarize_once(transcript, model, job.get("attendees", ""))
            except Exception as e:  # noqa: BLE001
                self._send(500, json.dumps({"error": str(e)}))
                return
            job["markdown"] = markdown
            if job.get("outdir"):
                with open(os.path.join(job["outdir"], "MoM.md"), "w", encoding="utf-8") as f:
                    f.write(markdown + "\n")
        self._send(200, json.dumps({"markdown": markdown, "transcript": transcript}))

    def handle_upload(self, qs):
        filename = urllib.parse.unquote(self.headers.get("X-Filename", "recording"))
        language = self.headers.get("X-Language", "el")
        model = self.headers.get("X-Model", "qwen2.5:7b")
        attendees = urllib.parse.unquote(self.headers.get("X-Attendees", ""))
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            self._send(400, json.dumps({"error": "empty upload"}))
            return
        tmpdir = os.path.join(OUTPUT_BASE, ".uploads")
        os.makedirs(tmpdir, exist_ok=True)
        dst = os.path.join(tmpdir, uuid.uuid4().hex + "_" + os.path.basename(filename))
        remaining = length
        with open(dst, "wb") as f:
            while remaining > 0:
                chunk = self.rfile.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                f.write(chunk)
                remaining -= len(chunk)
        jid = new_job(filename)
        t = threading.Thread(target=run_pipeline, args=(jid, dst, language, model, attendees), daemon=True)
        t.start()
        self._send(200, json.dumps({"job": jid}))

    def handle_events(self, jid):
        with JOBS_LOCK:
            exists = jid in JOBS
        if not exists:
            self._send(404, json.dumps({"error": "no such job"}))
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        idx = 0
        try:
            while True:
                with JOBS_LOCK:
                    job = JOBS.get(jid)
                    events = job["events"][idx:] if job else []
                    status = job["status"] if job else "error"
                for ev in events:
                    self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode())
                    self.wfile.flush()
                    idx += 1
                if status in ("done", "error") and idx >= len(job["events"]):
                    break
                time.sleep(0.25)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def handle_download(self, jid):
        with JOBS_LOCK:
            job = JOBS.get(jid)
        if not job or not job.get("markdown"):
            self._send(404, json.dumps({"error": "no result"}))
            return
        body = job["markdown"].encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/markdown; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="MoM.md"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_job(self, jid):
        """Current state of a job — used to resume after the tab was closed."""
        with JOBS_LOCK:
            job = JOBS.get(jid)
        if not job:
            self._send(404, json.dumps({"error": "not found"}))
            return
        self._send(200, json.dumps({
            "status": job.get("status"), "filename": job.get("filename"),
            "markdown": job.get("markdown"), "transcript": job.get("transcript"),
            "speakers": job.get("speakers", []), "speaker_map": job.get("speaker_map", {}),
            "roster": job.get("roster", []), "outdir": job.get("outdir"),
            "error": job.get("error"),
        }))

    def handle_jobs(self):
        """Recent finished results, read from disk (survives restarts)."""
        items = []
        try:
            for name in os.listdir(OUTPUT_BASE):
                if name.startswith("."):
                    continue
                d = os.path.join(OUTPUT_BASE, name)
                # Prefer the transcript's time, fall back to the MoM's.
                marker = next((os.path.join(d, f) for f in ("transcript.txt", "MoM.md")
                               if os.path.isfile(os.path.join(d, f))), None)
                if marker:
                    items.append({"dir": name, "label": pretty_label(name),
                                  "when": os.path.getmtime(marker)})
        except FileNotFoundError:
            pass
        items.sort(key=lambda x: -x["when"])
        self._send(200, json.dumps({"jobs": items[:20]}))

    def handle_result_file(self, dirname):
        """Re-open a finished result from disk by folder name."""
        safe = os.path.basename(dirname)  # no path traversal
        d = os.path.join(OUTPUT_BASE, safe)
        if not safe or not is_real_result(d):
            self._send(404, json.dumps({"error": "not found"}))
            return
        mom = os.path.join(d, "MoM.md")
        md = ""
        if os.path.isfile(mom):
            with open(mom, "r", encoding="utf-8") as f:
                md = f.read()
        tpath = os.path.join(d, "transcript.txt")
        tr = ""
        if os.path.isfile(tpath):
            with open(tpath, "r", encoding="utf-8") as f:
                tr = f.read()
        self._send(200, json.dumps({"markdown": md, "transcript": tr, "outdir": d}))


# ----------------------------------------------------------------------------
# Frontend (static; pulls config from /health). No external/CDN dependencies.
# ----------------------------------------------------------------------------
INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MoM Generator</title>
<style>
  /* Light-first "document workspace" theme. efood red for primary emphasis only. */
  :root {
    --bg:#f1f5f9; --panel:#ffffff; --panel2:#f8fafc; --border:#e2e8f0; --border-strong:#cbd5e1;
    --text:#0f172a; --muted:#64748b;
    --accent:#EF000D; --accent-dark:#c40009; --accent-tint:#fef2f2; --accent2:#2563eb;
    --green:#16a34a; --green-tint:#f0fdf4; --green-border:#bbf7d0;
    --yellow:#d97706; --amber-tint:#fffbeb; --amber-border:#fde68a;
    --red:#ef4444;
  }
  * { box-sizing:border-box; }
  body { margin:0; font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Inter,sans-serif;
         background:var(--bg); color:var(--text); }
  header { padding:16px 28px; border-bottom:1px solid var(--border); background:var(--panel);
           display:flex; align-items:center; gap:14px; }
  header .logo { width:38px;height:38px;border-radius:9px;background:var(--accent);color:#fff;
                 display:flex;align-items:center;justify-content:center; }
  header h1 { font-size:17px; margin:0; font-weight:500; letter-spacing:-.2px; }
  header p { margin:2px 0 0; color:var(--muted); font-size:13px; }
  /* inline SVG icons (offline sprite) — inherit text color + size */
  svg.ic { width:1.05em; height:1.05em; flex-shrink:0; vertical-align:-.15em; }
  .badge { font-size:11px; font-weight:500; padding:3px 9px; border-radius:999px;
           background:var(--accent-tint); color:var(--accent-dark); }
  .status-pill { display:inline-flex; align-items:center; gap:5px; font-size:12px; font-weight:500;
                 padding:5px 11px; border-radius:999px; background:var(--green-tint); color:#166534; }
  .wrap { max-width:860px; margin:0 auto; padding:24px 28px 96px; }
  .card { background:var(--panel); border:1px solid var(--border); border-radius:10px; padding:22px; margin-bottom:18px;
          box-shadow:0 1px 2px rgba(15,23,42,.04), 0 1px 3px rgba(15,23,42,.06); }
  .row { display:flex; gap:16px; flex-wrap:wrap; align-items:center; }
  label { font-size:13px; color:var(--muted); display:block; margin-bottom:6px; font-weight:500; }
  input[type=text], select, textarea { background:var(--panel); color:var(--text); border:1px solid var(--border-strong);
           border-radius:8px; padding:10px 12px; font-size:14px; font-family:inherit; transition:.12s; }
  input[type=text]:focus, select:focus, textarea:focus { outline:none; border-color:var(--accent);
           box-shadow:0 0 0 3px var(--accent-tint); }
  select { min-width:170px; }
  textarea { width:100%; resize:vertical; }
  label .hint { opacity:.85; font-weight:400; }
  /* numbered step blocks */
  .step-block { padding-bottom:20px; border-bottom:1px solid var(--border); margin-bottom:20px; }
  .step-block:last-child { border-bottom:0; padding-bottom:0; margin-bottom:0; }
  .step-head { display:flex; align-items:center; gap:10px; font-weight:500; font-size:15px; margin-bottom:14px; }
  .step-num { width:24px;height:24px;border-radius:50%;background:var(--accent);color:#fff;font-size:13px;
              font-weight:500;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
  .or { color:var(--muted); font-size:11.5px; text-align:center; margin:12px 0; letter-spacing:.08em; text-transform:uppercase; }
  #drop { border:2px dashed var(--border-strong); border-radius:10px; padding:26px 20px; text-align:center;
          cursor:pointer; transition:.15s; background:var(--panel2); }
  #drop.hover { border-color:var(--accent); background:var(--accent-tint); }
  #drop .big { font-size:30px; }
  #drop .sub { color:var(--muted); font-size:13px; margin-top:6px; }
  /* selected-file row */
  #fileRow { display:flex; align-items:center; gap:12px; background:var(--panel2); border:1px solid var(--border);
             border-radius:8px; padding:12px 14px; margin-top:12px; }
  #fileRow .fi-ic { font-size:20px; }
  #fileRow .fi-name { font-weight:500; font-size:14px; }
  #fileRow .fi-meta { color:var(--muted); font-size:12.5px; }
  .link-btn { background:none; border:0; color:var(--accent); font-size:13px; font-weight:500; cursor:pointer; padding:4px 6px; }
  .link-btn:hover { text-decoration:underline; }
  .reason { color:var(--muted); font-size:13px; }
  button.primary { background:var(--accent); color:#fff; border:0; border-radius:8px; padding:11px 20px;
                   font-size:14px; font-weight:500; cursor:pointer; transition:.12s;
                   display:inline-flex; align-items:center; gap:7px; }
  button.primary:hover { background:var(--accent-dark); }
  button.primary:disabled { background:var(--border-strong); cursor:not-allowed; }
  button.ghost { background:var(--panel); color:var(--text); border:1px solid var(--border-strong);
                 border-radius:8px; padding:9px 14px; font-size:13px; font-weight:500; cursor:pointer; transition:.12s;
                 display:inline-flex; align-items:center; gap:6px; }
  button.ghost:hover { border-color:var(--accent); color:var(--accent); }
  .banner { padding:12px 16px; border-radius:8px; font-size:13.5px; margin-bottom:16px; }
  .banner.ok { background:var(--green-tint); border:1px solid var(--green-border); color:#166534; }
  .banner.warn { background:var(--amber-tint); border:1px solid var(--amber-border); color:#92400e; }
  .banner ul { margin:8px 0 0 18px; padding:0; }
  .banner code { background:rgba(0,0,0,.06); padding:1px 5px; border-radius:4px; }
  /* processing stage cards */
  .steps { display:flex; gap:10px; margin:2px 0 16px; flex-wrap:wrap; }
  .step { flex:1; min-width:140px; background:var(--panel2); border:1px solid var(--border); border-radius:8px;
          padding:12px 14px; font-size:13px; color:var(--muted); display:flex; align-items:center; gap:9px; }
  .step .ic { width:20px;height:20px;border-radius:50%;border:2px solid var(--border-strong);flex-shrink:0;
              display:flex;align-items:center;justify-content:center;font-size:11px; }
  .step.active { border-color:var(--accent); color:var(--text); background:var(--accent-tint); }
  .step.active .ic { border-color:var(--accent); color:var(--accent); }
  .step.done { border-color:var(--green); color:var(--text); background:var(--green-tint); }
  .step.done .ic { border-color:var(--green); background:var(--green); color:#fff; }
  #progWrap { margin:4px 0 14px; }
  #progBar { height:8px; background:var(--panel2); border:1px solid var(--border); border-radius:6px; overflow:hidden; }
  #progFill { height:100%; width:0; background:var(--accent); border-radius:6px; transition:width .4s ease; }
  #progFill.indet { width:35%; animation:indet 1.3s ease-in-out infinite; }
  @keyframes indet { 0%{margin-left:-35%} 100%{margin-left:100%} }
  #progMeta { display:flex; justify-content:space-between; gap:10px; font-size:13px; color:var(--text); margin-top:10px; }
  #phaseLabel { font-weight:600; }
  #elapsed { color:var(--muted); font-variant-numeric:tabular-nums; }
  #log { background:#0f172a; color:#7ee787; border:1px solid var(--border); border-radius:8px; padding:12px; margin-top:10px;
         font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; max-height:170px; overflow:auto; white-space:pre-wrap; }
  .hidden { display:none !important; }
  /* result: fork + saved location */
  #resultHead { font-size:17px; font-weight:500; margin-bottom:16px; display:flex; align-items:center; gap:8px; }
  #resultHead .ic { color:var(--green); width:1.15em; height:1.15em; }
  #routeCards { display:flex; gap:14px; flex-wrap:wrap; margin-bottom:18px; }
  .route { flex:1; min-width:260px; border:1px solid var(--border); border-radius:12px; padding:16px 18px; background:var(--panel2);
           display:flex; flex-direction:column; gap:7px; }
  .route.reco { border:2px solid var(--accent); padding:15px 17px; }
  .route-head { display:flex; align-items:center; justify-content:space-between; }
  .route-head .ic { width:20px; height:20px; }
  .route-title { font-weight:500; font-size:14.5px; }
  .route-sub { color:var(--muted); font-size:12.5px; line-height:1.5; margin-bottom:4px; }
  .route .btns { display:flex; gap:8px; flex-wrap:wrap; }
  .saved-loc { display:flex; align-items:center; gap:8px; font-size:12.5px; color:var(--muted); margin-bottom:14px; }
  .saved-loc code { background:var(--panel2); border:1px solid var(--border); border-radius:5px; padding:2px 7px; font-size:12px; }
  #momHead { display:flex; align-items:center; gap:7px; font-size:12px; color:var(--muted);
             background:var(--panel2); border:1px solid var(--border); border-bottom:0;
             border-radius:10px 10px 0 0; padding:9px 14px; }
  #momHead + #mom { border-radius:0 0 10px 10px; border-top:0; }
  #mom { background:var(--panel); border:1px solid var(--border); border-radius:10px; padding:8px 26px 26px; overflow-x:auto; }
  #mom h1,#mom h2,#mom h3 { line-height:1.3; }
  #mom h1 { font-size:22px; border-bottom:1px solid var(--border); padding-bottom:8px; }
  #mom h2 { font-size:18px; margin-top:26px; }
  #mom h3 { font-size:15px; }
  #mom table { border-collapse:collapse; width:100%; margin:12px 0; font-size:14px; }
  #mom th,#mom td { border:1px solid var(--border); padding:7px 10px; text-align:left; vertical-align:top; }
  #mom th { background:var(--panel2); }
  #mom code { background:var(--panel2); padding:1px 5px; border-radius:5px; font-size:13px; }
  #mom li { margin:3px 0; }
  .toolbar { display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin:6px 0 12px; }
  #speakerPanel { background:var(--amber-tint); border:1px solid var(--amber-border); border-radius:10px; padding:16px 18px; margin-bottom:18px; }
  #speakerPanel h4 { margin:0 0 4px; font-size:14.5px; font-weight:500; display:flex; align-items:center; gap:7px; }
  #speakerPanel .sp-sub { color:var(--muted); font-size:12.5px; font-weight:400; display:block; margin-bottom:12px; }
  #speakerPanel .sp-row { display:flex; align-items:center; gap:10px; margin:8px 0; }
  #speakerPanel .sp-row .lab { width:120px; color:#92400e; font-size:12.5px; font-weight:500; }
  #speakerPanel input { flex:1; background:var(--panel); color:var(--text); border:1px solid var(--border-strong); border-radius:8px; padding:8px 11px; font-size:14px; }
  details { margin-top:18px; }
  summary { cursor:pointer; color:var(--muted); font-size:13px; }
  .spin { display:inline-block; width:14px;height:14px;border:2px solid rgba(255,255,255,.3);
          border-top-color:#fff;border-radius:50%;animation:s .8s linear infinite;vertical-align:-2px;margin-right:8px;}
  svg.spin-ic { animation:s .9s linear infinite; }
  @keyframes s { to { transform:rotate(360deg);} }
  @media print {
    header, #banner, #inputCard, #progCard, .toolbar, #routeCards, #resultHead,
    #speakerPanel, .saved-loc, details, #recentBar { display:none !important; }
    body { background:#fff; color:#000; }
    .wrap { max-width:none; padding:0; }
    #resultCard, #mom { border:0; padding:0; background:#fff; box-shadow:none; }
    #mom th, #mom td { border-color:#999 !important; }
    #mom th { background:#f2f2f2 !important; }
  }
</style>
</head>
<body>
<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs><symbol id="i-alert-triangle" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4" /> <path d="M10.363 3.591l-8.106 13.534a1.914 1.914 0 0 0 1.636 2.871h16.214a1.914 1.914 0 0 0 1.636 -2.87l-8.106 -13.536a1.914 1.914 0 0 0 -3.274 0" /> <path d="M12 16h.01" /></symbol><symbol id="i-arrow-up-right" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 7l-10 10" /> <path d="M8 7l9 0l0 9" /></symbol><symbol id="i-ban" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 18 0a9 9 0 1 0 -18 0" /> <path d="M5.7 5.7l12.6 12.6" /></symbol><symbol id="i-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5l10 -10" /></symbol><symbol id="i-copy" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 9.667a2.667 2.667 0 0 1 2.667 -2.667h8.666a2.667 2.667 0 0 1 2.667 2.667v8.666a2.667 2.667 0 0 1 -2.667 2.667h-8.666a2.667 2.667 0 0 1 -2.667 -2.667l0 -8.666" /> <path d="M4.012 16.737a2.005 2.005 0 0 1 -1.012 -1.737v-10c0 -1.1 .9 -2 2 -2h10c.75 0 1.158 .385 1.5 1" /></symbol><symbol id="i-device-floppy" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 4h10l4 4v10a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2v-12a2 2 0 0 1 2 -2" /> <path d="M10 14a2 2 0 1 0 4 0a2 2 0 1 0 -4 0" /> <path d="M14 4l0 4l-6 0l0 -4" /></symbol><symbol id="i-download" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2 -2v-2" /> <path d="M7 11l5 5l5 -5" /> <path d="M12 4l0 12" /></symbol><symbol id="i-eye" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 12a2 2 0 1 0 4 0a2 2 0 0 0 -4 0" /> <path d="M21 12c-2.4 4 -5.4 6 -9 6c-3.6 0 -6.6 -2 -9 -6c2.4 -4 5.4 -6 9 -6c3.6 0 6.6 2 9 6" /></symbol><symbol id="i-file-text" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3v4a1 1 0 0 0 1 1h4" /> <path d="M17 21h-10a2 2 0 0 1 -2 -2v-14a2 2 0 0 1 2 -2h7l5 5v11a2 2 0 0 1 -2 2" /> <path d="M9 9l1 0" /> <path d="M9 13l6 0" /> <path d="M9 17l6 0" /></symbol><symbol id="i-folder-open" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 19l2.757 -7.351a1 1 0 0 1 .936 -.649h12.307a1 1 0 0 1 .986 1.164l-.996 5.211a2 2 0 0 1 -1.964 1.625h-14.026a2 2 0 0 1 -2 -2v-11a2 2 0 0 1 2 -2h4l3 3h7a2 2 0 0 1 2 2v2" /></symbol><symbol id="i-loader-2" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a9 9 0 1 0 9 9" /></symbol><symbol id="i-lock" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 13a2 2 0 0 1 2 -2h10a2 2 0 0 1 2 2v6a2 2 0 0 1 -2 2h-10a2 2 0 0 1 -2 -2v-6" /> <path d="M11 16a1 1 0 1 0 2 0a1 1 0 0 0 -2 0" /> <path d="M8 11v-4a4 4 0 1 1 8 0v4" /></symbol><symbol id="i-microphone-2" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 12.9a5 5 0 1 0 -3.902 -3.9" /> <path d="M15 12.9l-3.902 -3.899l-7.513 8.584a2 2 0 1 0 2.827 2.83l8.588 -7.515" /></symbol><symbol id="i-pencil" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4l10.5 -10.5a2.828 2.828 0 1 0 -4 -4l-10.5 10.5v4" /> <path d="M13.5 6.5l4 4" /></symbol><symbol id="i-printer" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 17h2a2 2 0 0 0 2 -2v-4a2 2 0 0 0 -2 -2h-14a2 2 0 0 0 -2 2v4a2 2 0 0 0 2 2h2" /> <path d="M17 9v-4a2 2 0 0 0 -2 -2h-6a2 2 0 0 0 -2 2v4" /> <path d="M7 15a2 2 0 0 1 2 -2h6a2 2 0 0 1 2 2v4a2 2 0 0 1 -2 2h-6a2 2 0 0 1 -2 -2l0 -4" /></symbol><symbol id="i-sparkles" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 18a2 2 0 0 1 2 2a2 2 0 0 1 2 -2a2 2 0 0 1 -2 -2a2 2 0 0 1 -2 2m0 -12a2 2 0 0 1 2 2a2 2 0 0 1 2 -2a2 2 0 0 1 -2 -2a2 2 0 0 1 -2 2m-7 12a6 6 0 0 1 6 -6a6 6 0 0 1 -6 -6a6 6 0 0 1 -6 6a6 6 0 0 1 6 6" /></symbol><symbol id="i-users" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 7a4 4 0 1 0 8 0a4 4 0 1 0 -8 0" /> <path d="M3 21v-2a4 4 0 0 1 4 -4h4a4 4 0 0 1 4 4v2" /> <path d="M16 3.13a4 4 0 0 1 0 7.75" /> <path d="M21 21v-2a4 4 0 0 0 -3 -3.85" /></symbol><symbol id="i-writing" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 17v-12c0 -1.121 -.879 -2 -2 -2s-2 .879 -2 2v12l2 2l2 -2" /> <path d="M16 7h4" /> <path d="M18 19h-13a2 2 0 1 1 0 -4h4a2 2 0 1 0 0 -4h-3" /></symbol><symbol id="i-x" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6l-12 12" /> <path d="M6 6l12 12" /></symbol></defs></svg>
<header>
  <div class="logo"><svg class="ic"><use href="#i-file-text"/></svg></div>
  <div>
    <h1>MoM Generator</h1>
    <p>Meeting recording → speaker-labelled transcript → styled Minutes-of-Meeting · on-device, 100% local</p>
  </div>
</header>
<div class="wrap">
  <div id="recentBar" class="hidden">
    <span>↻ Recent results:</span>
    <select id="recent" style="min-width:240px"><option value="">— pick a past MoM —</option></select>
  </div>
  <div id="banner"></div>

  <div class="card" id="inputCard">
    <!-- STEP 1 — recording -->
    <div class="step-block">
      <div class="step-head"><span class="step-num">1</span> Choose a recording</div>
      <input id="path" type="text" style="width:100%"
             placeholder="Paste a file path on this Mac — e.g. ~/Downloads/meeting.mp4">
      <div class="or">— or —</div>
      <div id="drop">
        <div class="big"><svg style="width:30px;height:30px;color:var(--muted)" aria-hidden="true"><use href="#i-microphone-2"/></svg></div>
        <div>Drag a recording here, or <u>click to choose a file</u></div>
        <div class="sub">.mp4 · .mov · .m4a · .mp3 · .wav · .aac — audio or video</div>
        <input type="file" id="file" class="hidden" accept="audio/*,video/*">
      </div>
      <div id="fileRow" class="hidden">
        <span class="fi-ic"><svg style="width:20px;height:20px;color:var(--muted)" aria-hidden="true"><use href="#i-file-text"/></svg></span>
        <div style="flex:1">
          <div class="fi-name" id="fiName"></div>
          <div class="fi-meta" id="fiMeta"></div>
        </div>
        <button class="link-btn" id="fileChange">Change</button>
        <button class="link-btn" id="fileRemove">Remove</button>
      </div>
      <div id="urlRow" class="hidden" style="margin-top:14px; gap:10px; align-items:center">
        <input id="url" type="text" style="flex:1"
               placeholder="…or paste a YouTube / video link, then click Fetch">
        <button class="ghost" id="fetchBtn" style="white-space:nowrap">Fetch &amp; Generate</button>
      </div>
    </div>

    <!-- STEP 2 — context -->
    <div class="step-block">
      <div class="step-head"><span class="step-num">2</span> Meeting context</div>
      <label>Attendees <span class="hint">(recommended — locks speaker-name detection onto these people; comma or line separated)</span></label>
      <textarea id="attendees" rows="2" placeholder="e.g. Maria Papadopoulou, Nikos Georgiou, Eleni K."></textarea>
      <div class="row" style="margin-top:16px">
        <div>
          <label>Spoken language</label>
          <select id="lang">
            <option value="el" selected>Greek</option>
            <option value="auto">Auto-detect</option>
            <option value="en">English</option>
          </select>
        </div>
        <div id="momOptWrap">
          <label>Draft an English MoM now <span class="hint">(optional)</span></label>
          <div style="display:flex;align-items:center;gap:8px;height:40px">
            <label style="display:flex;align-items:center;gap:7px;cursor:pointer;font-weight:400;color:var(--text);margin:0">
              <input type="checkbox" id="genMom" style="width:16px;height:16px;accent-color:var(--accent)">
              also draft it locally
            </label>
            <select id="model" class="hidden" style="min-width:130px"></select>
          </div>
        </div>
      </div>
    </div>

    <!-- STEP 3 — generate -->
    <div class="step-block">
      <div class="step-head"><span class="step-num">3</span> Generate</div>
      <div style="display:flex;align-items:center;gap:4px;flex-wrap:wrap">
        <button class="primary" id="go" disabled>Generate transcript</button>
        <span class="reason" id="goReason">Choose a recording first.</span>
      </div>
    </div>
  </div>

  <div class="card hidden" id="progCard">
    <div class="steps">
      <div class="step" data-k="audio"><span class="ic" data-n="1">1</span> Extracting audio</div>
      <div class="step" data-k="transcribe"><span class="ic" data-n="2">2</span> Transcribing (Greek)</div>
      <div class="step" data-k="names"><span class="ic" data-n="3">3</span> Reading speaker names</div>
    </div>
    <div id="progWrap">
      <div id="progBar"><div id="progFill"></div></div>
      <div id="progMeta" role="status" aria-live="polite"><span id="phaseLabel">Starting…</span><span id="elapsed"></span></div>
    </div>
    <details><summary>Technical log</summary><div id="log"></div></details>
  </div>

  <div class="card hidden" id="resultCard">
    <div id="resultHead"><svg class="ic"><use href="#i-check"/></svg> Transcript ready — with speaker names</div>

    <div id="speakerPanel" class="hidden"></div>

    <!-- Choose how to create the MoM -->
    <div id="routeCards">
      <div class="route reco">
        <div class="route-head">
          <svg class="ic" style="color:var(--accent)"><use href="#i-sparkles"/></svg>
          <span class="badge">Recommended</span>
        </div>
        <div class="route-title">Google Gemini</div>
        <div class="route-sub">Best quality, and it reads your screenshots. Paste into Gemini, then paste the result into Gmail.</div>
        <div class="btns">
          <button class="primary" id="copyPromptBtn" title="Copies the styling prompt with this transcript embedded — paste into Gemini, attach screenshots"><svg class="ic"><use href="#i-sparkles"/></svg> Copy prompt</button>
          <button class="ghost" id="dlTxtBtn"><svg class="ic"><use href="#i-download"/></svg> Transcript</button>
          <button class="ghost" id="copyTxtBtn"><svg class="ic"><use href="#i-copy"/></svg> Copy</button>
        </div>
      </div>
      <div class="route">
        <div class="route-head"><svg class="ic" style="color:var(--muted)"><use href="#i-lock"/></svg></div>
        <div class="route-title">Private and offline</div>
        <div class="route-sub">On your Mac, no tokens. Drafts the styled MoM with your local model (screenshots not read).</div>
        <div class="btns">
          <button class="primary" id="styledBtn" title="Generate the styled email MoM locally with your Ollama model — 100% offline, no tokens"><svg class="ic"><use href="#i-file-text"/></svg> Generate MoM</button>
        </div>
      </div>
    </div>

    <!-- Actions once a MoM exists -->
    <div id="momActions" class="toolbar hidden">
      <button class="primary" id="copyRichBtn"><svg class="ic"><use href="#i-copy"/></svg> Copy for Gmail</button>
      <button class="ghost" id="dlBtn"><svg class="ic"><use href="#i-download"/></svg> Download</button>
      <button class="ghost" id="pdfBtn"><svg class="ic"><use href="#i-printer"/></svg> Save as PDF</button>
      <button class="ghost" id="openFolderBtn"><svg class="ic"><use href="#i-folder-open"/></svg> Open folder</button>
      <button class="ghost" id="copyBtn"><svg class="ic"><use href="#i-copy"/></svg> Copy text</button>
    </div>
    <div id="savedLoc" class="saved-loc hidden"></div>

    <div id="momHead" class="hidden"><svg class="ic"><use href="#i-eye"/></svg> Preview — pastes into Gmail as-is</div>
    <div id="mom"></div>
    <details>
      <summary>Show raw transcript</summary>
      <pre id="rawTranscript" style="white-space:pre-wrap;font-size:13px;color:var(--muted)"></pre>
    </details>
  </div>
</div>

<script>
const $ = s => document.querySelector(s);
let chosenFile = null, currentJob = null, momText = "", transcriptText = "", styledHtml = "", currentOutdir = "";

async function loadHealth(){
  let h;
  try { h = await (await fetch('/health')).json(); }
  catch(e){ return; }
  const sel = $('#model'); sel.innerHTML = '';
  const models = h.ollama.models || [];
  models.forEach(m => {
    const o = document.createElement('option'); o.value = m; o.textContent = m;
    if (m === h.default_model) o.selected = true; sel.appendChild(o);
  });
  // The optional local-MoM toggle only makes sense when Ollama has a model.
  $('#momOptWrap').classList.toggle('hidden', models.length === 0);
  // YouTube/link field only when the optional tools are installed (personal add-on).
  if (h.ytdlp) $('#urlRow').classList.remove('hidden'), $('#urlRow').style.display='flex';
  const b = $('#banner');
  const notes = (h.notes && h.notes.length) ? '<div style="margin-top:6px;opacity:.85;font-size:12.5px">'+h.notes.join('<br>')+'</div>' : '';
  if (h.ready){
    b.className='banner ok';
    b.innerHTML = icon('check')+' Ready. Add a recording, then Generate — you\'ll get a speaker-labelled transcript.' + notes;
  } else {
    b.className='banner warn';
    b.innerHTML = icon('alert-triangle')+' Some tools are missing — run <code>./setup.sh</code>:<ul>' +
      h.issues.map(i=>'<li>'+i+'</li>').join('') + '</ul>' + notes;
  }
  updateGo();
}

// Generate is enabled when there's either a picked file or a typed path.
function updateGo(){
  const hasPath = $('#path').value.trim() !== '';
  const ok = !!chosenFile || hasPath;
  $('#go').disabled = !ok;
  $('#goReason').textContent = ok ? '' : 'Choose a recording or paste a file path first.';
}
// Local-MoM checkbox reveals the model picker and changes the button intent.
function wireMomToggle(){
  const on = $('#genMom').checked;
  $('#model').classList.toggle('hidden', !on);
  $('#go').textContent = on ? 'Generate transcript + MoM' : 'Generate transcript';
}

const drop = $('#drop'), fileInput = $('#file');
drop.onclick = () => fileInput.click();
fileInput.onchange = e => setFile(e.target.files[0]);
['dragover','dragenter'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.add('hover');}));
['dragleave','drop'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.remove('hover');}));
drop.addEventListener('drop', e => { if(e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]); });
// Show a clean file row (name + size + Change/Remove); a typed path clears any picked file.
function setFile(f){
  chosenFile = f || null;
  if(chosenFile){
    $('#path').value = '';
    $('#fiName').textContent = chosenFile.name;
    $('#fiMeta').textContent = (chosenFile.size/1048576).toFixed(1)+' MB';
    $('#fileRow').classList.remove('hidden');
    $('#drop').classList.add('hidden');
  } else {
    $('#fileRow').classList.add('hidden');
    $('#drop').classList.remove('hidden');
    fileInput.value = '';
  }
  updateGo();
}
$('#fileChange').onclick = () => fileInput.click();
$('#fileRemove').onclick = () => setFile(null);
$('#path').addEventListener('input', () => { if($('#path').value.trim() && chosenFile) setFile(null); updateGo(); });
$('#genMom').onchange = wireMomToggle;

let elapsedTimer=null, startTime=0, curPhase='';
function fmtTime(ms){ const s=Math.floor(ms/1000); return Math.floor(s/60)+':'+String(s%60).padStart(2,'0'); }
function startTimer(){ startTime=Date.now(); $('#elapsed').textContent='⏱ 0:00'; clearInterval(elapsedTimer);
  elapsedTimer=setInterval(()=>{ $('#elapsed').textContent='⏱ '+fmtTime(Date.now()-startTime); },500); }
function stopTimer(){ clearInterval(elapsedTimer); }
function setIndet(on){ const f=$('#progFill'); f.classList.toggle('indet',on); if(on) f.style.width=''; }
function setProgress(pct){ setIndet(false); $('#progFill').style.width=Math.round(pct*100)+'%'; }
function setPhase(t){ curPhase=t; $('#phaseLabel').textContent=t; }

function beginRun(phase){
  $('#go').disabled = true; $('#fetchBtn').disabled = true;
  $('#resultCard').classList.add('hidden');
  $('#speakerPanel').classList.add('hidden');
  $('#progCard').classList.remove('hidden');
  $('#log').textContent = '';
  document.querySelectorAll('.step').forEach(s=>{ s.className='step'; const ic=s.querySelector('.ic'); if(ic) ic.textContent=ic.dataset.n||ic.textContent; });
  $('#progFill').style.width='0'; setIndet(true); setPhase(phase); startTimer();
  momText = ""; styledHtml = ""; currentOutdir=""; $('#mom').innerHTML = '';
  window.scrollTo({top: $('#progCard').offsetTop-20, behavior:'smooth'});
}

const modelFor = () => ($('#genMom').checked && $('#model').value) ? $('#model').value : 'none';

// One Generate button: uses the typed path if present, else the picked file.
$('#go').onclick = async () => {
  const path = $('#path').value.trim();
  if(path){
    beginRun('Reading local file…');
    const res = await fetch('/local', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ path, language:$('#lang').value, model:modelFor(), attendees:$('#attendees').value })
    });
    const d = await res.json();
    if(d.error){ alert(d.error); $('#go').disabled=false; stopTimer(); $('#progCard').classList.add('hidden'); return; }
    currentJob = d.job; localStorage.setItem('momJob', d.job); listen(d.job);
    return;
  }
  if(!chosenFile){ updateGo(); return; }
  beginRun('Uploading…');
  const res = await fetch('/upload', {
    method:'POST', body: chosenFile,
    headers:{ 'X-Filename': encodeURIComponent(chosenFile.name),
              'X-Language': $('#lang').value, 'X-Model': modelFor(),
              'X-Attendees': encodeURIComponent($('#attendees').value) }
  });
  const { job } = await res.json();
  currentJob = job; localStorage.setItem('momJob', job);
  listen(job);
};
$('#path').addEventListener('keydown', e => { if(e.key==='Enter' && !$('#go').disabled) $('#go').click(); });

$('#fetchBtn').onclick = async () => {
  const url = $('#url').value.trim();
  if(!/^https?:\/\//i.test(url)) { alert('Paste a valid link starting with http(s)://'); return; }
  beginRun('Downloading from link…');
  const res = await fetch('/fetch', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ url, language: $('#lang').value, model: modelFor(), attendees: $('#attendees').value })
  });
  const d = await res.json();
  if(d.error){ alert(d.error); $('#go').disabled=false; $('#fetchBtn').disabled=false; stopTimer(); return; }
  currentJob = d.job; localStorage.setItem('momJob', d.job);
  listen(d.job);
};

function setStepIcon(el, state){
  const ic = el.querySelector('.ic'); if(!ic) return;
  ic.innerHTML = state==='done' ? '<svg style="width:13px;height:13px" aria-hidden="true"><use href="#i-check"/></svg>' : (ic.dataset.n||'');
}
function setStep(k, state){
  const order=['audio','transcribe','names'];
  const el=document.querySelector('.step[data-k="'+k+'"]'); if(!el) return;
  el.className='step '+state; setStepIcon(el, state);
  if(state==='active'){ // mark earlier as done
    order.slice(0, order.indexOf(k)).forEach(p=>{
      const e=document.querySelector('.step[data-k="'+p+'"]'); if(e){ e.className='step done'; setStepIcon(e,'done'); }
    });
  }
}
function logLine(t){ const l=$('#log'); l.textContent += t+'\n'; l.scrollTop=l.scrollHeight; }

function listen(job){
  const es = new EventSource('/events?job='+job);
  es.onmessage = e => {
    const d = JSON.parse(e.data);
    if(d.type==='stage'){ setStep(d.stage,'active'); logLine('▶ '+d.msg); setPhase(d.msg); setIndet(true); }
    else if(d.type==='progress'){ setProgress(d.pct); $('#phaseLabel').textContent = curPhase+' '+Math.round(d.pct*100)+'%'; }
    else if(d.type==='log'){ logLine(d.line); }
    else if(d.type==='transcript'){ transcriptText = d.text; $('#rawTranscript').textContent = d.text; }
    else if(d.type==='partial'){ momText += d.text; $('#resultCard').classList.remove('hidden'); $('#mom').innerHTML = renderMd(momText); }
    else if(d.type==='done'){
      es.close(); stopTimer(); setIndet(false); $('#progFill').style.width='100%'; $('#phaseLabel').textContent='Done';
      ['audio','transcribe','names'].forEach(k=>setStep(k,'done'));
      renderResult(d);
      localStorage.removeItem('momJob'); loadRecent();
      $('#go').disabled=false; $('#fetchBtn').disabled=false;
      window.scrollTo({top: $('#resultCard').offsetTop-20, behavior:'smooth'});
    }
    else if(d.type==='error'){
      es.close(); stopTimer(); setIndet(false); $('#phaseLabel').textContent='Error';
      logLine('ERROR: '+d.error);
      $('#banner').className='banner warn'; $('#banner').innerHTML=icon('alert-triangle')+' '+d.error;
      $('#go').disabled=false; $('#fetchBtn').disabled=false;
    }
  };
  es.onerror = () => { es.close(); };
}

function icon(n){ return '<svg class="ic"><use href="#i-'+n+'"/></svg>'; }
// innerHTML-based so buttons keep their SVG icon after a flash message.
function flash(sel,msg){ const b=$(sel); const o=b.dataset.html||(b.dataset.html=b.innerHTML); b.innerHTML=msg; setTimeout(()=>b.innerHTML=o,1600); }

function renderSpeakerPanel(speakers, map, roster){
  const p = $('#speakerPanel'); p.classList.remove('hidden');
  const esc2 = s => (s||'').replace(/"/g,'&quot;');
  const opts = (roster||[]).map(n=>'<option value="'+esc2(n)+'">').join('');
  const rows = speakers.map(s=>
    '<div class="sp-row"><span class="lab">'+s+'</span>'+
    '<input data-spk="'+s+'" value="'+esc2(map[s]||'')+'" list="rosterList" '+
    'placeholder="name (blank = keep '+s+')"></div>').join('');
  p.innerHTML = '<h4>'+icon('users')+' Review speaker names</h4>'+
    '<span class="sp-sub">Read from the video — fix any that look wrong (autocompletes from your attendees), then apply.</span>'+
    rows + '<datalist id="rosterList">'+opts+'</datalist>'+
    '<button class="primary" id="regenBtn" style="margin-top:12px">'+icon('check')+' Apply names &amp; update</button>';
  $('#regenBtn').onclick = regen;
}
async function regen(){
  const mapping = {};
  document.querySelectorAll('#speakerPanel input').forEach(i=>{ if(i.value.trim()) mapping[i.dataset.spk]=i.value.trim(); });
  const btn=$('#regenBtn'); const orig=btn.dataset.html||(btn.dataset.html=btn.innerHTML); btn.textContent='Applying…'; btn.disabled=true;
  try {
    const r = await fetch('/rename?job='+currentJob, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({mapping})});
    const d = await r.json();
    if(d.error){ alert(d.error); }
    else {
      if(d.transcript){ transcriptText = d.transcript; $('#rawTranscript').textContent = d.transcript; }
      if(d.markdown){ momText = d.markdown; $('#mom').innerHTML = renderMd(momText); }
      flash('#regenBtn','Updated');
    }
  } catch(e){ alert('update failed'); }
  btn.innerHTML=orig; btn.disabled=false;
}

$('#copyBtn').onclick = () => navigator.clipboard.writeText(momText).then(()=>flash('#copyBtn','Copied!'));
$('#dlBtn').onclick = () => {
  if(!momText) return;
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([momText],{type:'text/markdown'}));
  a.download='MoM.md'; a.click(); URL.revokeObjectURL(a.href);
};
$('#pdfBtn').onclick = () => window.print();

// Primary deliverable: the speaker-labelled transcript, for Gemini.
$('#copyTxtBtn').onclick = () => navigator.clipboard.writeText(transcriptText).then(()=>flash('#copyTxtBtn','Copied!'));
$('#dlTxtBtn').onclick = () => {
  if(!transcriptText){ flash('#dlTxtBtn','No transcript yet'); return; }
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([transcriptText],{type:'text/plain'}));
  a.download='transcript.txt'; a.click(); URL.revokeObjectURL(a.href);
};

// One-click Gemini flow: copies the styling prompt with this transcript embedded.
// Paste into Gemini, attach your screenshots → same styled MoM email every time.
$('#copyPromptBtn').onclick = async () => {
  if(!transcriptText){ flash('#copyPromptBtn','No transcript yet'); return; }
  try {
    const r = await fetch('/gemini_prompt?job='+(currentJob||''));
    let prompt = (await r.json()).prompt || '';
    if(prompt.indexOf(transcriptText)===-1){ prompt = prompt.replace('<paste transcript here>', transcriptText); }
    await navigator.clipboard.writeText(prompt);
    flash('#copyPromptBtn','Copied — paste into Gemini, attach screenshots');
  } catch(e){ flash('#copyPromptBtn','Copy failed'); }
};

// Inline styles so formatting survives a paste into Gmail (which strips <style>/classes).
const EMAIL_STYLES = {
  h1:'font-size:21px;font-weight:700;margin:18px 0 8px;border-bottom:1px solid #ddd;padding-bottom:5px;font-family:Arial,Helvetica,sans-serif',
  h2:'font-size:17px;font-weight:700;margin:18px 0 6px;font-family:Arial,Helvetica,sans-serif',
  h3:'font-size:15px;font-weight:700;margin:12px 0 4px;font-family:Arial,Helvetica,sans-serif',
  h4:'font-size:14px;font-weight:700;margin:10px 0 4px;font-family:Arial,Helvetica,sans-serif',
  table:'border-collapse:collapse;width:100%;margin:10px 0;font-size:13px',
  th:'border:1px solid #bbb;padding:6px 9px;text-align:left;background:#f2f2f2',
  td:'border:1px solid #bbb;padding:6px 9px;text-align:left;vertical-align:top',
  ul:'margin:6px 0 6px 22px;padding:0', ol:'margin:6px 0 6px 22px;padding:0',
  li:'margin:3px 0', p:'margin:8px 0',
  code:'background:#f0f0f0;padding:1px 4px;border-radius:4px;font-family:monospace'
};

// Offline styled MoM: local Ollama model -> JSON -> exact email template. No tokens.
$('#styledBtn').onclick = async () => {
  if(!transcriptText){ flash('#styledBtn','No transcript yet'); return; }
  const b=$('#styledBtn'); const orig=b.dataset.html||(b.dataset.html=b.innerHTML);
  b.innerHTML='<svg class="ic spin-ic" aria-hidden="true"><use href="#i-loader-2"/></svg> Generating on your Mac…'; b.disabled=true;
  try {
    const r = await fetch('/styled_mom?job='+(currentJob||''), {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    const d = await r.json();
    if(d.error){ alert(d.error); }
    else {
      styledHtml = d.html;
      $('#mom').innerHTML = styledHtml;
      $('#momHead').classList.remove('hidden');
      $('#momActions').classList.remove('hidden');
      $('#resultCard').classList.remove('hidden');
      b.innerHTML=icon('check')+' Drafted with '+d.model; setTimeout(()=>{b.innerHTML=orig;},2500);
      $('#momHead').scrollIntoView({behavior:'smooth', block:'start'});
    }
  } catch(e){ alert('Local MoM failed'); b.innerHTML=orig; }
  b.disabled=false;
};

$('#copyRichBtn').onclick = async () => {
  // Prefer the deterministic styled email if we generated one; else render markdown.
  const html = styledHtml
    ? styledHtml
    : '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#111;line-height:1.55">'
             + renderMd(momText, EMAIL_STYLES) + '</div>';
  const plain = styledHtml ? (new DOMParser().parseFromString(styledHtml,'text/html').body.textContent||'') : momText;
  try {
    await navigator.clipboard.write([new ClipboardItem({
      'text/html': new Blob([html], {type:'text/html'}),
      'text/plain': new Blob([plain], {type:'text/plain'})
    })]);
    flash('#copyRichBtn','Copied — paste into Gmail');
    return;
  } catch(e){}
  try {
    await navigator.clipboard.write([new ClipboardItem({
      'text/html': new Blob([html], {type:'text/html'}),
      'text/plain': new Blob([momText], {type:'text/plain'})
    })]);
    flash('#copyRichBtn','Copied — paste into Gmail');
  } catch(e){
    // Fallback for browsers without ClipboardItem: select rendered HTML + execCommand.
    const tmp=document.createElement('div'); tmp.innerHTML=html;
    tmp.style.cssText='position:fixed;left:-9999px;top:0'; document.body.appendChild(tmp);
    const sel=getSelection(), r=document.createRange(); r.selectNodeContents(tmp);
    sel.removeAllRanges(); sel.addRange(r);
    try{ document.execCommand('copy'); flash('#copyRichBtn','Copied — paste into Gmail'); }
    catch(_){ flash('#copyRichBtn','Copy failed'); }
    sel.removeAllRanges(); document.body.removeChild(tmp);
  }
};

// --- tiny markdown renderer (headings, bold, code, lists, tables) ---
// Pass a styles map (EMAIL_STYLES) to emit inline styles; omit for on-page CSS.
function esc(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function st(S,tag){ return (S && S[tag]) ? (' style="'+S[tag]+'"') : ''; }
function inline(s,S){ return esc(s).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/`(.+?)`/g,'<code'+st(S,'code')+'>$1</code>'); }
function renderMd(md,S){
  const lines = md.split('\n'); let out=[], i=0;
  while(i<lines.length){
    let ln = lines[i];
    if(/^\s*\|.*\|\s*$/.test(ln) && i+1<lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i+1])){
      const head = ln.split('|').slice(1,-1).map(c=>c.trim());
      i+=2; let rows=[];
      while(i<lines.length && /^\s*\|.*\|\s*$/.test(lines[i])){ rows.push(lines[i].split('|').slice(1,-1).map(c=>c.trim())); i++; }
      out.push('<table'+st(S,'table')+'><thead><tr>'+head.map(h=>'<th'+st(S,'th')+'>'+inline(h,S)+'</th>').join('')+'</tr></thead><tbody>'+
        rows.map(r=>'<tr>'+r.map(c=>'<td'+st(S,'td')+'>'+inline(c,S)+'</td>').join('')+'</tr>').join('')+'</tbody></table>');
      continue;
    }
    let m;
    if((m=ln.match(/^(#{1,4})\s+(.*)/))){ const n=m[1].length; out.push('<h'+n+st(S,'h'+n)+'>'+inline(m[2],S)+'</h'+n+'>'); i++; continue; }
    if(/^\s*[-*]\s+/.test(ln)){ let items=[]; while(i<lines.length && /^\s*[-*]\s+/.test(lines[i])){ items.push('<li'+st(S,'li')+'>'+inline(lines[i].replace(/^\s*[-*]\s+/,''),S)+'</li>'); i++; } out.push('<ul'+st(S,'ul')+'>'+items.join('')+'</ul>'); continue; }
    if(/^\s*\d+\.\s+/.test(ln)){ let items=[]; while(i<lines.length && /^\s*\d+\.\s+/.test(lines[i])){ items.push('<li'+st(S,'li')+'>'+inline(lines[i].replace(/^\s*\d+\.\s+/,''),S)+'</li>'); i++; } out.push('<ol'+st(S,'ol')+'>'+items.join('')+'</ol>'); continue; }
    if(ln.trim()===''){ out.push(''); i++; continue; }
    out.push('<p'+st(S,'p')+'>'+inline(ln,S)+'</p>'); i++;
  }
  return out.join('\n');
}

// ---- resume + recent results ----
function renderResult(d){
  momText = d.markdown || '';
  styledHtml = '';
  if(d.transcript) transcriptText = d.transcript;
  $('#mom').innerHTML = momText ? renderMd(momText) : '';
  $('#resultCard').classList.remove('hidden');
  // The fork is available whenever there's a transcript to work from.
  $('#routeCards').classList.toggle('hidden', !transcriptText);
  // MoM actions + preview header appear only once a MoM actually exists.
  $('#momActions').classList.toggle('hidden', !momText);
  $('#momHead').classList.toggle('hidden', !momText);
  if(d.transcript) $('#rawTranscript').textContent = d.transcript;
  currentOutdir = d.outdir || '';
  const sl = $('#savedLoc');
  if(currentOutdir){
    sl.classList.remove('hidden');
    sl.innerHTML = icon('device-floppy')+' Saved to <code>'+currentOutdir.replace(/^.*\/Documents/,'~/Documents')+'</code>';
  } else { sl.classList.add('hidden'); }
  if(d.speakers && d.speakers.length) renderSpeakerPanel(d.speakers, d.speaker_map||{}, d.roster||[]);
  else $('#speakerPanel').classList.add('hidden');
}

// Open the output folder in Finder (local server can do this safely).
$('#openFolderBtn').onclick = async () => {
  if(!currentOutdir){ flash('#openFolderBtn','No folder'); return; }
  try {
    const r = await fetch('/open_folder', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({dir: currentOutdir})});
    const d = await r.json(); if(d.error) flash('#openFolderBtn', 'Could not open'); else flash('#openFolderBtn','Opened');
  } catch(e){ flash('#openFolderBtn','Could not open'); }
};

async function loadRecent(){
  try {
    const {jobs} = await (await fetch('/jobs')).json();
    const sel = $('#recent');
    sel.innerHTML = '<option value="">— pick a past MoM —</option>';
    (jobs||[]).forEach(j=>{
      const when = new Date(j.when*1000).toLocaleString();
      const o = document.createElement('option'); o.value=j.dir; o.textContent = j.label+' · '+when;
      sel.appendChild(o);
    });
    $('#recentBar').classList.toggle('hidden', !(jobs && jobs.length));
  } catch(e){}
}
$('#recent').onchange = async () => {
  const dir = $('#recent').value; if(!dir) return;
  try {
    const d = await (await fetch('/result_file?dir='+encodeURIComponent(dir))).json();
    if(d.error){ alert(d.error); return; }
    $('#progCard').classList.add('hidden');
    renderResult(d);
    window.scrollTo({top: $('#resultCard').offsetTop-20, behavior:'smooth'});
  } catch(e){ alert('Could not open that result.'); }
};

async function tryResume(){
  const id = localStorage.getItem('momJob'); if(!id) return;
  let d; try { const r = await fetch('/job?job='+id); if(!r.ok){ localStorage.removeItem('momJob'); return; } d = await r.json(); }
  catch(e){ return; }
  currentJob = id;
  if(d.status==='done'){ renderResult(d); }
  else if(d.status==='queued' || d.status==='running'){
    $('#progCard').classList.remove('hidden'); setIndet(true); setPhase('Resuming…'); startTimer();
    $('#go').disabled=true; $('#fetchBtn').disabled=true; listen(id);
  } else { localStorage.removeItem('momJob'); }  // error/unknown
}

loadHealth();
loadRecent();
tryResume();
</script>
</body>
</html>
"""


def self_check():
    """Report detected engine, ocrmac availability and model discovery WITHOUT
    processing any file. Run: python3 server.py --self-check"""
    whisper = find_whisper()
    ocr_py, ocr_reason = ocrmac_python()
    print("MoM Generator — self-check")
    print(f"  ffmpeg:        {find_ffmpeg() or '❌ not found'}")
    print(f"  whisper.cpp dir: {WHISPERCPP_DIR or '(none discovered)'}")
    if whisper:
        print(f"  transcriber:   {whisper['type']}"
              + (f" · model {os.path.basename(whisper.get('model',''))}" if whisper.get('model') else ""))
    else:
        print("  transcriber:   ❌ none (run ./setup.sh)")
    print(f"  ocrmac Python: {ocr_py or '❌ ' + ocr_reason}")
    print(f"  ollama:        {find_ollama() or '❌ not found (optional)'}")
    return 0 if (whisper and find_ffmpeg()) else 1


def main():
    if "--self-check" in sys.argv[1:]:
        sys.exit(self_check())
    os.makedirs(OUTPUT_BASE, exist_ok=True)
    cleanup_incomplete_outputs()  # tidy abandoned/failed runs from before
    try:
        httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        # Port already in use → another instance is running; just open the browser.
        print(f"MoM Generator already running at http://{HOST}:{PORT}")
        webbrowser.open(f"http://{HOST}:{PORT}")
        return
    url = f"http://{HOST}:{PORT}"
    print(f"MoM Generator running at {url}  (close this window / quit the app to stop)")
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")


if __name__ == "__main__":
    main()
