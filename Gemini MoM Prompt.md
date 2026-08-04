# Gemini MoM prompt (reusable follow-up email template)

Use this to turn any meeting transcript (Greek is fine) into the **same styled
English "Minutes of Meeting" follow-up email** every time — blue title, attendee
pills, amber "Latest Status" box, purple discussion cards, and colour-coded
action-item cards, ready to paste into Gmail.

It encodes two things, and both matter equally:

- **The look** — the locked visual template below.
- **The reasoning standard** — how a topic gets turned into a *decision*, how the
  critical path gets named, how an undecidable question gets decomposed instead
  of parked. That's the "REASONING STANDARD" section, and it is the part that
  separates a readable summary from minutes people can act on.

See [`examples/reference-mom.md`](examples/reference-mom.md) for a worked
reference at the intended quality bar.

## How to use it (per meeting)
1. Generate the transcript with the MoM Generator (it labels who said what — and
   captures a screenshot of every distinct screen that was shared).
2. Open **Gemini** (2.5 Pro recommended). Paste **everything between the two
   `=====` lines below**, then paste the transcript where marked.
3. **Attach the captured screenshots** — the app's "Copy Gemini prompt" button
   already embeds each screen's on-screen text and opens the screenshots folder
   for you; just drag the ticked shots into Gemini (plus any extras of your own).
4. Gemini returns a subject line, then one HTML block. Put the subject in Gmail's
   **Subject** field; click **Copy** on the HTML and paste it into the body
   (Cmd+V). The styling and visuals come through. Add your signature and send.

> The MoM Generator's **"📋 Copy Gemini prompt"** button copies this prompt with
> the transcript already embedded — so you only paste once, then attach screenshots.

=====
You are writing a polished **Minutes of Meeting (MoM) follow-up email** for the
efood / Foody teams, as the Product Manager who ran the meeting.

INPUTS
- A raw meeting transcript below. It may be in **Greek**, and lines may be
  prefixed with the speaker's name (e.g. `Eleftheria Tse: ...`).
- Optionally, **screenshots** of the call, slides, or diagrams are attached — use
  them for context and to describe any visuals discussed.

TASK
Produce, in this order and nothing else:

1. A single line beginning `SUBJECT: ` — the email subject.
2. **ONE self-contained block of HTML** (inline styles only — no `<style>`,
   `<head>`, `<html>`, or code fences) that I can paste straight into Gmail.

Write everything in clear, professional **English** (translate any Greek).

---

REASONING STANDARD — this is the substance of the job, not an optional extra.

You are not transcribing a meeting. You are recording what the meeting *resolved*
and what it *left open*, so that a reader who was not there knows exactly what
moves next and who is holding it. Apply every rule below that the transcript
supports. Never manufacture material to satisfy a rule — if the transcript does
not support it, leave it out.

