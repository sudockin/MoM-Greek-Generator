#!/usr/bin/env python3
"""Label each transcript segment with the real on-screen name of the active
speaker, by OCR-ing the speaker's name tag. Fully local (Apple Vision via
ocrmac) — no tokens. Run inside the WhisperX venv (which has ocrmac installed).

Two meeting platforms, two different signals — both measured from real
recordings (use --inspect to do the same for a new platform):

* Google Meet shows ONLY the active speaker during a share, as a floating
  thumbnail (default bottom-RIGHT) with the name tag at its bottom-left —
  measured x≈0.75, y≈0.38 (origin bottom-left). Position therefore identifies
  the speaker. Doc/UI false positives sit in the left column and are filtered
  out by position + an optional attendee roster.
* Microsoft Teams shows EVERYONE at once (a tile grid plus a static right-hand
  column of overflow participants), so position says nothing. Teams instead
  highlights the active speaker's name with a coloured badge — measured
  RGB ~(97,100,166), luminance ~121, against 0 for every other label — and that
  badge decides. Older Teams speaker view (name hard bottom-left, x<0.06) is
  still handled by the positional fallback.

CLI:  python ocr_speakers.py VIDEO [audio.json] --name-transcript [--step 4]
                                   [--roster "Name One, Name Two"]
      python ocr_speakers.py VIDEO --inspect      # report a recording's layout
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
# A weaker match is still trustworthy when nothing else comes close: heavily
# mangled Greek tags land near 0.70, but only ever near ONE attendee. Junk text
# scores low against everybody, so it has no clear winner and is still rejected.
ROSTER_MATCH_LOW = _envf("MOM_OCR_ROSTER_LOW", 0.62)
ROSTER_MATCH_MARGIN = _envf("MOM_OCR_ROSTER_MARGIN", 0.12)
# Microsoft Teams highlights the ACTIVE speaker's name with a coloured badge
# (measured ~RGB 96-99,100-101,164-167 -> luminance ~121); every other name sits
# on black (luminance 0). That is a far stronger signal than position, so when a
# badge is visible it decides who was speaking.
BADGE_MIN_LUM = _envf("MOM_OCR_BADGE_MIN_LUM", 40.0)
# Brightness alone is not enough: Teams draws avatar monogram circles ("NA",
# "ΠΔ") whose pastel fill is BRIGHTER than the badge (measured 214-220 vs 120)
# and would outrank it. The badge is identified by its blue-violet hue instead —
# measured B-R +70 / B-G +62, where the pale-blue avatars reach only +30/+17 and
# the pink ones go negative.
BADGE_MAX_LUM = _envf("MOM_OCR_BADGE_MAX_LUM", 190.0)
BADGE_MIN_BLUE = _envf("MOM_OCR_BADGE_MIN_BLUE", 30.0)
# Teams also lists non-visible participants in a static right-hand column; 3+
# name tags sharing an x are that roster, never the active speaker.
ROSTER_COL_MIN = int(_envf("MOM_OCR_ROSTER_COL_MIN", 3))

# Punctuation that never appears in a clean name tag (so we reject doc/UI lines).
_BAD_CHARS = set(",:;•|/\\()[]{}@#%&*=<>\"")
# Common UI/doc bigrams that look name-ish but aren't people.
STOPWORDS = {
    "risk register", "key milestones", "action items", "google drive",
    "ask chat", "add tab", "file edit", "control panel", "delivery hero",
    "open questions", "next steps", "vendors domain", "google meet",
}
# Single tokens that mark app/doc text on a shared screen, never a person
# ("Logs Table JSON", "Table Explorer", "Data Quality", ...). Compared on the
# normalized (Latin) token; a short Greek list is compared on the raw lowercase.
_UI_TOKENS = {
    "json", "table", "tables", "logs", "log", "data", "explorer", "class",
    "global", "operator", "quality", "entity", "settings", "error", "file",
    "edit", "view", "chat", "tab", "panel", "dashboard", "query", "filter",
    "export", "import", "menu", "search", "home", "admin", "login", "total",
    "report", "overview", "summary", "meeting", "minutes", "agenda", "review",
    "status", "update", "project", "roadmap", "backlog", "sprint", "vendor",
    "console", "browser", "window", "untitled", "document", "sheet", "slide",
    "external", "ids", "internal", "details", "results", "options",
}
_GREEK_UI_TOKENS = {"σύνολο", "αναζήτηση", "αρχείο", "επεξεργασία", "προβολή",
                    "ρυθμίσεις", "μενού", "σελίδα", "πίνακας"}


def _mixed_script(tok):
    """OCR garbage often fuses Greek and Latin letters in one token ('Tιp')."""
    has_latin = any(c.isalpha() and "a" <= c.lower() <= "z" for c in tok)
    has_greek = any("Ͱ" <= c <= "Ͽ" or "ἀ" <= c <= "῿" for c in tok)
    return has_latin and has_greek


def _strict_token_ok(tok):
    """Extra shape rules used when NO roster vouches for names: reject acronyms
    and OCR case-noise ('JSON', 'MangoDB', 'GkanatsidE') and non-initial dots
    ('Gkanatcio.'). Hyphen/apostrophe parts are each checked ('Anna-Maria' ok)."""
    if "." in tok:
        if not (tok.endswith(".") and tok.count(".") == 1 and len(tok) <= 3):
            return False
        tok = tok[:-1]
    for part in re.split(r"[-'’]", tok):
        if any(c.isupper() for c in part[1:]):
            return False
    return True


# Greek -> Latin, and the Cyrillic letters Apple Vision substitutes for
# visually-identical Greek ones (it reads "Χαιρετάκης" as "Харетак"). Both map
# into one Latin space so a Greek display name, its OCR mangling and a
# Latin-spelled attendee entry all compare against each other.
_TRANSLIT = {
    # Greek
    "α": "a", "β": "v", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "i",
    "θ": "th", "ι": "i", "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x",
    "ο": "o", "π": "p", "ρ": "r", "σ": "s", "ς": "s", "τ": "t", "υ": "y",
    "φ": "f", "χ": "ch", "ψ": "ps", "ω": "o",
    # Cyrillic look-alikes (OCR confusion, not real Russian text)
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "z",
    "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "y", "ф": "f",
    "х": "ch", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh", "ы": "y",
    "э": "e", "ю": "yu", "я": "ya", "ь": "", "ъ": "",
}


def normalize(s):
    """Accent-free lowercase text, keeping letters of ANY script.

    The old version stripped everything outside [a-zA-Z], which silently
    reduced every Greek-script name to an empty string — so Greek attendees
    were dropped from the roster entirely and could never be matched."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = "".join(c if (c.isalpha() or c.isspace()) else " " for c in s).lower()
    return re.sub(r"\s+", " ", s).strip()


