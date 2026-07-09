#!/bin/bash
# One-time setup for the MoM Generator on a Mac.
# Installs the local tools the app needs:
#   - ffmpeg                       (audio extraction)
#   - whisper.cpp + large-v3-turbo (FAST Greek transcription on the Metal GPU)
#   - WhisperX (large-v3)          (fallback transcriber + Apple Vision OCR venv)
#   - Ollama + qwen2.5:7b          (OPTIONAL local English MoM writer)
# Everything runs locally — no API tokens are used at runtime. The primary output
# is a Greek transcript WITH speaker names (read on-screen via OCR) for Gemini.

set -uo pipefail
say() { printf "\n\033[1;36m==> %s\033[0m\n" "$1"; }
ok()  { printf "\033[1;32m   ✓ %s\033[0m\n" "$1"; }
warn(){ printf "\033[1;33m   ! %s\033[0m\n" "$1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HOME/.cache/mom-generator/venv"
CFG="$HOME/.cache/mom-generator/config.json"
mkdir -p "$HOME/.cache/mom-generator"

# ---------------------------------------------------------------- Homebrew ---
# Used only for ffmpeg / ollama. WhisperX uses uv (no brew needed).
if ! command -v brew >/dev/null 2>&1; then
  if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ollama >/dev/null 2>&1; then
    say "Installing Homebrew (for ffmpeg/ollama; you may be asked for your password)"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  fi
fi
[ -x /opt/homebrew/bin/brew ] && eval "$(/opt/homebrew/bin/brew shellenv)"
[ -x /usr/local/bin/brew ]    && eval "$(/usr/local/bin/brew shellenv)"

# ----------------------------------------------------------------- ffmpeg ---
if command -v ffmpeg >/dev/null 2>&1 \
   || [ -x "/Applications/MediaHuman Audio Converter.app/Contents/Resources/ffmpeg" ]; then
  ok "ffmpeg present"
else
  say "Installing ffmpeg"; brew install ffmpeg && ok "ffmpeg installed"
fi

# ------------------------------------------ whisper.cpp (fast Metal path) ----
# whisper.cpp runs large-v3 on the Apple GPU (~10x faster than WhisperX on CPU).
# The large-v3-turbo model keeps Greek quality while being small + quick.
WCPP_MODELDIR="$HOME/.cache/whisper-cpp"
WCPP_MODEL="$WCPP_MODELDIR/ggml-large-v3-turbo-q5_0.bin"
mkdir -p "$WCPP_MODELDIR"
if command -v whisper-cli >/dev/null 2>&1; then
  ok "whisper.cpp present"
else
  say "Installing whisper.cpp (Metal GPU transcriber)"; brew install whisper-cpp \
    && ok "whisper.cpp installed" || warn "whisper.cpp install skipped (WhisperX will be used)"
fi
if [ -f "$WCPP_MODEL" ]; then
  ok "Greek model (large-v3-turbo) present"
else
  say "Downloading the Greek speech model (large-v3-turbo, ~570 MB)"
  curl -L --fail -o "$WCPP_MODEL" \
    https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin \
    && ok "Greek model downloaded" || warn "Model download failed — re-run setup with internet."
fi

# -------------------------------------------------------- uv + WhisperX ------
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  say "Installing uv (Python manager)"; curl -LsSf https://astral.sh/uv/install.sh | sh
fi
UV="$HOME/.local/bin/uv"; [ -x "$UV" ] || UV="$(command -v uv)"
say "Installing Python 3.11 + WhisperX (fallback transcriber) + Apple Vision OCR (~1 GB)."
"$UV" python install 3.11
"$UV" venv "$VENV" --python 3.11
# ocrmac: Apple Vision OCR — reads on-screen speaker names from video calls. This
#   is what the FAST whisper.cpp path needs for naming (OCR needs ocrmac, NOT
#   WhisperX), so install it FIRST and on its own — it must land even if the heavy
#   WhisperX resolve below is skipped or fails.
"$UV" pip install --python "$VENV/bin/python" ocrmac \
  && ok "Apple Vision OCR (ocrmac) installed" \
  || warn "ocrmac install failed — on-screen speaker naming stays off until it's installed"
# soundfile: gives torchaudio/pyannote a WAV backend without FFmpeg shared libs
#   (torchcodec can't find them on a stock Mac) — required for diarization.
"$UV" pip install --python "$VENV/bin/python" whisperx soundfile \
  && ok "WhisperX installed ($("$VENV/bin/whisperx" --version 2>/dev/null))" \
  || warn "WhisperX install skipped — the whisper.cpp fast path still works"

# ----------------------------------------------------------------- Ollama ---
if command -v ollama >/dev/null 2>&1 || [ -x "/Applications/Ollama.app/Contents/Resources/ollama" ]; then
  ok "Ollama present"
else
  say "Installing Ollama"; brew install ollama && ok "Ollama installed"
fi
OLLAMA="$(command -v ollama || echo /Applications/Ollama.app/Contents/Resources/ollama)"
export OLLAMA_HOST=127.0.0.1:11434
if ! "$OLLAMA" list >/dev/null 2>&1; then
  say "Starting Ollama server"; nohup "$OLLAMA" serve >/tmp/ollama_serve.log 2>&1 &
  for _ in $(seq 1 15); do "$OLLAMA" list >/dev/null 2>&1 && break; sleep 1; done
fi
if "$OLLAMA" list 2>/dev/null | grep -q "qwen2.5:7b"; then ok "Model qwen2.5:7b present"; else
  say "Pulling model qwen2.5:7b (~4.7 GB)"; "$OLLAMA" pull qwen2.5:7b && ok "Model ready"
fi

# Speaker names come from the on-screen names in the video (OCR) — no token,
# no account needed. (Audio-only diarization via a HuggingFace token is an
# optional power-user extra; not part of setup.)

# ------------------------------------------- de-quarantine the launcher ---
# Clear download flags on the whole folder so the .command double-clicks cleanly.
xattr -cr "$SCRIPT_DIR" 2>/dev/null || true
chmod +x "$SCRIPT_DIR/Start MoM Generator.command" 2>/dev/null || true
ok "Launcher cleared to run"

say "Setup complete 🎉  Double-click 'Start MoM Generator.command'."
echo "   (First time: if macOS warns, right-click it → Open → Open.)"
echo "   The Greek speech model is already downloaded — transcription is fully offline."
