# 📝 MoM Generator — v1.3

**Turn a meeting recording into a polished, English Minutes‑of‑Meeting email — even if the meeting was in Greek — without anything leaving your Mac.**

Drop in a Google Meet / Teams recording. Out comes a clean transcript that already knows **who said what**, plus a beautifully styled MoM email ready to paste into Gmail. No cloud upload, no API keys, no per‑meeting cost.

---

## 🆕 What's new in v1.3 — minutes that reason, not just summarise

v1.2 made the minutes *look* right every time. v1.3 makes them *think* right every time. The gap between a readable summary and minutes people can act on is reasoning, and that reasoning is now written into every prompt path instead of living in the author's head.

### 🧠 A reasoning standard, enforced in all four prompts

Every prompt (Gemini, offline JSON, and both markdown paths) now carries the same twelve‑rule standard. The rules that change the output most:

- **Every discussion point resolves.** A topic ends in a decision — or, when nothing was settled, in the *decomposition*: the specific questions that must be answered first, who answers each, and what approval is needed. "This was discussed" is explicitly named as the failure mode to avoid.
- **The critical path gets named.** Usually one open item gates the rest; the minutes now say so in those terms and mark that item `Blocking` with an owner and a date.
- **Parallel tracks, so nobody is idle.** When a decision waits on someone outside the room, the minutes record what runs in the meantime, and why.
- **Scope is held.** What's in the MVP and what defers to a later phase are both stated — deferral is recorded as a decision, with the interim workaround.
- **Re‑opened decisions get their history restated** — the prior decision, its date, and the reason it was taken, before re‑litigating.
- **Ask for the number that decides.** "Some cases are complex" becomes an action item for the count or percentage, plus what that number decides.
- **Honest about the unknowable.** No invented confidence or fabricated effort ranges.
- **Ownership discipline.** Nothing commits DH/Central to a deliverable, date, or capability the transcript doesn't show them committing to themselves.

### 🚨 `Blocking` is no longer the same as `Blocked`

The distinction that tells the reader where to push:

- 🚨 **Blocking** — on the critical path; other work waits on *this*. Its own amber card.
- 🛑 **Blocked** — cannot start until something else is done; *this* is waiting.

Also new: ⏳ **Awaiting**, for items sitting with a third party where there is nothing for us to do.

### 🗂️ Action items in three groups

**New** → **Carried Forward** → **Closed**. The Closed group isn't padding — it's what shows the ledger moving, and it's what lets the opening line say "three open points closed; two new items now sit on the critical path." Empty groups are omitted.

### ✉️ A subject line you can copy

The generator now writes the subject too, in the form `[MoM] <workstream> — <DD/MM>: <what changed>` — the part after the colon states the *change*, not the topic. It appears above the preview with a Copy button.

### ➕ Also

- **Discussion headings carry the verdict** — `Declared Domain Ownership — New Blocker`, `Hosting Cluster — Re‑opened` — so the topic list alone reads as a status summary.
- **`Target:` line** on any discussion point with a resolution date.
- **`Also Discussed` section** for settled facts and low‑salience items, recorded with the reason they're there rather than dropped.
- **Due dates and gating conditions** on action items: a bare date renders as `Due 05/08`, a condition renders verbatim (`Gated on domain`, `After credentials`).
- **A closing cadence line**, so the default assumption isn't that everything waits for the next sync.
- **[`examples/reference-mom.md`](examples/reference-mom.md)** — a worked reference at the intended quality bar, annotated with which rule each passage demonstrates, plus a side‑by‑side of what a failing MoM looks like. Content is fictional; this repo is public.
- **Tests** covering grouping, status vocabulary, escaping, and a contract test asserting the prompts and the renderer agree on every field name — so a prompt edit can't silently start emitting fields the template drops.

---

## What's new in v1.2 — the screen share makes it into the notes

Meetings aren't only talk. When someone presents, **what was on screen is now part of the MoM** — and the transcript itself got noticeably sharper.

### 🖥️ Shared screens, captured automatically