def translit(s):
    """Normalized text folded into Latin, so 'Χαιρετάκης', its OCR mangling
    'Харетак' and a Latin-spelled 'Chairetakis' all land in the same space."""
    return "".join(_TRANSLIT.get(c, c) for c in normalize(s))


# Vision reads Greek glyphs as the LATIN letters they look like, not the ones
# they sound like: "Καραγιάννη" comes back as "Kapaylavvn" (ρ→p, γ→y, ι→l, ν→v).
# Phonetic transliteration cannot undo that, so names are also compared with
# visually-confusable glyphs collapsed into one class per shape.
_SHAPE = {}
for _cls, _chars in {
    "a": "aαа", "b": "bβв", "d": "dδд", "e": "eεе", "f": "fφ",
    "g": "g", "h": "h", "i": "iιίі1lλ", "k": "kκк", "m": "mμмu",
    "n": "nηнπ", "o": "oοо0", "p": "pρр", "r": "r", "s": "sσςс",
    "t": "tτт", "v": "vν", "w": "wω", "x": "xξχх", "y": "yγуυ",
    "z": "zζ", "c": "c", "j": "j", "q": "q", "th": "θ", "ps": "ψ",
}.items():
    for _ch in _chars:
        _SHAPE[_ch] = _cls


def shape_fold(s):
    """Normalized text with visually-confusable glyphs collapsed, so an OCR
    misreading of a Greek name lines up with the real name."""
    return "".join(_SHAPE.get(c, c) for c in normalize(s))


def _tok_ratio(a, b):
    """Similarity of two name tokens, tolerating truncation ('Andreo' vs
    'Andreopoulos')."""
    r = difflib.SequenceMatcher(None, a, b).ratio()
    if len(a) + 2 < len(b):
        r = max(r, difflib.SequenceMatcher(None, a, b[:len(a)]).ratio())
    return r


def token_align(a, b):
    """Match a tag against a name token-by-token, each tag token taking its best
    partner (so word order doesn't matter), averaged.

    Whole-string similarity is too blunt when two people share a forename:
    'Χαιρετάκης Νικόλαος' and 'Nikos Andreopoulos' overlap heavily as strings,
    but token-wise the surnames are decisively different — and the surname is
    what tells them apart."""
    at, bt = a.split(), b.split()
    if not at or not bt:
        return 0.0
    return sum(max(_tok_ratio(x, y) for y in bt) for x in at) / len(at)


def _name_ratio(a_forms, b_forms):
    """Best similarity across the comparison spaces, plus a prefix-tolerant
    pass: Teams truncates long names on narrow tiles ('Nikos Andreo…'), so a
    short tag is also compared against the same-length head of the full name."""
    best = 0.0
    for a, b in zip(a_forms, b_forms):
        if not a or not b:
            continue
        best = max(best, difflib.SequenceMatcher(None, a, b).ratio())
        if len(a) + 2 < len(b):   # a looks truncated -> compare like-for-like
            best = max(best, difflib.SequenceMatcher(None, a, b[:len(a)]).ratio())
    return best


