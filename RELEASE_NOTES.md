# 📝 MoM Generator — v1.1

**Turn a meeting recording into a polished, English Minutes‑of‑Meeting email — even if the meeting was in Greek — without anything leaving your Mac.**

Drop in a Google Meet / Teams recording. Out comes a clean transcript that already knows **who said what**, plus a beautifully styled MoM email ready to paste into Gmail. No cloud upload, no API keys, no per‑meeting cost.

---

## 🆕 What's new in v1.1 — speaker names that never fail silently

v1.0 could quietly produce a **nameless** transcript when on‑screen speaker naming (OCR) hit a snag — and you'd only find out after the run. v1.1 makes naming **loud, robust, and easier to get right**.

- **No more silent failures.** Every reason naming can't run now shows up in the launcher log as a plain‑English line — missing OCR module, missing timestamps, no `ocrmac`, the OCR step erroring out, or simply **0 names matched** on screen. The run still finishes with a transcript.
- **Naming works on the fast (whisper.cpp) path.** OCR needs Apple Vision (`ocrmac`), *not* WhisperX — so it's now decoupled from the WhisperX environment and picks whichever Python has `ocrmac`. A whisper.cpp‑only Mac can label speakers; a Mac missing `ocrmac` gets a one‑line install hint instead of a blank.
- **Up‑front capability check.** At the start of every job the log states the engine in use, whether **on‑screen names** are possible, and whether **audio diarization** is available — *before* a long transcription runs.
- **Better transcript kept on a miss.** When OCR matches zero names, the neatly **segmented** transcript is preserved instead of being replaced by one nameless blob.
- **Catches more names.** Recognises single first‑name tags (e.g. just “Alex”) and `Name (Company)` labels when you supply an attendee list, and the geometry gates are tunable via `MOM_OCR_*` env vars for unusual meeting layouts.
- **Portable install.** Removed a hardcoded developer path; whisper.cpp is now auto‑discovered (env var → Homebrew/`~/.cache` → `PATH`). `setup.sh` installs `ocrmac` on its own so the fast path always gets it.
- **New:** `python3 server.py --self-check` prints detected engine, `ocrmac` availability and model discovery **without** processing a file. Added unit tests for the pure OCR/discovery logic.

📸 See [`screenshots/`](screenshots/) for the current app UI (and how it's captured each release).

---

## ✨ Why people like it

- **Greek in → English out.** Records in Greek, writes the minutes in clear business English.
- **Knows who spoke.** Reads the active‑speaker name straight off the video (Apple Vision OCR) and labels every line — no accounts, no tokens, real names only.
- **Fast.** Transcription runs on your Mac's GPU (whisper.cpp · large‑v3‑turbo) — a 40‑minute meeting is done in a few minutes.
- **Beautiful, consistent output.** Every MoM comes out in the same styled email format — title, attendee chips, "Latest status", discussion cards, and colour‑coded ✅ / 🔄 / 🛑 / ⬜ action items.
- **100% private.** Audio, transcript, and minutes never leave the laptop.

## 🚦 Two ways to write the MoM — you pick per meeting

| | ✨ **Google Gemini** | 🔒 **Private & offline** |
|---|---|---|
| Best for | Highest quality + reading your **screenshots** | Confidential meetings, zero tokens |
| How | One click copies a ready‑made prompt → paste into Gemini → paste into Gmail | One click drafts the styled MoM with a local model on your Mac |
| Internet | Uses Gemini | **None** — fully offline |

Both produce the **same email styling** — only where the thinking happens changes.

## 🖥️ The app

- **Guided 1‑2‑3 flow:** ① choose a recording (drag‑drop *or* paste a local file path) → ② add attendees & context → ③ Generate.
- **Clear progress:** live "Extracting audio → Transcribing → Reading speaker names" stages with elapsed time.
- **Review speaker names** panel with autocomplete from your attendee list — fix any label in one click.
- **Result actions that make sense:** **Copy for Gmail** front and centre, plus Download, Save as PDF, and Open folder.
- **Fresh light‑first design** in the efood palette.

## 🔒 Privacy

Everything runs on your machine — ffmpeg, the speech model, the OCR, and the local LLM. The only time it touches the network is the **one‑time** setup download of the tools and models.

---

## 🚀 Get started

1. **Install once:** double‑click `Install MoM Generator.command` and wait for "All set!".
2. **Run:** double‑click `Start MoM Generator.command` — your browser opens the tool.
3. Add a recording, enter the attendees, and click **Generate**.

Full details, sharing instructions, and troubleshooting are in [`README.md`](README.md).

---

### Requirements
Apple‑silicon Mac (M1–M4), ~15 GB free for the one‑time model downloads. Built for internal efood / Foody use.

---

## 🗂️ Version history

| Version | Date | Highlights |
|---|---|---|
| **v1.1** | 2026‑07‑09 | Loud speaker‑naming (no silent failures); OCR decoupled from WhisperX (works on the whisper.cpp fast path); removed hardcoded path + auto‑discovery; job‑start capability preflight; keep segmented transcript on 0‑name runs; wider name capture (single first names, `Name (Company)`, `MOM_OCR_*` tuning); `--self-check`; unit tests. |
| **v1.0** | 2026‑07‑01 | First release — local Greek→English Minutes‑of‑Meeting: recording → whisper.cpp/WhisperX → on‑screen speaker naming (OCR) → Greek transcript → styled MoM (Gemini prompt or offline local model). Guided UI, speaker‑review panel, Copy‑for‑Gmail. |
