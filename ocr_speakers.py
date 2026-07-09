#!/usr/bin/env python3
"""Label each transcript segment with the real on-screen name of the active
speaker, by OCR-ing the speaker's name tag. Fully local (Apple Vision via
ocrmac) — no tokens. Run inside the WhisperX venv (which has ocrmac installed).

Primary target: Google Meet. During a screen-share, Meet floats the active
speaker as a thumbnail (default bottom-RIGHT) with the name tag at the tile's
bottom-left — measured at x≈0.75, y≈0.38 (origin bottom-left). Microsoft Teams
(name hard bottom-left, x<0.06) is still supported. Doc/UI text false positives
sit in the left column (x<0.3) and are filtered out by position + an optional
attendee roster.

CLI:  python ocr_speakers.py VIDEO [audio.json] --name-transcript [--step 4]
                                   [--roster "Name One, Name Two"]
"""
import argparse
import bisect
import collections
import concurrent.futures
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata

FFMPEG = os.environ.get("MOM_FFMPEG") or "ffmpeg"

def _envf(name, default):
    """Read a float from env (for tuning geometry gates on unusual layouts)."""
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default

# Text-height window for a name tag (normalized). Real tags measured ~0.016–0.026.
LABEL_MIN_H = _envf("MOM_OCR_MIN_H", 0.008)
LABEL_MAX_H = _envf("MOM_OCR_MAX_H", 0.05)
# Position gates (ocrmac bbox = [x, y, w, h], normalized, origin BOTTOM-left).
RIGHT_TILE_MIN_X = _envf("MOM_OCR_RIGHT_MIN_X", 0.55)  # Meet floating active-speaker tile (bottom-right)
TEAMS_MAX_X = _envf("MOM_OCR_TEAMS_MAX_X", 0.06)       # Teams name tag (hard bottom-left)
TEAMS_MAX_Y = _envf("MOM_OCR_TEAMS_MAX_Y", 0.10)
# Permissive band for the common bottom-name-strip layout — used only to PREFER a
# bottom name when a roster already vouches for it (never widens acceptance alone).
BOTTOM_STRIP_MAX_Y = _envf("MOM_OCR_BOTTOM_MAX_Y", 0.12)
ROSTER_MATCH_MIN = _envf("MOM_OCR_ROSTER_MIN", 0.72)   # fuzzy ratio to accept an OCR string as a roster name

# Punctuation that never appears in a clean name tag (so we reject doc/UI lines).
_BAD_CHARS = set(",:;•|/\\()[]{}@#%&*=<>\"")
# Common UI/doc bigrams that look name-ish but aren't people.
STOPWORDS = {
    "risk register", "key milestones", "action items", "google drive",
    "ask chat", "add tab", "file edit", "control panel", "delivery hero",
    "open questions", "next steps", "vendors domain", "google meet",
}


def normalize(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-zA-Z ]+", " ", s).lower()
    return re.sub(r"\s+", " ", s).strip()


