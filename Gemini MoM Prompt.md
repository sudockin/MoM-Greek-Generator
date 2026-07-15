# Gemini MoM prompt (reusable follow-up email template)

Use this to turn any meeting transcript (Greek is fine) into the **same styled
English "Minutes of Meeting" follow-up email** every time — blue title, attendee
pills, amber "Latest Status" box, purple discussion cards, and colour-coded
action-item cards, ready to paste into Gmail.

## How to use it (per meeting)
1. Generate the transcript with the MoM Generator (it labels who said what).
2. Open **Gemini** (2.5 Pro recommended). Paste **everything between the two
   `=====` lines below**, then paste the transcript where marked.
3. **Attach your screenshots** (slides, diagrams, the Meet window) so Gemini can
   pull visuals/context into the notes.
4. Gemini returns one HTML block. Click **Copy**, then in Gmail paste it into the
   body (Cmd+V). The styling and visuals come through. Add your signature and send.

> The MoM Generator's **"📋 Copy Gemini prompt"** button copies this prompt with
> the transcript already embedded — so you only paste once, then attach screenshots.

=====
You are writing a polished **Minutes of Meeting (MoM) follow-up email** for the
efood / Foody teams.

INPUTS
- A raw meeting transcript below. It may be in **Greek**, and lines may be
  prefixed with the speaker's name (e.g. `Eleftheria Tse: ...`).
- Optionally, **screenshots** of the call, slides, or diagrams are attached — use
  them for context and to describe any visuals discussed.

TASK
Produce **ONE self-contained block of HTML** (inline styles only — no `<style>`,
`<head>`, `<html>`, or code fences) that I can paste straight into Gmail. Write
everything in clear, professional **English** (translate any Greek).

CONTENT RULES
- **Never invent** facts, names, dates, numbers, or decisions. Use only what is in
  the transcript/screenshots. If something is unclear, leave it out or mark it.
- **Owners** of action items must be a person named in the transcript or attendee
  list. If the owner is unclear, write `⚠️ owner not stated` — never guess a name.
- Preserve the **efood/Foody (local) ↔ DH / Central (global)** ownership nuance;
  do not commit DH/Central to capabilities that were not actually stated.
- Keep it concise and skimmable. Summarise; don't transcribe.

STYLING — reproduce this exact look for EVERY meeting (only the content changes).
Follow the inline styles precisely; repeat a card/pill/row pattern as many times as
needed. Omit the "Latest Status Updates" box if there is nothing new to report.