- **Every distinct screen is saved.** The same on‑device pass that reads speaker names now spots when someone is sharing and saves one screenshot per screen — no clicking, no manual snipping. Showing the same dashboard again later doesn't create a duplicate.
- **Cropped to the content, like Gemini's notes.** The floating speaker tile is trimmed away, so you get the slide or dashboard, not a picture of someone's face.
- **You decide what appears.** A thumbnail strip on the results screen lets you untick anything that shouldn't reach the email.
- **Placed in context.** Screenshots land inside the discussion point they belong to, captioned with the timestamp and who was presenting. Unmatched ones collect in a "Shared screens" section.
- **Works both ways.** The offline MoM embeds the images directly; the Gemini prompt carries each screen's on‑screen text and opens the folder so you can drag the shots straight in.

### 🎯 Sharper transcripts

- **Key terms field.** Type the product names and jargon used in the call (`Salesforce`, `KYC`, …) and the transcriber is biased toward spelling them correctly instead of turning English terms into similar‑sounding Greek.
- **Garbled terms get repaired.** The MoM prompts now instruct the model to restore obviously mangled technical terms — and to leave the wording alone when it isn't sure.
- **No more junk speakers during screen‑shares.** Window titles and app text that merely *looked* like names ("Logs Table JSON", "Table Explorer") no longer become participants, and OCR misspellings of a real name merge into one person.
- **Faster again.** Fixed a regression where a portability change could make the app quietly fall back to the slow CPU transcriber. A 45‑minute meeting runs end‑to‑end in a few minutes on the GPU path.

### ✏️ Also

- The minutes now address the **efood / Foody** teams.
- **43 automated tests** cover the capture, cropping and naming logic.

---

## 🗒️ Previously in v1.1 — speaker names that never fail silently

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
- **Shows what was presented.** Shared screens are captured, cropped and placed next to the discussion they belong to.
- **100% private.** Audio, transcript, and minutes never leave the laptop.

## 🚦 Two ways to write the MoM — you pick per meeting

| | ✨ **Google Gemini** | 🔒 **Private & offline** |
|---|---|---|
| Best for | Highest quality + reading your **screenshots** | Confidential meetings, zero tokens |
| How | One click copies a ready‑made prompt → paste into Gemini → paste into Gmail | One click drafts the styled MoM with a local model on your Mac |
| Internet | Uses Gemini | **None** — fully offline |

Both produce the **same email styling** — only where the thinking happens changes.

## 🖥️ The app

- **Guided 1‑2‑3 flow:** ① choose a recording (drag‑drop *or* paste a local file path) → ② add attendees, key terms & context → ③ Generate.
- **Clear progress:** live "Extracting audio → Transcribing → Reading speaker names" stages with elapsed time.
- **Review speaker names** panel with autocomplete from your attendee list — fix any label in one click.
- **Shared screens strip:** tick the captures that belong in the email.
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
| **v1.2** | 2026‑07‑30 | Shared‑screen capture — distinct screens saved automatically, cropped to the presented content (speaker tile removed), picked from a thumbnail strip, embedded under the matching discussion point in the offline MoM and described in the Gemini prompt. Sharper transcripts: "Key terms" vocabulary bias, garbled‑term repair, no junk speakers from screen‑share text, OCR misspellings merged. Fixed a silent fallback to the slow CPU transcriber. MoM audience is efood/Foody. 43 tests. |
| **v1.1** | 2026‑07‑09 | Loud speaker‑naming (no silent failures); OCR decoupled from WhisperX (works on the whisper.cpp fast path); removed hardcoded path + auto‑discovery; job‑start capability preflight; keep segmented transcript on 0‑name runs; wider name capture (single first names, `Name (Company)`, `MOM_OCR_*` tuning); `--self-check`; unit tests. |
| **v1.0** | 2026‑07‑01 | First release — local Greek→English Minutes‑of‑Meeting: recording → whisper.cpp/WhisperX → on‑screen speaker naming (OCR) → Greek transcript → styled MoM (Gemini prompt or offline local model). Guided UI, speaker‑review panel, Copy‑for‑Gmail. |
