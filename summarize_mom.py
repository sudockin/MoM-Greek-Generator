#!/usr/bin/env python3
"""Step 3 of the local no-token MoM pipeline.

Reads a Greek transcript, sends it to a local Ollama model, and writes a
structured English MoM. Uses the Ollama HTTP API directly so we can control
the context window (num_ctx) and keep escaping sane for long transcripts.

No API tokens are spent — everything runs against the local Ollama server.
"""
import argparse
import json
import sys
import urllib.request

PROMPT_TEMPLATE = """Create a Google Gemini-style MoM (Minutes of Meeting) from this transcript.

The transcript may be in Greek. Write the MoM in clear internal English for the efood and Foody teams.

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
- Use these sections, in this order: Attendees, Executive Summary, Key Decisions, Ownership Split, Action Items, Also Discussed, Open Questions, Risks, Next Decision.
- Format the whole MoM as GitHub-flavoured Markdown: a single "# Minutes of Meeting" title, then each section title as a "## " heading (e.g. "## Executive Summary"); use bullet lists and **bold** for inline labels.
- Attendees section: list the provided attendees; mark anyone never clearly referenced in the transcript as "(listed; not clearly identified in audio)". If no list was provided, write "No attendee list provided."
- Use red/yellow/green status signals (🔴/🟡/🟢) for risk and priority.
- Action Items MUST be a markdown table with columns: Action | Owner | Due | Status | Group. Owner must be a name from the Attendees list or "⚠️ owner not stated". Status is one of Blocking / In Progress / Blocked / Awaiting / Pending / Done. Group is New, Carried Forward, or Closed. Due is a date or an explicit gating condition ("Gated on domain", "After credentials").
- Be faithful to the transcript; do not invent.

REASONING STANDARD (this is the substance of the job, not an optional extra).
You are not transcribing a meeting. You are recording what it RESOLVED and what it LEFT
OPEN, so a reader who was not there knows what moves next and who holds it. Apply every
rule the transcript supports; never manufacture material to satisfy one.
1. Every key topic resolves. It ends either in a decision, or — when nothing was settled —
   in the DECOMPOSITION: the specific questions that must be answered before it can be
   decided, who answers each, and what approval is needed. Never write "this was
   discussed" and stop. That is the failure mode to avoid.
2. Name the critical path. Usually one open item gates the rest. Say so in those terms
   ("if this is not closed, nothing else moves") and mark that action item "Blocking",
   with an owner and a date.
3. Keep the team un-idle. When a decision depends on someone outside the room, record the
   parallel track that runs meanwhile, and say why.
4. Hold scope. When a request grows effort, state what is in the MVP and what defers to a
   later phase. Deferral is a decision — record it as one.
5. Re-opened decisions get their history restated: the prior decision, its date, and the
   reason it was taken, before the new discussion.
6. Ask for the number that decides. If something affects "some" or "several" cases, the
   action item is to get the count or percentage, and say why it matters.
7. State the reasoning that makes a proposal moot. If a stated fact rules an approach out,
   follow the chain and say so explicitly.
8. Be honest about what cannot be estimated. Do not invent confidence or ranges.
9. Put settled facts and low-salience items under "Also Discussed", saying why they are
   recorded (e.g. so everyone works from the same understanding).
10. "Blocking" and "Blocked" are DIFFERENT and must not be conflated:
    Blocking = on the critical path, other work waits on it;
    Blocked  = cannot start until something else is done.

TONE: understated, declarative, specific. Short sentences. "We" for the team. No
enthusiasm adverbs, no "great discussion", no "aligned on", no filler.
- The transcript is machine-transcribed: English technical terms embedded in Greek speech may be phonetically garbled (e.g. a product name rendered as similar-sounding Greek). Restore the intended term when it is obvious from context; if unsure, keep the transcript wording.

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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript", help="Path to the Greek transcript .txt file")
    ap.add_argument("-o", "--output", required=True, help="Path to write the MoM markdown")
    ap.add_argument("-m", "--model", default="qwen2.5:7b", help="Ollama model name")
    ap.add_argument("--host", default="http://127.0.0.1:11434", help="Ollama host")
    ap.add_argument("--num-ctx", type=int, default=16384, help="Context window size")
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--attendees", default="",
                    help="Comma/newline separated attendee names (the only names allowed as owners)")
    args = ap.parse_args()

    with open(args.transcript, "r", encoding="utf-8") as f:
        transcript = f.read().strip()

    if not transcript:
        print("ERROR: transcript is empty", file=sys.stderr)
        return 1

    prompt = build_prompt(transcript, args.attendees)

    payload = {
        "model": args.model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_ctx": args.num_ctx, "temperature": args.temperature},
    }

    req = urllib.request.Request(
        f"{args.host}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    print(f"Summarizing with {args.model} (num_ctx={args.num_ctx})...", file=sys.stderr)
    with urllib.request.urlopen(req, timeout=1800) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    mom = data.get("response", "").strip()
    if not mom:
        print("ERROR: empty response from model", file=sys.stderr)
        return 1

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(mom + "\n")

    print(f"MoM written to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