```html
<div style="font-family:Inter,Helvetica,Arial,sans-serif;color:rgb(51,65,85)">

  <!-- GREETING (edit freely) -->
  <p style="color:rgb(16,16,16);font-size:14px;margin:0 0 12px">Hello all,</p>
  <p style="color:rgb(16,16,16);font-size:14px;margin:0 0 16px">Following up on our sync — sharing the MoM below along with the action items.</p>

  <!-- TITLE -->
  <h1 style="margin:0;color:rgb(37,99,235);font-size:26px;font-weight:bold;letter-spacing:-0.5px">MEETING TITLE</h1>
  <p style="margin:6px 0 0;color:rgb(100,116,139);font-size:15px">Short subtitle — Minutes of Meeting</p>

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

  <h3 style="margin:0 0 6px;font-size:16px;color:rgb(76,29,149)">1. Topic Name</h3>
  <div style="border-left:3px solid rgb(139,92,246);background-color:rgb(250,245,255);padding:15px 18px;margin-bottom:15px;border-radius:0 8px 8px 0">
    <p style="margin:0;color:rgb(71,85,105);line-height:1.6;font-size:14px">Summary of what was discussed. <strong>Decision:</strong> what was decided.</p>
  </div>

  <!-- ACTION ITEMS (one table per item; pick the matching status style) -->
  <h2 style="font-size:18px;color:rgb(15,23,42);border-left:4px solid rgb(59,130,246);padding-left:12px;margin:24px 0 20px">Action Items</h2>

  <!-- DONE -->
  <table width="100%" cellpadding="12" cellspacing="0" border="0" style="margin-bottom:12px;background-color:rgb(240,253,244);border:1px solid rgb(187,247,208);border-radius:8px"><tbody><tr>
    <td width="30" valign="top" style="font-size:18px">✅</td>
    <td valign="top"><div style="font-size:15px;font-weight:bold;color:rgb(22,101,52);margin-bottom:4px;text-decoration:line-through">Completed task.</div><div style="font-size:13px;color:rgb(21,128,61)">Completed by NAME.</div></td>
    <td width="100" valign="top" align="right"><span style="background-color:rgb(220,252,231);color:rgb(22,163,74);font-size:12px;font-weight:600;padding:4px 10px;border-radius:12px;border:1px solid rgb(134,239,172)">Done</span></td>
  </tr></tbody></table>

  <!-- IN PROGRESS -->
  <table width="100%" cellpadding="12" cellspacing="0" border="0" style="margin-bottom:12px;background-color:rgb(248,250,252);border:1px solid rgb(226,232,240);border-radius:8px"><tbody><tr>
    <td width="30" valign="top" style="font-size:18px">🔄</td>
    <td valign="top"><div style="font-size:15px;font-weight:bold;color:rgb(15,23,42);margin-bottom:4px">Ongoing task.</div><div style="font-size:13px;color:rgb(100,116,139)">Assignee: <span style="color:rgb(99,102,241)">NAME</span></div><div style="font-size:13px;color:rgb(148,163,184);margin-top:5px;font-style:italic">Note: optional context.</div></td>
    <td width="100" valign="top" align="right"><span style="background-color:rgb(255,251,235);color:rgb(217,119,6);font-size:12px;font-weight:600;padding:4px 10px;border-radius:12px;border:1px solid rgb(252,211,77)">In Progress</span></td>
  </tr></tbody></table>

  <!-- BLOCKED -->
  <table width="100%" cellpadding="12" cellspacing="0" border="0" style="margin-bottom:12px;background-color:rgb(254,242,242);border:1px solid rgb(254,202,202);border-radius:8px"><tbody><tr>
    <td width="30" valign="top" style="font-size:18px">🛑</td>
    <td valign="top"><div style="font-size:15px;font-weight:bold;color:rgb(153,27,27);margin-bottom:4px">Blocked task.</div><div style="font-size:13px;color:rgb(185,28,28)">Assignee: NAME</div><div style="font-size:13px;color:rgb(220,38,38);margin-top:5px;font-style:italic">Blocked: reason.</div></td>
    <td width="100" valign="top" align="right"><span style="background-color:rgb(254,226,226);color:rgb(239,68,68);font-size:12px;font-weight:600;padding:4px 10px;border-radius:12px;border:1px solid rgb(252,165,165)">Blocked</span></td>
  </tr></tbody></table>

  <!-- PENDING -->
  <table width="100%" cellpadding="12" cellspacing="0" border="0" style="margin-bottom:12px;background-color:rgb(248,250,252);border:1px solid rgb(226,232,240);border-radius:8px"><tbody><tr>
    <td width="30" valign="top" style="font-size:18px">⬜</td>
    <td valign="top"><div style="font-size:15px;font-weight:bold;color:rgb(15,23,42);margin-bottom:4px">Not-yet-started task.</div><div style="font-size:13px;color:rgb(100,116,139)">Assignee: <span style="color:rgb(99,102,241)">NAME</span></div></td>
    <td width="100" valign="top" align="right"><span style="color:rgb(100,116,139);font-size:12px;font-weight:600;padding:4px 10px;border-radius:12px;border:1px solid rgb(203,213,225)">Pending</span></td>
  </tr></tbody></table>

  <!-- CLOSING -->
  <p style="color:rgb(51,65,85);font-size:14px;margin:20px 0 0">Thank you,</p>
</div>
```

TRANSCRIPT (translate to English; keep speaker attributions):
<<<TRANSCRIPT>>>
=====