def strip_company_tag(s):
    """Clean a name tag: drop a trailing '(Company)' (Meet), the ellipsis Teams
    adds when a name is too long for its tile ('Nikos Andreo…'), and trailing
    junk from the mute/mic glyph next to Teams names (OCR reads it as %, *, ¼)."""
    s = re.sub(r"\s*\([^)]*\)\s*$", "", (s or "").strip())
    s = re.sub(r"\s*(?:\.\.\.|…)\s*$", "", s)
    s = re.sub(r"[^\w'’\-.]+$", "", s, flags=re.UNICODE)
    return s.strip()


def is_person_name(s, allow_single=False, strict=False):
    """Capitalised, letters-only name tokens (Latin or Greek); no digits/punctuation.

    Accepts 2–3 tokens by default; with allow_single=True also accepts a single
    first-name token (only safe when a roster vouches for it — see name_from_results).
    A trailing '(Company)' tag is stripped first. Uses Unicode-aware str methods
    rather than a regex range so Greek caps work.

    strict=True (used when there is NO attendee roster) additionally applies
    shape rules that separate people from shared-screen app text — see
    _strict_token_ok. With a roster the fuzzy roster match is the gate instead,
    so misread frames of a real attendee still count toward the right person."""
    s = strip_company_tag(s)
    toks = s.split()
    lo = 1 if allow_single else 2
    if not (lo <= len(toks) <= 3):
        return False
    # A lone 2-letter token is an avatar monogram ("NA", "ΠΔ"), not a name.
    if len(toks) == 1 and len(toks[0].rstrip(".")) < 3:
        return False
    if any(ch.isdigit() for ch in s) or any(ch in _BAD_CHARS for ch in s):
        return False
    for t in toks:
        if len(t) < 2 or not (t[0].isalpha() and t[0].isupper()):
            return False
        if not all(c.isalpha() or c in ".'’-" for c in t):
            return False
        if normalize(t) in _UI_TOKENS or t.lower().rstrip(".") in _GREEK_UI_TOKENS:
            return False
        # Mixed Greek/Latin is OCR garbage on a shared screen — but it is also
        # exactly how Vision renders a Greek display name ("NIKÓNaos"), so only
        # reject it when no roster is around to vouch for the name.
        if strict and (_mixed_script(t) or not _strict_token_ok(t)):
            return False
    return normalize(s) not in STOPWORDS


def parse_roster(raw):
    """Attendee string -> [(canonical_name, translit_name)] for fuzzy matching.

    Compared in transliterated form so an attendee typed in Greek and an
    on-screen tag OCR'd into Latin (or Cyrillic) still meet."""
    if not raw:
        return None
    names = [n.strip() for n in re.split(r"[,\n;]+", raw) if n.strip()]
    pairs = [(n, translit(n)) for n in names]
    pairs = [(c, rn) for c, rn in pairs if rn]
    return pairs or None


def roster_match(text, roster_pairs):
    """Return the canonical roster name an OCR string corresponds to, or None.

    Fuzzy so OCR slips ('Smyth' vs 'Smith') still match the attendee.
    Also matches a single on-screen first name ('Alex') against a full roster
    entry ('Alex Rivera') by taking the best of the full-string and per-token
    ratios — a first name IS a strong signal since it must be an attendee token."""
    forms = (translit(text), shape_fold(text))
    if not any(forms):
        return None
    single = len(forms[0].split()) == 1
    best, best_r, runner_r = None, 0.0, 0.0
    for canon, rn in roster_pairs:
        rforms = (rn, shape_fold(canon))
        r = _name_ratio(forms, rforms)
        for tf, rf in zip(forms, rforms):
            r = max(r, token_align(tf, rf))
        # Compare against individual roster tokens ONLY for a lone on-screen
        # first name. Doing it for multi-token text let a surname-plus-forename
        # tag collide with an unrelated attendee who shares a forename
        # ("Харетак NIKONaos" -> "Nikos Andreopoulos").
        if single:
            for rf, tf in ((rforms[0], forms[0]), (rforms[1], forms[1])):
                for tok in rf.split():
                    r = max(r, _name_ratio((tf,), (tok,)))
        if r > best_r:
            best_r, runner_r, best = r, best_r, canon
        elif r > runner_r:
            runner_r = r
    if best_r >= ROSTER_MATCH_MIN:
        return best
    if best_r >= ROSTER_MATCH_LOW and (best_r - runner_r) >= ROSTER_MATCH_MARGIN:
        return best
    return None


def _open_frame(image_path):
    try:
        from PIL import Image
        return Image.open(image_path).convert("RGB")
    except Exception:
        return None


def label_bg_colour(img, box):
    """A name label's BACKGROUND colour — the modal colour inside its box, since
    the badge fills the box and the glyphs are a minority of pixels."""
    if img is None:
        return None
    x, y, w, h = box
    W, H = img.size
    left, top = int(x * W), int((1.0 - y - h) * H)
    right, bottom = int((x + w) * W), int((1.0 - y) * H)
    if right <= left or bottom <= top:
        return None
    try:
        crop = img.crop((max(0, left), max(0, top), min(W, right), min(H, bottom)))
        return collections.Counter(crop.getdata()).most_common(1)[0][0][:3]
    except Exception:
        return None