def strip_company_tag(s):
    """'Alex R. (Example Co)' -> 'Alex R.' — Meet often appends an org in parentheses."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", (s or "").strip()).strip()


def is_person_name(s, allow_single=False):
    """Capitalised, letters-only name tokens (Latin or Greek); no digits/punctuation.

    Accepts 2–3 tokens by default; with allow_single=True also accepts a single
    first-name token (only safe when a roster vouches for it — see name_from_results).
    A trailing '(Company)' tag is stripped first. Uses Unicode-aware str methods
    rather than a regex range so Greek caps work."""
    s = strip_company_tag(s)
    toks = s.split()
    lo = 1 if allow_single else 2
    if not (lo <= len(toks) <= 3):
        return False
    if any(ch.isdigit() for ch in s) or any(ch in _BAD_CHARS for ch in s):
        return False
    for t in toks:
        if len(t) < 2 or not (t[0].isalpha() and t[0].isupper()):
            return False
        if not all(c.isalpha() or c in ".'’-" for c in t):
            return False
    return normalize(s) not in STOPWORDS


def parse_roster(raw):
    """Attendee string -> [(canonical_name, normalized_name)] for fuzzy matching."""
    if not raw:
        return None
    names = [n.strip() for n in re.split(r"[,\n;]+", raw) if n.strip()]
    pairs = [(n, normalize(n)) for n in names]
    pairs = [(c, rn) for c, rn in pairs if rn]
    return pairs or None


def roster_match(text, roster_pairs):
    """Return the canonical roster name an OCR string corresponds to, or None.

    Fuzzy so OCR slips ('Smyth' vs 'Smith') still match the attendee.
    Also matches a single on-screen first name ('Alex') against a full roster
    entry ('Alex Rivera') by taking the best of the full-string and per-token
    ratios — a first name IS a strong signal since it must be an attendee token."""
    cn = normalize(text)
    if not cn:
        return None
    best, best_r = None, 0.0
    for canon, rn in roster_pairs:
        r = difflib.SequenceMatcher(None, cn, rn).ratio()
        for tok in rn.split():
            r = max(r, difflib.SequenceMatcher(None, cn, tok).ratio())
        if r > best_r:
            best_r, best = r, canon
    return best if best_r >= ROSTER_MATCH_MIN else None


def name_from_results(results, roster_pairs=None):
    """Pick the active-speaker name tag from one frame's OCR results.

    With a roster: accept only attendee names (position is a tie-breaker), which
    is bulletproof against shared-screen text. Without one: gate on position (the
    floating right-side tile, or Teams' bottom-left) and prefer name-like text."""
    cands = []
    for text, conf, (x, y, w, h) in results:
        t = strip_company_tag((text or "").strip())
        if conf < 0.3 or not (LABEL_MIN_H <= h <= LABEL_MAX_H):
            continue
        # Single-token first names are only trusted when a roster can vouch for them
        # (otherwise stray one-word UI labels would leak in) — so gate allow_single.
        if not is_person_name(t, allow_single=bool(roster_pairs)):
            continue
        right = x > RIGHT_TILE_MIN_X
        teams = x < TEAMS_MAX_X and y < TEAMS_MAX_Y
        bottom = y < BOTTOM_STRIP_MAX_Y
        if roster_pairs:
            canon = roster_match(t, roster_pairs)
            if not canon:
                continue
            # Strong roster match → allow any position, but prefer the real tile
            # (right/teams) and the common bottom name-strip.
            score = (conf + 5.0 + (3.0 if right else 0.0)
                     + (2.0 if teams else 0.0) + (1.0 if bottom else 0.0))
            cands.append((score, canon))
        else:
            if not (right or teams):
                continue
            score = conf + (3.0 if right else 0.0) + (2.0 if teams else 0.0)
            cands.append((score, t))
    if not cands:
        return None
    cands.sort(reverse=True)
    return cands[0][1]


def _ocr_one(path):
    from ocrmac import ocrmac
    try:
        return ocrmac.OCR(path, recognition_level="accurate").recognize()
    except Exception:
        return []


def build_name_timeline(video, step=4.0, progress=None, ffmpeg=None, roster_pairs=None):
    """Return sorted [(timestamp_seconds, name)] sampled every `step` seconds.

    OCR runs across frames in parallel (Apple Vision releases the GIL), which is
    the bulk of the wall-clock time on long meetings."""
    ffmpeg = ffmpeg or FFMPEG
    timeline = []
    with tempfile.TemporaryDirectory() as tmp:
        # One ffmpeg pass: sample frames at 1/step fps as JPEGs.
        out = os.path.join(tmp, "f_%05d.jpg")
        cmd = [ffmpeg, "-y", "-i", video, "-vf", f"fps=1/{step}", "-q:v", "4", out]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        frames = sorted(f for f in os.listdir(tmp) if f.endswith(".jpg"))
        n = len(frames)
        paths = [os.path.join(tmp, fn) for fn in frames]
        done = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
            for i, res in enumerate(ex.map(_ocr_one, paths)):
                name = name_from_results(res, roster_pairs)
                if name:
                    timeline.append((i * step, name))
                done += 1
                if progress and done % 25 == 0:
                    progress(done, n)
    timeline.sort()
    return timeline


def consolidate_roster(timeline):
    """Count names; merge a name that is a prefix of a longer one (label truncation)."""
    counts = collections.Counter(n for _, n in timeline)
    names = sorted(counts, key=lambda n: -counts[n])
    canonical = {}
    kept = []
    for n in names:
        merged = False
        for k in kept:
            if k.startswith(n) or n.startswith(k):
                canonical[n] = k
                counts[k] += counts[n]
                merged = True
                break
        if not merged:
            kept.append(n)
            canonical[n] = n
    return counts, canonical


def map_speakers(diar_segments, timeline, canonical=None):
    """For each diarized speaker, majority-vote the OCR name during their segments."""
    canonical = canonical or {}
    times = [t for t, _ in timeline]
    per_speaker = collections.defaultdict(collections.Counter)
    for seg in diar_segments:
        spk = seg.get("speaker")
        if not spk:
            continue
        lo = bisect.bisect_left(times, seg["start"])
        hi = bisect.bisect_right(times, seg["end"])
        for _, name in timeline[lo:hi]:
            per_speaker[spk][canonical.get(name, name)] += 1
    mapping = {}
    for spk, ctr in per_speaker.items():
        if ctr:
            mapping[spk] = ctr.most_common(1)[0][0]
    return mapping


UNKNOWN = "Speaker (unknown)"


def assign_transcript(video, audio_json, step=4.0, ffmpeg=None, progress=None, roster_pairs=None):
    """Token-free speaker attribution: label each transcript segment with the
    on-screen active-speaker name (no diarization needed).

    Returns (transcript_text, roster_dict, speakers_list)."""
    tl = build_name_timeline(video, step=step, ffmpeg=ffmpeg, progress=progress,
                             roster_pairs=roster_pairs)
    with open(audio_json, "r", encoding="utf-8") as f:
        segs = json.load(f).get("segments", [])

    if not tl:  # no on-screen names found (e.g. not a video call) -> plain transcript
        text = " ".join((s.get("text") or "").strip() for s in segs if s.get("text"))
        return text.strip(), {}, []

    counts, canonical = consolidate_roster(tl)
    times = [t for t, _ in tl]
    names = [canonical.get(n, n) for _, n in tl]

    blocks, last = [], None
    for s in segs:
        txt = (s.get("text") or "").strip()
        if not txt:
            continue
        st, en = float(s.get("start", 0)), float(s.get("end", 0))
        lo = bisect.bisect_left(times, st)
        hi = bisect.bisect_right(times, en)
        votes = collections.Counter(names[lo:hi])
        if votes:
            name = votes.most_common(1)[0][0]
            last = name
        elif last is not None:          # screen-share / gap -> carry over last speaker
            name = last
        else:                           # nothing yet -> nearest sample
            mid = (st + en) / 2
            idx = min(range(len(times)), key=lambda i: abs(times[i] - mid))
            name = names[idx]
            last = name
        if blocks and blocks[-1][0] == name:
            blocks[-1][1].append(txt)
        else:
            blocks.append([name, [txt]])

    transcript = "\n".join(f"{n}: {' '.join(p)}" for n, p in blocks)
    roster = {c: counts[c] for c in {canonical.get(n, n) for n in counts}}
    speakers = []
    for n, _ in blocks:
        if n not in speakers:
            speakers.append(n)
    return transcript, roster, speakers


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("diarization", nargs="?", help="WhisperX JSON with speaker segments")
    ap.add_argument("--step", type=float, default=4.0)
    ap.add_argument("--ffmpeg", default=None)
    ap.add_argument("--roster", default="",
                    help="attendee list (comma/newline separated) to lock OCR onto real names")
    ap.add_argument("--json", action="store_true", help="emit mapping+roster as JSON to stdout")
    ap.add_argument("--name-transcript", action="store_true",
                    help="token-free: label each segment of the given audio.json by on-screen name")
    args = ap.parse_args()

    prog = lambda i, n: print(f"  OCR {i}/{n}", file=sys.stderr)
    roster_pairs = parse_roster(args.roster)

    if args.name_transcript:
        transcript, roster, speakers = assign_transcript(
            args.video, args.diarization, step=args.step, ffmpeg=args.ffmpeg,
            progress=prog, roster_pairs=roster_pairs)
        print(json.dumps({"transcript": transcript, "roster": roster, "speakers": speakers}))
        return

    tl = build_name_timeline(args.video, step=args.step, ffmpeg=args.ffmpeg,
                             progress=prog, roster_pairs=roster_pairs)
    counts, canonical = consolidate_roster(tl)

    if args.json:
        roster = {}
        for n in counts:
            c = canonical.get(n, n)
            roster[c] = roster.get(c, 0) + 0  # ensure key
        roster = {c: counts[c] for c in {canonical.get(n, n) for n in counts}}
        mapping = {}
        if args.diarization:
            with open(args.diarization, "r", encoding="utf-8") as f:
                segs = json.load(f).get("segments", [])
            mapping = map_speakers(segs, tl, canonical)
        print(json.dumps({"mapping": mapping, "roster": roster}))
        return
    print("Roster (name: frames seen):")
    seen = set()
    for n in sorted(counts, key=lambda n: -counts[n]):
        c = canonical.get(n, n)
        if c in seen:
            continue
        seen.add(c)
        print(f"  {c}: {counts[c]}")

    if args.diarization:
        with open(args.diarization, "r", encoding="utf-8") as f:
            segs = json.load(f).get("segments", [])
        mapping = map_speakers(segs, tl, canonical)
        print("\nSpeaker mapping:")
        for spk, name in sorted(mapping.items()):
            print(f"  {spk} -> {name}")


if __name__ == "__main__":
    main()
