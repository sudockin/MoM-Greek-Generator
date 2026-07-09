<div align="center">

<img src="assets/hero.svg" alt="MoM Generator — Greek meeting recording → speaker-labelled transcript → styled Minutes of Meeting, 100% on-device" width="100%">

<br>

![Platform](https://img.shields.io/badge/platform-macOS%20Apple%20Silicon-111111)
![Privacy](https://img.shields.io/badge/privacy-100%25%20on--device-2ea44f)
![API keys](https://img.shields.io/badge/API%20keys-none-1d4ed8)
![Languages](https://img.shields.io/badge/Greek-%E2%86%92%20English-D81E2C)
![Runtime](https://img.shields.io/badge/python-stdlib%20only-3776AB)

**Drop in a meeting recording. Get back a transcript that already knows who said what — plus a polished Minutes-of-Meeting email ready to paste into Gmail. Nothing leaves your Mac.**

</div>

---

## Why it exists

Recording a call is easy; turning it into shareable minutes is the slog — especially when the meeting is in **Greek** and you need clean **English** notes with the right person against every decision. Cloud transcription means uploading confidential internal calls and paying per minute.

**MoM Generator does the whole thing locally.** ffmpeg extracts the audio, whisper.cpp transcribes it on the Apple GPU, Apple's on-device Vision OCR reads the on-screen speaker names, and you get a speaker-labelled transcript — then a styled MoM, either via a ready-made Gemini prompt or a fully-offline local model. No API keys, no upload, no per-meeting cost.

## What you get

- 🗣️ **Knows who spoke.** Reads the active-speaker name straight off Google Meet / Teams video (Apple Vision OCR) and labels every line — real names, no account, no token. It never invents a name.
- 🌐 **Greek in → English out.** Transcribes Greek accurately; the minutes come out in clear business English.
- ⚡ **Fast.** Runs `large-v3-turbo` on the Metal GPU — roughly **10× faster** than the old CPU path, same Greek quality. A 40-minute meeting is done in a few minutes.
- 🎨 **Consistent, beautiful output.** Every MoM lands in the same styled email — title, attendee chips, "Latest status", discussion cards, and colour-coded ✅ / 🔄 / 🛑 / ⬜ action items.
- 🔒 **Private by construction.** Audio, transcript, and minutes never leave the laptop. The only network access is the one-time setup download.
- 🖥️ **No terminal required.** Two double-clicks: install, then run. Opens in your browser.

<!--
  App screenshot: run  ./screenshots/capture.command  to generate screenshots/app-ready.png,
  then uncomment the block below (kept commented so the README never shows a broken image).

<div align="center">
<br>
<img src="screenshots/app-ready.png" alt="MoM Generator app — guided 1-2-3 flow" width="720">
<br>
<sub>The guided flow: choose a recording → add attendees → Generate.</sub>
</div>
-->

> **📸 See it in action:** run [`./screenshots/capture.command`](screenshots/) to render the
> live app UI (headless Chrome) into `screenshots/app-ready.png`, then uncomment the image
> block near the top of this README. Regenerated each release.

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

> **Before a long run**, the log prints a one-line **capability check** — engine in use,
> whether on-screen speaker names are possible, and whether audio diarization is available —
> so you know up front what to expect. Run `python3 server.py --self-check` for the same
> report without processing a file.

### 🎥 Speaker names from the video (OCR — no token, no account)

For **video-call recordings** (Google Meet or Teams), the active speaker's name
is shown on screen. The app reads those names with Apple's on-device Vision OCR
and labels each line of the transcript with whoever was speaking — **real names**,
**no HuggingFace token and no account**. All local. Providing the **Attendees**
list makes this rock-solid: OCR only accepts names that match an attendee (it now
also matches single first names and `Name (Company)` tags).

After processing, a **Speaker names** panel shows the detected names; correct any
that look off and click **Apply names**. It never invents a name — segments it
can't read (e.g. during a screen-share) carry over the last known speaker. If OCR
can't run or matches nothing, the log says exactly why and you still get a clean
segmented transcript.

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
   (ffmpeg, whisper.cpp + the Greek model, Apple Vision OCR, and Ollama + qwen2.5:7b).
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

### Tuning OCR for unusual layouts
The name-detection geometry is overridable via env vars (`MOM_OCR_RIGHT_MIN_X`,
`MOM_OCR_TEAMS_MAX_X`, `MOM_OCR_MIN_H`/`MAX_H`, `MOM_OCR_BOTTOM_MAX_Y`,
`MOM_OCR_ROSTER_MIN`) if a particular meeting client places name tags differently.

---

## 🧩 What's in here

| File | Purpose |
|------|---------|
| `Install MoM Generator.command` | Double-click once to install everything |
| `Start MoM Generator.command` | Double-click launcher (starts the local web UI) |
| `server.py` | The web app + pipeline (Python standard library only — calls whisper.cpp/Ollama as subprocesses) |
| `ocr_speakers.py` | Reads on-screen speaker names from the video (Apple Vision OCR) |
| `summarize_mom.py` | Step 3 helper (transcript → MoM via Ollama) |
| `Gemini MoM Prompt.md` | The reusable styling prompt that reproduces the MoM email look in Gemini every meeting |
| `run_mom.sh` | Headless CLI for the full pipeline |
| `setup.sh` | The actual installer (ffmpeg, whisper.cpp, Apple Vision OCR, Ollama, model) |
| `test_speaker_naming.py` | Unit tests for the OCR / model-discovery / overwrite-guard logic |
| `screenshots/` | Product screenshot + `capture.command` (regenerated each release) |
| `RELEASE_NOTES.md` | What's new, per version, with version history |
| `~/.cache/mom-generator/` | OCR/WhisperX venv + `config.json` (optional HuggingFace token) |

## 🔒 Privacy

Audio, transcripts, and minutes never leave the machine. whisper.cpp, the OCR, and
Ollama all run locally; the only network access is the **first-time** download of the
tools and models in `setup.sh`. Aligned with GDPR expectations for handling internal
meeting content.

## 🛠 Troubleshooting

- **Banner says a tool is missing** → run `./setup.sh`, then reload the page.
- **No speaker names on a video** → the log now says why (no `ocrmac`, 0 names matched,
  etc.). Add the **Attendees** list to lock detection onto real names.
- **"No Ollama model"** → `ollama pull qwen2.5:7b` (only needed for the offline MoM draft).
- **Empty transcript** → the audio may be silent or the wrong language; check the
  language dropdown.
- **Long meeting cut off** → the model context is 16k tokens (~1.5–2 hrs of
  speech). For longer recordings, ask for chunking to be enabled.

---

<div align="center">
<sub>Built for internal efood / Foody / Delivery Hero use · Apple-silicon Mac (M1–M4), ~15 GB free for one-time model downloads</sub>
</div>