def label_is_badged(img, box):
    """True when a label sits on the platform's active-speaker badge.

    Matches on the badge's blue-violet hue, not merely on brightness — see
    BADGE_MAX_LUM/BADGE_MIN_BLUE for why avatar monograms would otherwise win."""
    rgb = label_bg_colour(img, box)
    if not rgb:
        return False
    r, g, b = rgb
    return (BADGE_MIN_LUM <= (r + g + b) / 3.0 <= BADGE_MAX_LUM
            and (b - r) >= BADGE_MIN_BLUE and (b - g) >= BADGE_MIN_BLUE)


def name_from_results(results, roster_pairs=None, image_path=None):
    """Pick the active-speaker name tag from one frame's OCR results.

    Platform-adaptive, in priority order:
      1. A HIGHLIGHTED label wins outright (Teams badges the active speaker).
         When any label is highlighted, the un-highlighted ones are known not to
         be speaking, so they are discarded rather than merely out-scored.
      2. Otherwise fall back to position (Meet's floating right-hand tile, or
         Teams' bottom-left tag) — unchanged behaviour for Meet.
    A static column of 3+ names at the same x is Teams' overflow participant
    roster, not a speaker, so it never wins on position alone.

    With a roster, only attendee names are accepted, which is bulletproof
    against shared-screen text."""
    prelim = []
    for text, conf, (x, y, w, h) in results:
        t = strip_company_tag((text or "").strip())
        if conf < 0.3 or not (LABEL_MIN_H <= h <= LABEL_MAX_H):
            continue
        # Single-token first names are only trusted when a roster can vouch for them
        # (otherwise stray one-word UI labels would leak in) — so gate allow_single.
        # Without a roster the strict shape rules are the only defence against
        # shared-screen app text, so they switch on exactly then.
        if not is_person_name(t, allow_single=bool(roster_pairs), strict=not roster_pairs):
            continue
        # Unresolvable tags stay in the list with name=None: they still carry the
        # badge, and a badge we cannot name must block the positional fallback
        # rather than let it credit somebody else.
        name = roster_match(t, roster_pairs) if roster_pairs else t
        prelim.append({"name": name, "conf": conf, "x": x, "y": y, "box": (x, y, w, h)})
    if not prelim:
        return None

    # Teams' overflow roster: 3+ names stacked in one narrow column.
    cols = collections.Counter(round(c["x"], 2) for c in prelim)
    for c in prelim:
        c["roster_col"] = cols[round(c["x"], 2)] >= ROSTER_COL_MIN

    # Reading the badge means decoding the frame, so only do it when there is
    # actually something to disambiguate. Meet shows one name (the floating
    # active-speaker tile) and skips the decode entirely; Teams shows the whole
    # gallery at once and needs it.
    if len(prelim) > 1 and image_path:
        img = _open_frame(image_path)
        if img is not None:
            lit = [c for c in prelim if label_is_badged(img, c["box"])]
            if lit:
                lit.sort(key=lambda c: -c["conf"])
                # May be None: the platform told us who is speaking and it isn't
                # anyone we can name, so report unknown. The caller carries the
                # previous speaker over, which beats naming the wrong person.
                return lit[0]["name"]

    cands = []
    for c in (c for c in prelim if c["name"]):
        right = c["x"] > RIGHT_TILE_MIN_X
        teams = c["x"] < TEAMS_MAX_X and c["y"] < TEAMS_MAX_Y
        bottom = c["y"] < BOTTOM_STRIP_MAX_Y
        if c["roster_col"]:
            continue
        if roster_pairs:
            # Strong roster match → allow any position, but prefer the real tile
            # (right/teams) and the common bottom name-strip.
            score = (c["conf"] + 5.0 + (3.0 if right else 0.0)
                     + (2.0 if teams else 0.0) + (1.0 if bottom else 0.0))
        else:
            if not (right or teams):
                continue
            score = c["conf"] + (3.0 if right else 0.0) + (2.0 if teams else 0.0)
        cands.append((score, c["name"]))
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


# ---------------------------------------------------------------------------
# Shared-screen capture: reuse the same OCR pass to detect when someone is
# presenting, split the share into distinct "screens" (slide/page changes),
# and save one representative frame per screen for the MoM.
# ---------------------------------------------------------------------------
SHARE_MIN_BOXES = int(_envf("MOM_SCREEN_MIN_BOXES", 8))    # text lines mid-frame
SHARE_MIN_CHARS = int(_envf("MOM_SCREEN_MIN_CHARS", 120))  # total chars mid-frame
SCREEN_NEW_SIM = _envf("MOM_SCREEN_NEW_SIM", 0.3)          # below → a new screen
SCREEN_MIN_FRAMES = int(_envf("MOM_SCREEN_MIN_FRAMES", 2)) # ignore 1-frame blips
SCREEN_MAX = int(_envf("MOM_SCREEN_MAX", 40))              # capture cap per meeting


