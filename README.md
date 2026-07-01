# 📝 MoM Generator

Turn a meeting **recording** into a Greek **transcript with speaker names**, ready
to drop into **Gemini** (with your screenshots) to write the English Minutes of
Meeting — fully on your Mac, **no API tokens, no cloud, no data leaving your machine**.

```
recording → ffmpeg (audio) → whisper.cpp large-v3-turbo on the Metal GPU (Greek transcript)
          → Apple Vision OCR (speaker names from the video) → transcript.txt  →  paste into Gemini
                                                                              ↘ (optional) Ollama → local MoM
```

⚡ **Fast:** transcription runs on the Apple GPU (whisper.cpp + large-v3-turbo),
roughly **10× faster** than the old CPU path, with the same Greek quality.

---

## ▶️ Use it (you, right now)

0. *First time only:* double-click **`Install MoM Generator.command`** and wait for "All set!".
1. Double-click **`Start MoM Generator.command`** (keep the small window it opens). Your browser opens the UI.
2. **① Choose a recording** — drag one in (`.mp4 .mov .m4a .mp3 .wav .aac`) **or paste a
   file path** on this Mac (e.g. `~/Downloads/meeting.mp4`, which skips the upload).
3. **② Meeting context** — type the **Attendees** (recommended: this **locks speaker-name
   detection** onto the real people and kills false matches from shared-screen text).
4. **③ Generate.** When it's done you get a speaker-labelled transcript and a choice of
   two ways to write the MoM:
   - **✨ Best quality — Google Gemini:** click **Copy Gemini prompt**, paste into Gemini,
     attach your screenshots → paste the styled result into Gmail.
   - **🔒 Private & offline:** click **Generate styled MoM** to draft it locally with your
     Ollama model — same styled email, 100% offline, no tokens. Then **Copy for Gmail**.

Both paths produce the **same styled email** (title, attendee chips, status box,
discussion cards, colour-coded action items). A bigger local model (`qwen2.5:14b`)
gives richer offline drafts on a 24 GB Mac.

### 🎥 Speaker names from the video (OCR — no token, no account)

For **video-call recordings** (Google Meet or Teams), the active speaker's name
is shown on screen. The app reads those names with Apple's on-device Vision OCR
and labels each line of the transcript with whoever was speaking — **real names**,
**no HuggingFace token and no account**. All local. Providing the **Attendees**
list makes this rock-solid: OCR only accepts names that match an attendee.

After processing, a **Speaker names** panel shows the detected names; correct any
that look off and click **Apply names**. It never invents a name — segments it
can't read (e.g. during a screen-share) carry over the last known speaker.

> The Greek speech model (**large-v3-turbo**, ~570 MB) is downloaded once during
> setup, then transcription is fully offline.

Results are also saved to `~/Documents/MoM Outputs/<recording-name>-<timestamp>/`
(transcript + MoM). To stop the app, close the small launcher window.

> Prefer the terminal? `python3 server.py` does the same thing, and
> `./run_mom.sh /path/to/recording.mp4` runs the whole pipeline headless.

---

## 🤝 Share it with a colleague

Send them this **whole folder** (zip it). On their Mac, no commands needed:

1. Double-click **`Install MoM Generator.command`** — it installs everything
   (ffmpeg, WhisperX large-v3 in its own `uv` Python venv, Ollama + qwen2.5:7b).
   A few GB of downloads the first time, then permanent and offline.
2. Double-click **`Start MoM Generator.command`** (keep the small window it opens).

If macOS says it's from an *unidentified developer*: right-click it →
**Open** → **Open** (only needed once). The installer clears this for you.

### Not included: YouTube / link transcription
Pasting a YouTube link is a **personal-use add-on that is deliberately left out of
this build** — it would download and run YouTube's remote challenge-solver code and
read your browser cookies, which isn't appropriate to ship to a shared/legal
audience. This build transcribes **files you provide**. (The person who shared this
can enable links on their own machine.)

### Optional: audio-only speaker separation
Video calls need nothing extra. For **audio-only** recordings, speaker labels
require pyannote diarization, which needs a free HuggingFace token saved to
`~/.cache/mom-generator/config.json` as `{"hf_token":"..."}` (accept the terms at
huggingface.co/pyannote/speaker-diarization-community-1). Not needed for Meet/Teams.

---

## 🧩 What's in here

| File | Purpose |
|------|---------|
| `Install MoM Generator.command` | Double-click once to install everything |
| `Start MoM Generator.command` | Double-click launcher (starts the local web UI) |
| `server.py` | The web app + pipeline (Python standard library only — calls whisper.cpp/Ollama as subprocesses) |
| `Gemini MoM Prompt.md` | The reusable styling prompt that reproduces the MoM email look in Gemini every meeting |
| `RELEASE_NOTES.md` | What this tool does + what's new |
| `ocr_speakers.py` | Reads on-screen speaker names from the video (Apple Vision OCR) |
| `summarize_mom.py` | Step 3 helper (transcript → MoM via Ollama) |
| `run_mom.sh` | Headless CLI for the full pipeline |
| `setup.sh` | The actual installer (ffmpeg, WhisperX, Ollama, model) — run by the installer above |
| `~/.cache/mom-generator/` | WhisperX venv + `config.json` (your HuggingFace token) |

## 🔒 Privacy

Audio, transcripts, and minutes never leave the machine. Whisper and Ollama run
locally; the only network access is the **first-time** download of the tools and
models in `setup.sh`.

## 🛠 Troubleshooting

- **Banner says a tool is missing** → run `./setup.sh`, then reload the page.
- **"No Ollama model"** → `ollama pull qwen2.5:7b`.
- **Empty transcript** → the audio may be silent or the wrong language; check the
  language dropdown.
- **Long meeting cut off** → the model context is 16k tokens (~1.5–2 hrs of
  speech). For longer recordings, ask for chunking to be enabled.
