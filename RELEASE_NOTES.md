# 📝 MoM Generator — v1.0

**Turn a meeting recording into a polished, English Minutes‑of‑Meeting email — even if the meeting was in Greek — without anything leaving your Mac.**

Drop in a Google Meet / Teams recording. Out comes a clean transcript that already knows **who said what**, plus a beautifully styled MoM email ready to paste into Gmail. No cloud upload, no API keys, no per‑meeting cost.

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

## 🖥️ What's new in the app

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
Apple‑silicon Mac (M1–M4), ~15 GB free for the one‑time model downloads. Built for internal efood / DH Pay use.