_WORD_RE = re.compile(r"[A-Za-zΑ-Ωα-ωΆ-ώ]{3,}")


def _frame_text_stats(results):
    """(central_text_boxes, total_chars, signature_set, lines, rects) for one
    frame; rects = [(x, y, w, h, text)] of each accepted central box.

    A camera-grid frame has a handful of short name tags; a shared screen has
    many text lines spread across the middle of the frame. The signature is a
    WORD set (letters-only, len>=3) — robust to OCR noise and to digit-heavy
    content (timestamps, log lines) that differs on every read of the same
    screen."""
    sig, lines, rects, chars, boxes = set(), [], [], 0, 0
    for text, conf, (x, y, w, h) in results:
        t = (text or "").strip()
        if conf < 0.3 or len(t) < 2:
            continue
        cx, cy = x + w / 2.0, y + h / 2.0
        if 0.03 <= cx <= 0.97 and 0.05 <= cy <= 0.97:
            boxes += 1
            chars += len(t)
            lines.append(t)
            rects.append((x, y, w, h, t))
            sig.update(w.lower() for w in _WORD_RE.findall(t))
    return boxes, chars, sig, lines, rects


TILE_ZONE_MIN_X = _envf("MOM_SCREEN_TILE_MIN_X", 0.6)  # right-hand floating-tile zone
# The tile's name tag sits at the tile's bottom; anything higher is app chrome
# (tab strip, bookmarks bar) — origin is BOTTOM-left, so "higher" = larger y.
TILE_TAG_MAX_Y = _envf("MOM_SCREEN_TILE_MAX_Y", 0.75)


def content_crop_box(rects, pad=0.025, tile_x=None):
    """Normalized (x0, y0, x1, y1) of the PRESENTED content area (origin
    bottom-left), or None to keep the full frame.

    The area is the union of the frame's central text boxes, excluding
    person-name tags (the floating speaker tile / participant labels) — which
    crops recordings to just the shared screen, like Gemini's meeting notes.
    The speaker tile floats on the RIGHT and its name tag marks the tile's left
    edge, so the crop's right side is clamped there — that removes the tile even
    when full-width content (browser chrome) extends behind it. `tile_x` is the
    meeting-wide estimate of that edge (see ScreenTracker), used because the tag
    may be unreadable in this particular frame; the frame's own tags refine it.
    Falls back to None on sparse text or a suspiciously small union, so a big
    chart with few labels is never over-cropped."""
    keep, tag_xs = [], []
    for x, y, w, h, t in rects:
        if is_person_name(t, allow_single=True):
            tag_xs.append(x)
        else:
            keep.append((x, y, w, h))
    if len(keep) < 5:
        return None
    x0 = min(x for x, _, _, _ in keep)
    y0 = min(y for _, y, _, _ in keep)
    x1 = max(x + w for x, _, w, _ in keep)
    y1 = max(y + h for _, y, _, h in keep)
    xr = min(1.0, x1 + pad)
    # Clamp at the tile's left edge: this frame's leftmost right-zone tag, or the
    # meeting-wide estimate. Ignored if it would eat the content itself.
    # Prefer the meeting-wide estimate (robust); fall back to this frame's tags
    # only when no global estimate exists, since a stray name inside the shared
    # content would otherwise pull the edge left and eat real content.
    edges = [tile_x] if tile_x is not None else [
        tx for tx in tag_xs if tx >= TILE_ZONE_MIN_X]
    if edges:
        limit = min(edges) - 0.005
        if limit - x0 >= 0.35:
            xr = min(xr, limit)
    if (xr - x0) < 0.35 or (y1 - y0) < 0.25:
        return None
    return (max(0.0, x0 - pad), max(0.0, y0 - pad),
            xr, min(1.0, y1 + pad))


def content_stats(rects):
    """(boxes, chars) of text that is NOT a person-name label.

    A camera gallery is made of name tags — Microsoft Teams shows a grid plus a
    static roster column, which alone produced enough text to be mistaken for a
    shared screen. Ignoring name labels separates the two cleanly: measured on
    real recordings, a Teams gallery yields <=7 content boxes / 83 chars while a
    genuine screen share yields 58 boxes / 2106 chars."""
    content = [(x, y, w, h, t) for x, y, w, h, t in rects
               if not is_person_name(t, allow_single=True)]
    return len(content), sum(len(t) for *_rest, t in content)


def _sig_sim(a, b):
    """Jaccard similarity of two frame text signatures (0..1)."""
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def is_share_frame(results):
    *_rest, rects = _frame_text_stats(results)
    boxes, chars = content_stats(rects)
    return boxes >= SHARE_MIN_BOXES and chars >= SHARE_MIN_CHARS


