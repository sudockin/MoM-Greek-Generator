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