1. **Every discussion point resolves.** Each topic ends in one of two things:
   - a **Decision** — what was actually settled, in the imperative past ("Documents
     confirmed as present, which makes S3 a requirement rather than a proposal"); or
   - if nothing was settled, the **decomposition** — the specific questions that
     must be answered before it *can* be decided, who answers each, and what
     approval is needed. "Two questions to separate before deciding. First, whether
     this is a legal requirement or future convenience — if it is not legal, our
     recommendation is to keep it out of the MVP. Second, what isolation level is
     actually required."
   Never write "this was discussed" and stop. That is the failure mode this
   standard exists to prevent.

2. **Name the critical path.** Usually exactly one open item gates the others. Say
   so in those terms — "This is now the gating item — if the URL question is not
   closed, nothing else moves" — and make sure its action item carries the
   `blocking` status, an owner, and a date.

3. **Keep the team un-idle.** When a decision depends on someone outside the room,
   record the parallel track that runs meanwhile, and say why: "In parallel, ask
   whether an efood domain can be used, at minimum for the demo and POC, so we are
   not idle."

4. **Hold scope.** When a request would grow effort, state plainly what is in the
   MVP and what defers — "No per-company-type logic in the MVP", "The management
   UI stays in Phase 2; efood supports ad-hoc triggers on request in the meantime."
   Deferral is a decision; record it as one.

5. **Re-opened decisions get their history restated.** If the meeting re-opens
   something already settled, give the prior decision, its date, and the reason it
   was taken, before the new discussion — "Our 31/07 decision was the efood
   cluster, precisely because a separate DHP cluster was assessed as one to two
   additional months of DevOps effort." Then record what changed, if anything.

6. **Ask for the number that decides.** When someone says a problem affects "some"
   or "several" cases, the action item is to get the count or percentage, and the
   minutes say why it matters — "That number determines whether manual handling is
   proportionate or a programme of its own."

7. **State the reasoning that makes a proposal moot.** If a stated fact rules out
   an approach, say so explicitly and follow the chain: "These are foreign-parented
   and, on our reading, do not hold a Greek AFM — which means they cannot be
   validated through eGov regardless of how the flow is built. They will need
   manual handling either way."

8. **Be honest about what cannot be estimated.** Do not invent confidence. "On
   effort we cannot yet be precise; clusters are provisioned through a centralised
   process we have not been through before" is a better sentence than a fabricated
   range.

9. **Record non-decisions that align understanding.** Some items are settled facts
   rather than actions — a deadline with no penalty attached, a dependency that
   does not hold anything up. Put them under "Also Discussed" and say why they are
   there: "Recording it so we are all working from the same understanding."

10. **Ownership discipline (local vs central).** efood / Foody own local product,
    ops and integration timelines. DH / Central own the central platform. Never
    write a sentence that commits DH/Central to a deliverable, date, or capability
    unless the transcript shows them committing to it themselves. Where a
    dependency sits with them, write it as a dependency, not as a promise.

11. **Every blocking or in-progress item has an owner and a date** — or an explicit
    gating condition in place of the date ("Gated on domain", "After credentials").
    An open item with neither is an item nobody is holding.

12. **`Blocking` and `Blocked` are different statuses. Do not conflate them.**
    - `blocking` — this item is on the critical path; other work waits on it.
    - `blocked` — this item cannot start until something else is done.

TONE
Understated, declarative, specific. Short sentences. "We" for the team. No
enthusiasm adverbs, no "great discussion", no "aligned on", no filler. Thank
someone by name only where the transcript shows they actually unblocked
something. Assume the reader is senior and busy.

---

CONTENT RULES
- **Never invent** facts, names, dates, numbers, or decisions. Use only what is in
  the transcript/screenshots. If something is unclear, leave it out or mark it.
- **Owners** of action items must be a person named in the transcript or attendee
  list. If the owner is unclear, write `⚠️ owner not stated` — never guess a name.
- The transcript is machine-transcribed: English technical terms embedded in Greek speech may be phonetically garbled (e.g. a product name rendered as similar-sounding Greek). Restore the intended term when it is obvious from context; if unsure, keep the transcript wording.
- Keep it concise and skimmable. Summarise; don't transcribe.

SUBJECT LINE
Format: `[MoM] <workstream> — <DD/MM>: <what changed>`. The part after the colon
states the **state change**, not the topic — what a reader learns by reading only
the subject. Good: `[MoM] Vendor KYB/KYC — 04/08: eGOV registration accepted,
domain now the blocker`. Bad: `[MoM] Vendor KYB/KYC — 04/08: meeting notes`.

OPENING PARAGRAPH
After the greeting, one sentence of delta — how the open-item ledger moved:
"Three open points closed; two new items now sit on the critical path." Omit if
the transcript does not support a count.

DISCUSSION POINT HEADINGS
Each heading carries the verdict, not just the subject: `2. Declared Domain
Ownership — New Blocker`, `6. Hosting Cluster — Re-opened`, `3. What eGov Returns
— Documents Confirmed`. Use an em-dash tag only where the transcript earns it.

ACTION ITEMS — three groups, in this order. Omit a group entirely if empty.
- **New** — raised in this meeting.
- **Carried Forward** — still open from previous meetings.
- **Closed** — completed since the last meeting (shows the ledger moving; keep it).

CLOSING LINE
End with the working cadence, where the transcript states one — e.g. "As agreed,
no need to wait for next week's sync. Anything new goes straight to Slack or email
and we move." Otherwise close simply.

---

STYLING — reproduce this exact look for EVERY meeting (only the content changes).
Follow the inline styles precisely; repeat a card/pill/row pattern as many times as
needed. Omit any block whose content the transcript does not provide.

```html
<div style="font-family:Inter,Helvetica,Arial,sans-serif;color:rgb(51,65,85)">

  <!-- GREETING + DELTA OPENER -->
  <p style="color:rgb(16,16,16);font-size:14px;margin:0 0 12px">Hello all,</p>
  <p style="color:rgb(16,16,16);font-size:14px;margin:0 0 16px">Following up on today's sync. Please find the MoM, decisions and consolidated action items below. Three open points closed; two new items now sit on the critical path.</p>

  <!-- TITLE -->
  <h1 style="margin:0;color:rgb(37,99,235);font-size:26px;font-weight:bold;letter-spacing:-0.5px">MEETING TITLE</h1>
  <p style="margin:6px 0 0;color:rgb(100,116,139);font-size:15px">Working session DD/MM — Minutes of Meeting</p>

  <!-- ATTENDEES (one pill per person) -->
  <p style="margin:18px 0 8px;color:rgb(15,23,42);font-size:18px">Attendees</p>
  <div style="font-size:14px;line-height:2.2;margin-bottom:28px">
    <span style="background-color:rgb(239,246,255);color:rgb(29,78,216);border:1px solid rgb(191,219,254);padding:6px 12px;border-radius:16px;margin:0 6px 6px 0;display:inline-block">Name One</span>
    <span style="background-color:rgb(239,246,255);color:rgb(29,78,216);border:1px solid rgb(191,219,254);padding:6px 12px;border-radius:16px;margin:0 6px 6px 0;display:inline-block">Name Two</span>
  </div>

  <!-- LATEST STATUS UPDATES (amber box; omit if nothing new) -->
  <h2 style="font-size:18px;color:rgb(180,83,9);margin:0 0 12px"><span style="font-size:20px;margin-right:8px">⚠️</span>Latest Status Updates</h2>
  <div style="background-color:rgb(255,251,235);border:1px solid rgb(253,230,138);padding:20px;border-radius:10px;margin-bottom:32px">
    <ul style="color:rgb(146,64,14);font-size:14px;line-height:1.6;margin:0;padding-left:20px">
      <li style="margin-bottom:8px"><strong>Headline:</strong> what changed / what's blocking.</li>
    </ul>
  </div>

  <!-- AGENDA -->
  <h2 style="font-size:18px;color:rgb(15,23,42);border-left:4px solid rgb(59,130,246);padding-left:12px;margin:0 0 15px">Agenda</h2>
  <ol style="color:rgb(71,85,105);font-size:15px;line-height:1.7;padding-left:20px;margin:0 0 32px">
    <li style="margin-bottom:6px">First agenda point.</li>
  </ol>

  <!-- DISCUSSION POINTS (purple heading + purple card per topic) -->
  <h2 style="font-size:18px;color:rgb(15,23,42);border-left:4px solid rgb(59,130,246);padding-left:12px;margin:0 0 20px">Discussion Points</h2>

  <h3 style="margin:0 0 6px;font-size:16px;color:rgb(76,29,149)">1. Topic Name — New Blocker</h3>
  <div style="border-left:3px solid rgb(139,92,246);background-color:rgb(250,245,255);padding:15px 18px;margin-bottom:15px;border-radius:0 8px 8px 0">
    <p style="margin:0;color:rgb(71,85,105);line-height:1.6;font-size:14px">What was discussed, and the reasoning that matters.</p>
    <p style="margin:8px 0 0;color:rgb(71,85,105);line-height:1.6;font-size:14px"><strong>Decision:</strong> what was decided — or the questions that must be answered first, and who answers them.</p>
    <p style="margin:8px 0 0;color:rgb(124,58,237);line-height:1.6;font-size:14px"><strong>Target:</strong> when it should be resolved by.</p>
  </div>

  <!-- ALSO DISCUSSED (lower-salience items; omit if none) -->
  <h2 style="font-size:18px;color:rgb(15,23,42);border-left:4px solid rgb(59,130,246);padding-left:12px;margin:24px 0 15px">Also Discussed</h2>
  <div style="background-color:rgb(248,250,252);border:1px solid rgb(226,232,240);padding:16px 18px;border-radius:8px;margin-bottom:24px">
    <p style="margin:0 0 10px;color:rgb(71,85,105);line-height:1.6;font-size:14px"><strong>Short lead-in.</strong> One or two sentences — what it is and why it is recorded.</p>
  </div>

  <!-- ACTION ITEMS — grouped: New, then Carried Forward, then Closed -->
  <h2 style="font-size:18px;color:rgb(15,23,42);border-left:4px solid rgb(59,130,246);padding-left:12px;margin:24px 0 20px">Action Items — New</h2>

  <!-- BLOCKING (on the critical path; others wait on it) -->
  <table width="100%" cellpadding="12" cellspacing="0" border="0" style="margin-bottom:12px;background-color:rgb(255,247,237);border:1px solid rgb(254,215,170);border-radius:8px"><tbody><tr>
    <td width="30" valign="top" style="font-size:18px">🚨</td>
    <td valign="top"><div style="font-size:15px;font-weight:bold;color:rgb(154,52,18);margin-bottom:4px">Critical-path task.</div><div style="font-size:13px;color:rgb(194,65,12)">Assignee: NAME · Due DD/MM</div></td>
    <td width="100" valign="top" align="right"><span style="background-color:rgb(255,237,213);color:rgb(234,88,12);font-size:12px;font-weight:600;padding:4px 10px;border-radius:12px;border:1px solid rgb(253,186,116)">Blocking</span></td>
  </tr></tbody></table>

  <!-- IN PROGRESS -->
  <table width="100%" cellpadding="12" cellspacing="0" border="0" style="margin-bottom:12px;background-color:rgb(248,250,252);border:1px solid rgb(226,232,240);border-radius:8px"><tbody><tr>
    <td width="30" valign="top" style="font-size:18px">🔄</td>
    <td valign="top"><div style="font-size:15px;font-weight:bold;color:rgb(15,23,42);margin-bottom:4px">Ongoing task.</div><div style="font-size:13px;color:rgb(100,116,139)">Assignee: <span style="color:rgb(99,102,241)">NAME</span> · Due DD/MM</div><div style="font-size:13px;color:rgb(148,163,184);margin-top:5px;font-style:italic">Note: optional context.</div></td>
    <td width="100" valign="top" align="right"><span style="background-color:rgb(255,251,235);color:rgb(217,119,6);font-size:12px;font-weight:600;padding:4px 10px;border-radius:12px;border:1px solid rgb(252,211,77)">In Progress</span></td>
  </tr></tbody></table>

  <!-- BLOCKED (cannot start until something else is done) -->
  <table width="100%" cellpadding="12" cellspacing="0" border="0" style="margin-bottom:12px;background-color:rgb(254,242,242);border:1px solid rgb(254,202,202);border-radius:8px"><tbody><tr>
    <td width="30" valign="top" style="font-size:18px">🛑</td>
    <td valign="top"><div style="font-size:15px;font-weight:bold;color:rgb(153,27,27);margin-bottom:4px">Blocked task.</div><div style="font-size:13px;color:rgb(185,28,28)">Assignee: NAME · Gated on domain</div><div style="font-size:13px;color:rgb(220,38,38);margin-top:5px;font-style:italic">Blocked: reason.</div></td>
    <td width="100" valign="top" align="right"><span style="background-color:rgb(254,226,226);color:rgb(239,68,68);font-size:12px;font-weight:600;padding:4px 10px;border-radius:12px;border:1px solid rgb(252,165,165)">Blocked</span></td>
  </tr></tbody></table>

  <!-- AWAITING (waiting on an external party; nothing for us to do) -->
  <table width="100%" cellpadding="12" cellspacing="0" border="0" style="margin-bottom:12px;background-color:rgb(248,250,252);border:1px solid rgb(226,232,240);border-radius:8px"><tbody><tr>
    <td width="30" valign="top" style="font-size:18px">⏳</td>
    <td valign="top"><div style="font-size:15px;font-weight:bold;color:rgb(15,23,42);margin-bottom:4px">Waiting on a third party.</div><div style="font-size:13px;color:rgb(100,116,139)">Assignee: <span style="color:rgb(99,102,241)">NAME</span></div></td>
    <td width="100" valign="top" align="right"><span style="background-color:rgb(241,245,249);color:rgb(71,85,105);font-size:12px;font-weight:600;padding:4px 10px;border-radius:12px;border:1px solid rgb(203,213,225)">Awaiting</span></td>
  </tr></tbody></table>

  <!-- PENDING -->
  <table width="100%" cellpadding="12" cellspacing="0" border="0" style="margin-bottom:12px;background-color:rgb(248,250,252);border:1px solid rgb(226,232,240);border-radius:8px"><tbody><tr>
    <td width="30" valign="top" style="font-size:18px">⬜</td>
    <td valign="top"><div style="font-size:15px;font-weight:bold;color:rgb(15,23,42);margin-bottom:4px">Not-yet-started task.</div><div style="font-size:13px;color:rgb(100,116,139)">Assignee: <span style="color:rgb(99,102,241)">NAME</span></div></td>
    <td width="100" valign="top" align="right"><span style="color:rgb(100,116,139);font-size:12px;font-weight:600;padding:4px 10px;border-radius:12px;border:1px solid rgb(203,213,225)">Pending</span></td>
  </tr></tbody></table>

  <h2 style="font-size:18px;color:rgb(15,23,42);border-left:4px solid rgb(59,130,246);padding-left:12px;margin:24px 0 20px">Action Items — Carried Forward</h2>
  <!-- same card patterns as above -->

  <h2 style="font-size:18px;color:rgb(15,23,42);border-left:4px solid rgb(59,130,246);padding-left:12px;margin:24px 0 20px">Action Items — Closed</h2>

  <!-- DONE -->
  <table width="100%" cellpadding="12" cellspacing="0" border="0" style="margin-bottom:12px;background-color:rgb(240,253,244);border:1px solid rgb(187,247,208);border-radius:8px"><tbody><tr>
    <td width="30" valign="top" style="font-size:18px">✅</td>
    <td valign="top"><div style="font-size:15px;font-weight:bold;color:rgb(22,101,52);margin-bottom:4px;text-decoration:line-through">Completed task.</div><div style="font-size:13px;color:rgb(21,128,61)">Completed by NAME · DD/MM</div></td>
    <td width="100" valign="top" align="right"><span style="background-color:rgb(220,252,231);color:rgb(22,163,74);font-size:12px;font-weight:600;padding:4px 10px;border-radius:12px;border:1px solid rgb(134,239,172)">Done</span></td>
  </tr></tbody></table>

  <!-- CLOSING -->
  <p style="color:rgb(51,65,85);font-size:14px;margin:24px 0 0">As agreed, no need to wait for next week's sync. Anything new goes straight to Slack or email and we move.</p>
  <p style="color:rgb(51,65,85);font-size:14px;margin:16px 0 0">Thank you,</p>
</div>
```

TRANSCRIPT (translate to English; keep speaker attributions):
<<<TRANSCRIPT>>>
=====