class ScreenTracker:
    """Feed one frame at a time; groups consecutive similar share-frames into
    screens and saves ONE representative frame per screen via save_fn.

    Similarity is measured against the PREVIOUS frame in the run (not the
    first), so slowly scrolling content — a log viewer, a long doc — stays one
    screen instead of fragmenting. Runs shorter than SCREEN_MIN_FRAMES are
    treated as transition blips and dropped, and a new run that still looks
    like the last SAVED screen (app switch and back) extends it rather than
    producing a near-duplicate shot.

    Frames are only WRITTEN in finish(), so every crop can use the
    meeting-wide estimate of the floating tile's left edge (the tag is often
    unreadable in one given frame, but the tile never moves).

    save_fn(frame_index, screen_number, crop_box) -> saved filename (or None to
    skip); injected so the pure segmentation logic is testable without files."""

    def __init__(self, step, save_fn):
        self.step = step
        self.save_fn = save_fn
        self.screens = []
        self._run = None        # {"sig","start","frames":[(idx, lines, rects)]}
        self._saved_sigs = []   # word signature per kept screen (same order)
        self._pending = []      # (mid_idx, mid_rects) parallel to self.screens
        self._tag_xs = []       # right-zone name-tag x positions, whole meeting

    def feed(self, idx, results):
        t = idx * self.step
        _boxes, _chars, sig, lines, rects = _frame_text_stats(results)
        c_boxes, c_chars = content_stats(rects)
        share = c_boxes >= SHARE_MIN_BOXES and c_chars >= SHARE_MIN_CHARS
        # Track the floating tile's left edge, but ONLY while a screen is being
        # shared: in camera-grid view the participant tags sit at unrelated
        # positions and would drag the estimate left (over-cropping).
        if share:
            for x, y, _w, h, txt in rects:
                if (x >= TILE_ZONE_MIN_X and y <= TILE_TAG_MAX_Y
                        and LABEL_MIN_H <= h <= LABEL_MAX_H
                        # 2-3 tokens required: a single capitalised word is far
                        # more likely to be static browser/app chrome (bookmark
                        # buttons, toolbar labels), which sits at a fixed x and
                        # would otherwise become a very convincing false mode.
                        and is_person_name(txt)):
                    self._tag_xs.append(x)
        if share and self._run is not None and _sig_sim(sig, self._run["sig"]) >= SCREEN_NEW_SIM:
            self._run["sig"] = sig  # rolling: compare each frame to its neighbour
            self._run["frames"].append((idx, lines, rects))
            return
        self._close()
        if share:
            self._run = {"sig": sig, "start": t, "frames": [(idx, lines, rects)]}

    def _close(self):
        run = self._run
        self._run = None
        if not run or len(self.screens) >= SCREEN_MAX:
            return
        frames = run["frames"]
        if len(frames) < SCREEN_MIN_FRAMES:
            return
        mid_idx, mid_lines, mid_rects = frames[len(frames) // 2]
        # The same app/screen resurfacing later in the meeting extends the shot
        # already saved for it (most recent match wins) instead of duplicating.
        for si in range(len(self._saved_sigs) - 1, -1, -1):
            if _sig_sim(run["sig"], self._saved_sigs[si]) >= SCREEN_NEW_SIM:
                self.screens[si]["end"] = frames[-1][0] * self.step
                self.screens[si]["frames"] += len(frames)
                return
        self._saved_sigs.append(run["sig"])
        self._pending.append((mid_idx, mid_rects))
        self.screens.append({
            "file": None,   # assigned in finish(), once the tile edge is known
            "t": mid_idx * self.step,
            "start": run["start"],
            "end": frames[-1][0] * self.step,
            "frames": len(frames),
            "text": "\n".join(mid_lines[:60])[:1500],
        })

    def tile_edge(self):
        """Meeting-wide estimate of the floating tile's left edge, or None.

        Uses the MODE of observed name-tag positions, not the median: the tile
        sits at the same x in every shared frame (hundreds of hits in one spot),
        while person names that happen to appear inside the shared content
        (customer names in a log, a doc byline) scatter across positions and a
        median would be dragged left, over-cropping real content. Adjacent
        0.01 buckets are pooled so rounding jitter can't split the cluster."""
        if not self._tag_xs:
            return None
        buckets = collections.Counter(round(x, 2) for x in self._tag_xs)
        best, best_n = None, 0
        for b in buckets:
            n = (buckets[b] + buckets.get(round(b - 0.01, 2), 0)
                 + buckets.get(round(b + 0.01, 2), 0))
            if n > best_n:
                best, best_n = b, n
        if best is None or best_n < 3:
            return None  # no stable, repeated position — don't risk a crop
        cluster = sorted(x for x in self._tag_xs if abs(round(x, 2) - best) <= 0.01)
        return cluster[len(cluster) // 2]

    def finish(self):
        self._close()
        tile_x = self.tile_edge()
        kept = []
        for sc, (idx, rects) in zip(self.screens, self._pending):
            fname = self.save_fn(idx, len(kept) + 1,
                                 content_crop_box(rects, tile_x=tile_x))
            if fname:
                sc["file"] = fname
                kept.append(sc)
        self.screens = kept
        return kept


def build_name_timeline(video, step=4.0, progress=None, ffmpeg=None, roster_pairs=None,
                        screens_dir=None):
    """Return (sorted [(timestamp_seconds, name)], screens) sampled every `step`
    seconds. `screens` is [] unless screens_dir is given, in which case one
    representative JPEG per detected shared screen is saved there.

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

        tracker = None
        if screens_dir:
            os.makedirs(screens_dir, exist_ok=True)

            def save_frame(idx, num, crop=None):
                src = paths[idx]
                fname = f"screen-{num:02d}-t{int(idx * step)}s.jpg"
                dst = os.path.join(screens_dir, fname)
                # Crop to the presented content (ocrmac box origin is BOTTOM-left;
                # Pillow's is top-left). Any failure falls back to the full frame.
                if crop:
                    try:
                        from PIL import Image
                        with Image.open(src) as im:
                            wpx, hpx = im.size
                            x0, y0, x1, y1 = crop
                            box = (int(x0 * wpx), int((1 - y1) * hpx),
                                   int(x1 * wpx), int((1 - y0) * hpx))
                            im.crop(box).save(dst, "JPEG", quality=85)
                        return fname
                    except Exception:
                        pass
                try:
                    import shutil as _sh
                    _sh.copyfile(src, dst)
                    return fname
                except OSError:
                    return None
            tracker = ScreenTracker(step, save_frame)

        done = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
            for i, res in enumerate(ex.map(_ocr_one, paths)):
                name = name_from_results(res, roster_pairs, image_path=paths[i])
                if name:
                    timeline.append((i * step, name))
                if tracker:
                    tracker.feed(i, res)
                done += 1
                if progress and done % 25 == 0:
                    progress(done, n)
        screens = tracker.finish() if tracker else []
    timeline.sort()
    return timeline, screens


def _name_sim(a, b):
    """Similarity of two OCR'd names. Latin-normalized when possible; raw
    lowercase otherwise (normalize() strips Greek, which would make every pair
    of Greek names compare as identical empty strings)."""
    na, nb = normalize(a), normalize(b)
    if na and nb:
        return difflib.SequenceMatcher(None, na, nb).ratio()
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


# OCR misreads of the same tag ('Charalampos Ganatsios' / '...Gkanatsios') sit
# well above this; different people (even sharing a first name) sit well below.
MERGE_SIM = _envf("MOM_OCR_MERGE_SIM", 0.80)


def consolidate_roster(timeline):
    """Count names; merge prefixes (label truncation) and near-duplicates (OCR
    misreads) into the most frequently seen variant."""
    counts = collections.Counter(n for _, n in timeline)
    names = sorted(counts, key=lambda n: -counts[n])
    canonical = {}
    kept = []
    for n in names:
        merged = False
        for k in kept:
            if k.startswith(n) or n.startswith(k) or _name_sim(n, k) >= MERGE_SIM:
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


def assign_transcript(video, audio_json, step=4.0, ffmpeg=None, progress=None,
                      roster_pairs=None, screens_dir=None):
    """Token-free speaker attribution: label each transcript segment with the
    on-screen active-speaker name (no diarization needed). When screens_dir is
    given, also captures one JPEG per distinct shared screen.

    Returns (transcript_text, roster_dict, speakers_list, screens_list)."""
    tl, screens = build_name_timeline(video, step=step, ffmpeg=ffmpeg, progress=progress,
                                      roster_pairs=roster_pairs, screens_dir=screens_dir)
    with open(audio_json, "r", encoding="utf-8") as f:
        segs = json.load(f).get("segments", [])

    if not tl:  # no on-screen names found (e.g. not a video call) -> plain transcript
        text = " ".join((s.get("text") or "").strip() for s in segs if s.get("text"))
        return text.strip(), {}, [], screens

    counts, canonical = consolidate_roster(tl)
    # Without a roster, a name seen in a single frame of a long meeting is OCR
    # noise, not a person — drop it and let those moments carry over the last
    # real speaker (same behaviour as a screen-share gap). Never applied when a
    # roster vouches for names, and never if it would empty the timeline.
    if not roster_pairs:
        min_frames = int(_envf("MOM_OCR_MIN_FRAMES", 2))
        weak = {c for c in {canonical.get(n, n) for n in counts} if counts[c] < min_frames}
        kept_tl = [(t, n) for t, n in tl if canonical.get(n, n) not in weak]
        if weak and kept_tl:
            tl = kept_tl
            for w in weak:
                counts.pop(w, None)
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
    # Who was presenting each captured screen: the active speaker at its time
    # (carry-over semantics, same as transcript labelling).
    for sc in screens:
        idx = bisect.bisect_right(times, sc["t"]) - 1
        sc["presenter"] = names[idx] if 0 <= idx < len(names) else ""
    return transcript, roster, speakers, screens


def inspect_layout(video, step=20.0, ffmpeg=None, roster_pairs=None, limit=40):
    """Print where this recording puts its text: which frames look like a screen
    share, and where person-name tags cluster (the meeting platform's speaker
    tile). Use this to tune a NEW platform's layout from evidence instead of
    guessing — every geometry constant here was derived this way.

    Zones use the ocrmac convention: normalized, origin BOTTOM-left."""
    ffmpeg = ffmpeg or FFMPEG
    zones = collections.Counter()
    tag_pts, share_frames, total = [], 0, 0
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "f_%05d.jpg")
        subprocess.run([ffmpeg, "-y", "-i", video, "-vf", f"fps=1/{step}", "-q:v", "4", out],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        paths = [os.path.join(tmp, f) for f in
                 sorted(x for x in os.listdir(tmp) if x.endswith(".jpg"))][:limit]
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
            for i, res in enumerate(ex.map(_ocr_one, paths)):
                total += 1
                _b, _c, _sig, _lines, rects = _frame_text_stats(res)
                boxes, chars = content_stats(rects)
                share = boxes >= SHARE_MIN_BOXES and chars >= SHARE_MIN_CHARS
                share_frames += 1 if share else 0
                for x, y, w, h, t in rects:
                    if not is_person_name(t, allow_single=bool(roster_pairs)):
                        continue
                    if roster_pairs and not roster_match(t, roster_pairs):
                        continue
                    tag_pts.append((x, y, h, t, share))
                    zones["%s-%s" % ("right" if x >= 0.6 else "left" if x <= 0.1 else "middle",
                                     "top" if y >= 0.8 else "bottom" if y <= 0.15 else "middle")] += 1
    print(f"frames sampled     : {total} (every {step:g}s)")
    print(f"look like a share  : {share_frames}  ({100 * share_frames // max(total, 1)}%)")
    print(f"name tags found    : {len(tag_pts)}"
          f"  ({sum(1 for p in tag_pts if p[4])} of them on share frames)")
    if zones:
        print("tag zones (x-y)    : " + ", ".join(f"{z}={n}" for z, n in zones.most_common()))
    share_tags = [(x, y, h, t) for x, y, h, t, s in tag_pts if s]
    if share_tags:
        xs = collections.Counter(round(x, 2) for x, _, _, _ in share_tags)
        ys = collections.Counter(round(y, 2) for _, y, _, _ in share_tags)
        print(f"share-frame tag x  : {xs.most_common(4)}")
        print(f"share-frame tag y  : {ys.most_common(4)}")
        print(f"tag heights        : {collections.Counter(round(h, 3) for _, _, h, _ in share_tags).most_common(3)}")
        print("sample tags        : " + ", ".join(sorted({t for _, _, _, t in share_tags})[:6]))
    else:
        print("No name tags on share frames — this platform may render shared content "
              "full-frame (no overlay tile). Cropping would then correctly do nothing.")
    print("\nCurrent gates: RIGHT_TILE_MIN_X=%.2f TEAMS_MAX_X=%.2f/%.2f "
          "TILE_ZONE_MIN_X=%.2f TILE_TAG_MAX_Y=%.2f SHARE_MIN_BOXES=%d SHARE_MIN_CHARS=%d"
          % (RIGHT_TILE_MIN_X, TEAMS_MAX_X, TEAMS_MAX_Y, TILE_ZONE_MIN_X,
             TILE_TAG_MAX_Y, SHARE_MIN_BOXES, SHARE_MIN_CHARS))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("diarization", nargs="?", help="WhisperX JSON with speaker segments")
    ap.add_argument("--step", type=float, default=4.0)
    ap.add_argument("--ffmpeg", default=None)
    ap.add_argument("--roster", default="",
                    help="attendee list (comma/newline separated) to lock OCR onto real names")
    ap.add_argument("--screens-dir", default="",
                    help="also capture one JPEG per distinct shared screen into this dir")
    ap.add_argument("--json", action="store_true", help="emit mapping+roster as JSON to stdout")
    ap.add_argument("--name-transcript", action="store_true",
                    help="token-free: label each segment of the given audio.json by on-screen name")
    ap.add_argument("--inspect", action="store_true",
                    help="report this recording's layout (share detection + where name tags "
                         "sit) to tune a new meeting platform from evidence")
    args = ap.parse_args()

    prog = lambda i, n: print(f"  OCR {i}/{n}", file=sys.stderr)
    roster_pairs = parse_roster(args.roster)

    if args.inspect:
        inspect_layout(args.video, step=max(args.step, 20.0), ffmpeg=args.ffmpeg,
                       roster_pairs=roster_pairs)
        return

    if args.name_transcript:
        transcript, roster, speakers, screens = assign_transcript(
            args.video, args.diarization, step=args.step, ffmpeg=args.ffmpeg,
            progress=prog, roster_pairs=roster_pairs,
            screens_dir=args.screens_dir or None)
        print(json.dumps({"transcript": transcript, "roster": roster,
                          "speakers": speakers, "screens": screens}))
        return

    tl, _ = build_name_timeline(args.video, step=args.step, ffmpeg=args.ffmpeg,
                                progress=prog, roster_pairs=roster_pairs,
                                screens_dir=args.screens_dir or None)
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
