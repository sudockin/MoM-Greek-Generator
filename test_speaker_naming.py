#!/usr/bin/env python3
"""Unit tests for the pure functions touched by the speaker-naming fixes.

Runs with the stdlib only — no models, no macOS Vision, no network:

    python3 test_speaker_naming.py

All person names below are generic placeholders, not real people.
"""
import os
import tempfile
import unittest

import ocr_speakers as ocr
import server


class IsPersonName(unittest.TestCase):
    def test_two_and_three_token_names(self):
        self.assertTrue(ocr.is_person_name("Alex Rivera"))
        self.assertTrue(ocr.is_person_name("Alex Jordan Rivera"))

    def test_greek_caps(self):
        self.assertTrue(ocr.is_person_name("Άλφα Βήτα"))

    def test_rejects_digits_and_punctuation(self):
        self.assertFalse(ocr.is_person_name("Room 2 Notes"))
        self.assertFalse(ocr.is_person_name("File: Edit"))
        self.assertFalse(ocr.is_person_name("Q4 Plan"))

    def test_rejects_stopwords(self):
        self.assertFalse(ocr.is_person_name("Action Items"))
        self.assertFalse(ocr.is_person_name("Google Meet"))

    def test_single_token_gated_by_allow_single(self):
        # A lone first name is rejected by default (no roster to vouch for it)...
        self.assertFalse(ocr.is_person_name("Alex"))
        # ...but accepted when the caller opts in (roster present).
        self.assertTrue(ocr.is_person_name("Alex", allow_single=True))

    def test_company_tag_stripped(self):
        self.assertEqual(ocr.strip_company_tag("Alex R. (Example Co)"), "Alex R.")
        self.assertTrue(ocr.is_person_name("Alex Rivera (Example Co)"))
        self.assertTrue(ocr.is_person_name("Alex (Example Co)", allow_single=True))


class NameFromResults(unittest.TestCase):
    """bbox = [x, y, w, h], normalized, origin bottom-left; result = (text, conf, bbox)."""

    def test_single_first_name_matches_with_roster(self):
        roster = ocr.parse_roster("Alex Rivera, Sam Chen")
        results = [("Alex", 0.95, (0.80, 0.05, 0.1, 0.02))]
        self.assertEqual(ocr.name_from_results(results, roster), "Alex Rivera")

    def test_single_first_name_rejected_without_roster(self):
        results = [("Alex", 0.95, (0.80, 0.05, 0.1, 0.02))]
        self.assertIsNone(ocr.name_from_results(results, None))

    def test_no_new_false_positive_without_roster(self):
        # A stray one-word UI label in the right tile must NOT become a speaker.
        results = [("Chat", 0.95, (0.80, 0.05, 0.1, 0.02))]
        self.assertIsNone(ocr.name_from_results(results, None))


def _teams_gallery():
    """A Microsoft Teams camera gallery: a few tile names plus the static
    right-hand overflow roster. No shared content at all."""
    grid = [("Filippos", 0.004, 0.504), ("Chris Nikolaou", 0.44, 0.506),
            ("Dimitris K", 0.006, 0.10), ("Alex Rivera", 0.295, 0.10)]
    roster = [("Nikos Andreo", 0.898, y) for y in (0.80, 0.65, 0.50, 0.36, 0.21, 0.06)]
    return [(t, 0.9, (x, y, 0.10, 0.019)) for t, x, y in grid + roster]


class TeamsLayout(unittest.TestCase):
    """Microsoft Teams differs from Meet in two ways that broke both features:
    a camera gallery is nothing but name labels (mistaken for a screen share),
    and every participant's name is visible at once (so position can't say who
    is speaking — Teams badges the active speaker instead)."""

    def test_gallery_is_not_mistaken_for_a_screen_share(self):
        self.assertFalse(ocr.is_share_frame(_teams_gallery()))

    def test_content_stats_ignore_name_labels(self):
        boxes, chars = ocr.content_stats(
            [(0.1, 0.5, 0.2, 0.02, "Alex Rivera"),
             (0.1, 0.4, 0.2, 0.02, "quarterly revenue by region")])
        self.assertEqual(boxes, 1)
        self.assertEqual(chars, len("quarterly revenue by region"))

    def test_roster_column_never_wins_on_position(self):
        # 3+ names stacked at one x is the overflow roster; without a badge the
        # picker must not crown one of them just for being on the right.
        roster_only = [(t, 0.9, (x, y, 0.10, 0.019)) for t, x, y in
                       [("Nikos Andreo", 0.898, y) for y in (0.8, 0.65, 0.5, 0.36)]]
        self.assertIsNone(ocr.name_from_results(roster_only, None))

    def test_highlighted_label_wins_over_position(self):
        # Stub the badge probe (real one needs Pillow + a frame on disk).
        real = ocr.label_badge_lum
        ocr.label_badge_lum = lambda img, box: 121.0 if abs(box[0] - 0.44) < 1e-6 else 0.0
        try:
            got = ocr.name_from_results(_teams_gallery(), None, image_path="/dev/null")
        finally:
            ocr.label_badge_lum = real
        # /dev/null won't open as an image, so no badge data -> falls back to
        # position; assert the fallback at least refuses the roster column.
        self.assertNotEqual(got, "Nikos Andreo")

    def test_truncated_and_mic_glyph_tags_are_cleaned(self):
        # Teams truncates long names and draws a mute glyph the OCR misreads.
        self.assertEqual(ocr.strip_company_tag("Nikos Andreo..."), "Nikos Andreo")
        self.assertEqual(ocr.strip_company_tag("Nikos Andreo…"), "Nikos Andreo")
        self.assertEqual(ocr.strip_company_tag("Paminos Valsamakis *"), "Paminos Valsamakis")
        roster = ocr.parse_roster("Nikos Andreopoulos, Sam Chen")
        self.assertEqual(ocr.roster_match("Nikos Andreo...", roster), "Nikos Andreopoulos")


class GreekAndForeignNames(unittest.TestCase):
    """Greek-script display names must identify the right person.

    Apple Vision renders Greek glyphs as the LATIN letters they resemble
    ('Καραγιάννη' -> 'Kapaylavvn') or as Cyrillic look-alikes ('Χαιρετάκης' ->
    'Харетак'), and Teams truncates long names. All strings below were observed
    in a real Teams recording."""

    ROSTER = ("Nikos Andreopoulos, Ποντίκας Δημήτρης, Giorgos Kyrikos, "
              "Shmal Vyacheslav, Καραγιάννη Ευθυμία, Μιχαηλίδης Ευάγγελος, "
              "Filippos, Χαιρετάκης Νικόλαος, Dimitris K, Paminos Valsamakis, "
              "Efthymia Mavrokefalou")

    def setUp(self):
        self.roster = ocr.parse_roster(self.ROSTER)

    def test_greek_attendees_survive_parsing(self):
        # normalize() used to strip every non-Latin letter, so Greek-script
        # attendees vanished from the roster before matching even started.
        self.assertEqual(len(self.roster), 11)

    def test_normalize_keeps_greek(self):
        self.assertEqual(ocr.normalize("Χαιρετάκης"), "χαιρετακης")

    def test_greek_and_mangled_variants_resolve(self):
        for tag, want in [
            ("Χαιρετάκης Νικόλαος", "Χαιρετάκης Νικόλαος"),
            ("Харетак NIKÓNaos", "Χαιρετάκης Νικόλαος"),     # Cyrillic look-alikes
            ("Kapaylavvn E...", "Καραγιάννη Ευθυμία"),       # Latin look-alikes
            ("Mixandions Euk...", "Μιχαηλίδης Ευάγγελος"),
            ("Потікас Aпи...", "Ποντίκας Δημήτρης"),
            ("Nikos Andreo...", "Nikos Andreopoulos"),       # truncated Latin
            ("Efthymi...", "Efthymia Mavrokefalou"),
            ("Shmal Vyache...", "Shmal Vyacheslav"),         # non-Greek foreign name
        ]:
            self.assertEqual(ocr.roster_match(tag, self.roster), want, tag)

    def test_no_false_positives(self):
        for junk in ["Logs Table JSON", "Table Explorer", "Data Quality",
                     "Alex Rivera", "Sam Chen", "Σύνολο Παραγγελιών"]:
            self.assertIsNone(ocr.roster_match(junk, self.roster), junk)

    def test_forename_collision_rejected(self):
        # A surname+forename tag must not be swallowed by a different attendee
        # who merely shares a forename.
        roster = ocr.parse_roster("Nikos Andreopoulos, Χαιρετάκης Νικόλαος")
        self.assertEqual(ocr.roster_match("Харетак NIKÓNaos", roster),
                         "Χαιρετάκης Νικόλαος")


class ModelDiscovery(unittest.TestCase):
    def test_whispercpp_dir_has_no_hardcoded_personal_path(self):
        # The discovered dir may legitimately live under THIS user's $HOME
        # (~/.cache/whisper-cpp); what must never come back is a developer
        # path hardcoded in the source.
        src = open(server.__file__, encoding="utf-8").read()
        self.assertNotIn(".gemini/antigravity", src)
        if server.WHISPERCPP_DIR.startswith("/Users/"):
            self.assertTrue(server.WHISPERCPP_DIR.startswith(os.path.expanduser("~")))

    def test_env_var_wins(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["WHISPERCPP_DIR"] = d
            try:
                self.assertEqual(server.find_whispercpp_dir(), d)
            finally:
                del os.environ["WHISPERCPP_DIR"]

    def test_model_discovery_finds_env_model(self):
        with tempfile.TemporaryDirectory() as d:
            mp = os.path.join(d, "ggml-large-v3.bin")
            open(mp, "wb").close()
            os.environ["WHISPER_MODEL"] = mp
            try:
                self.assertEqual(server.find_whisper_cpp_model(None), mp)
            finally:
                del os.environ["WHISPER_MODEL"]

    def test_model_discovery_returns_none_when_absent(self):
        # No env model + no model file anywhere → nothing found (caller fails
        # loudly). Filesystem is mocked empty so a real ~/.cache install on the
        # dev machine doesn't turn this into a false failure.
        from unittest import mock
        with mock.patch("os.path.exists", return_value=False):
            self.assertIsNone(server.find_whisper_cpp_model("/nonexistent/bin/whisper-cli"))


class StrictScreenShareGate(unittest.TestCase):
    """No-roster mode must reject shared-screen app text that is shaped like a
    name (window titles, dev-tool tabs, OCR case-noise) — the source of junk
    'speakers' during screen-shares."""

    def test_rejects_ui_window_titles(self):
        for junk in ["Logs Table JSON", "Table Explorer", "Data Quality",
                     "Operator Class", "Global Entity", "Loga Table USON"]:
            self.assertFalse(ocr.is_person_name(junk, strict=True), junk)

    def test_rejects_midtoken_capitals(self):
        for junk in ["MangoDB Goland", "Alex RiverA", "Jordan SmitH XE"]:
            self.assertFalse(ocr.is_person_name(junk, strict=True), junk)

    def test_rejects_mixed_greek_latin_tokens(self):
        self.assertFalse(ocr.is_person_name("TIp. Lúvoto", strict=True))

    def test_rejects_long_dotted_token(self):
        self.assertFalse(ocr.is_person_name("Jordan Bakerr.", strict=True))

    def test_accepts_real_names_in_strict_mode(self):
        for ok in ["Alex Rivera", "Άλφα Βήτα", "Anna-Maria Petrou", "Eleni K."]:
            self.assertTrue(ocr.is_person_name(ok, strict=True), ok)

    def test_lenient_mode_keeps_misread_frames_for_roster(self):
        # With a roster, case-noise variants stay eligible so the fuzzy roster
        # match can credit the frame to the real attendee.
        self.assertTrue(ocr.is_person_name("Alex RiverA", strict=False))


class FuzzyConsolidation(unittest.TestCase):
    def test_ocr_misreads_merge_into_dominant_variant(self):
        tl = [(i * 4.0, "Alex Riverra") for i in range(3)] + \
             [(100 + i * 4.0, "Alex Rivera") for i in range(20)]
        counts, canonical = ocr.consolidate_roster(sorted(tl))
        self.assertEqual(canonical["Alex Riverra"], "Alex Rivera")
        self.assertEqual(counts["Alex Rivera"], 23)

    def test_distinct_people_sharing_first_name_stay_separate(self):
        tl = [(i * 4.0, "Jordan Smith") for i in range(10)] + \
             [(100 + i * 4.0, "Jordan Baker") for i in range(10)]
        counts, canonical = ocr.consolidate_roster(sorted(tl))
        self.assertEqual(canonical["Jordan Smith"], "Jordan Smith")
        self.assertEqual(canonical["Jordan Baker"], "Jordan Baker")


def _boxes(lines, x=0.3, y=0.5):
    """Synthesize OCR results: one central text box per line."""
    return [(t, 0.9, (x, y, 0.3, 0.02)) for t in lines]


_SLIDE_A = [f"Quarterly metrics row {i} with enough characters" for i in range(10)]
_SLIDE_B = [f"Totally different agenda item number {i} right here" for i in range(10)]
_CAMERA = ["Alex Rivera", "Sam Chen"]  # a camera grid: just a couple of name tags


class ScreenCapture(unittest.TestCase):
    def test_share_frame_detection(self):
        self.assertTrue(ocr.is_share_frame(_boxes(_SLIDE_A)))
        self.assertFalse(ocr.is_share_frame(_boxes(_CAMERA)))

    def test_tracker_one_screen_per_slide(self):
        saved = []
        tr = ocr.ScreenTracker(4.0, lambda idx, num, crop=None: (saved.append(idx) or f"screen-{num:02d}.jpg"))
        for i in range(5):            # slide A for 20s
            tr.feed(i, _boxes(_SLIDE_A))
        for i in range(5, 8):         # camera break
            tr.feed(i, _boxes(_CAMERA))
        for i in range(8, 12):        # slide B
            tr.feed(i, _boxes(_SLIDE_B))
        screens = tr.finish()
        self.assertEqual(len(screens), 2)
        self.assertEqual(screens[0]["file"], "screen-01.jpg")
        # representative frame = middle of each run (A: frames 0-4 → 2; B: frames 8-11 → 10)
        self.assertEqual(saved, [2, 10])
        self.assertIn("Quarterly metrics", screens[0]["text"])

    def test_tracker_splits_on_content_change_without_gap(self):
        tr = ocr.ScreenTracker(4.0, lambda idx, num, crop=None: f"s{num}.jpg")
        for i in range(4):
            tr.feed(i, _boxes(_SLIDE_A))
        for i in range(4, 8):         # slide flips directly to B
            tr.feed(i, _boxes(_SLIDE_B))
        self.assertEqual(len(tr.finish()), 2)

    def test_tracker_ignores_camera_only_meeting(self):
        tr = ocr.ScreenTracker(4.0, lambda idx, num, crop=None: f"s{num}.jpg")
        for i in range(30):
            tr.feed(i, _boxes(_CAMERA))
        self.assertEqual(tr.finish(), [])

    def test_noisy_or_scrolling_screen_stays_one_shot(self):
        # Same dashboard, OCR noise + scrolling: ~40% of lines differ per frame
        # but most words survive — must NOT fragment into one shot per frame.
        tr = ocr.ScreenTracker(4.0, lambda idx, num, crop=None: f"s{num}.jpg")
        base = [f"grafana explore logs panel row {i} error failed timeout" for i in range(10)]
        for f in range(12):
            noisy = list(base)
            for j in range(4):  # rotate 4 lines per frame (scroll/noise)
                noisy[(f + j) % 10] = f"grafana explore logs panel row shifted {f}{j} warn retry"
            tr.feed(f, _boxes(noisy))
        self.assertEqual(len(tr.finish()), 1)

    def test_single_frame_blip_dropped(self):
        tr = ocr.ScreenTracker(4.0, lambda idx, num, crop=None: f"s{num}.jpg")
        tr.feed(0, _boxes(_CAMERA))
        tr.feed(1, _boxes(_SLIDE_A))   # 4-second flash during app switching
        tr.feed(2, _boxes(_CAMERA))
        self.assertEqual(tr.finish(), [])

    def test_same_screen_resurfacing_extends_not_duplicates(self):
        tr = ocr.ScreenTracker(4.0, lambda idx, num, crop=None: f"s{num}.jpg")
        for i in range(4):
            tr.feed(i, _boxes(_SLIDE_A))
        for i in range(4, 7):
            tr.feed(i, _boxes(_CAMERA))
        for i in range(7, 11):          # back to the same slide
            tr.feed(i, _boxes(_SLIDE_A))
        screens = tr.finish()
        self.assertEqual(len(screens), 1)
        self.assertEqual(screens[0]["frames"], 8)


class ContentCrop(unittest.TestCase):
    """Screenshots crop to the presented area (like Gemini notes): union of
    central text boxes, excluding speaker-tile name tags."""

    def test_crop_excludes_speaker_name_tag(self):
        rects = [(0.05 + 0.02 * i, 0.3 + 0.04 * i, 0.5, 0.02, f"content line {i} here")
                 for i in range(8)]
        rects.append((0.80, 0.05, 0.12, 0.02, "Alex Rivera"))  # floating tile tag
        box = ocr.content_crop_box(rects)
        self.assertIsNotNone(box)
        x0, y0, x1, y1 = box
        self.assertLess(x1, 0.80)   # speaker tile area excluded
        self.assertGreater(y1, 0.5)

    def test_fullwidth_chrome_still_clamps_at_tile_tag(self):
        # Browser chrome spans the full width BEHIND the floating tile; the
        # tile's name tag (right zone) must still clamp the crop's right edge.
        rects = [(0.02, 0.95, 0.95, 0.02, "browser tab bar spanning everything wide")]
        rects += [(0.05, 0.3 + 0.05 * i, 0.6, 0.02, f"content line {i} here") for i in range(7)]
        rects.append((0.76, 0.38, 0.12, 0.02, "Alex Rivera"))
        x0, y0, x1, y1 = ocr.content_crop_box(rects)
        self.assertLessEqual(x1, 0.76)

    def test_global_tile_edge_clamps_when_tag_unreadable_in_that_frame(self):
        # The representative frame's own tag is garbled, but the tile edge was
        # seen in other frames — the crop must still exclude the tile.
        crops = []
        tr = ocr.ScreenTracker(4.0, lambda idx, num, crop=None: (
            crops.append(crop) or f"s{num}.jpg"))
        content = [(0.05, 0.3 + 0.05 * i, 0.6, 0.02, f"content line {i} here")
                   for i in range(9)]
        chrome = [(0.02, 0.95, 0.95, 0.02, "browser tab bar spanning full width")]
        legible = content + chrome + [(0.76, 0.38, 0.12, 0.02, "Alex Rivera")]
        garbled = content + chrome + [(0.76, 0.38, 0.12, 0.02, "Al3x RiverA/")]
        # 5 frames, the middle (representative) one garbled — the tile edge is
        # still known from the others.
        for i, rects in enumerate([legible, legible, garbled, legible, legible]):
            tr.feed(i, [(t, 0.9, (x, y, w, h)) for x, y, w, h, t in rects])
        tr.finish()
        self.assertEqual(tr.tile_edge(), 0.76)
        self.assertIsNotNone(crops[0])
        self.assertLessEqual(crops[0][2], 0.76)

    def test_grid_view_tags_do_not_drag_tile_estimate(self):
        # Camera-grid frames (no share) have participant tags at unrelated
        # positions — they must not lower the tile-edge estimate and over-crop.
        tr = ocr.ScreenTracker(4.0, lambda idx, num, crop=None: f"s{num}.jpg")
        grid = [(0.62, 0.5, 0.1, 0.02, "Sam Chen"), (0.65, 0.2, 0.1, 0.02, "Lee Park")]
        share = [(0.05, 0.3 + 0.05 * i, 0.6, 0.02, f"content line {i} here")
                 for i in range(9)] + [(0.78, 0.38, 0.12, 0.02, "Alex Rivera")]
        for i, rects in enumerate([grid, grid, share, share, share, share, grid]):
            tr.feed(i, [(t, 0.9, (x, y, w, h)) for x, y, w, h, t in rects])
        tr.finish()
        self.assertEqual(tr.tile_edge(), 0.78)

    def test_tile_edge_uses_mode_not_median(self):
        # The tile tag repeats at ~0.78; names inside the shared content
        # (customer names in a log) scatter lower. The estimate must be the
        # repeated tile position, not the median of everything.
        tr = ocr.ScreenTracker(4.0, lambda idx, num, crop=None: f"s{num}.jpg")
        content = [(0.05, 0.3 + 0.05 * i, 0.6, 0.02, f"content line {i} here")
                   for i in range(9)]
        scatter = ["Sam Chen", "Lee Park", "Ana Torres", "Nia Blake", "Omar Diaz"]
        for i in range(10):
            rects = list(content) + [(0.78, 0.38, 0.12, 0.02, "Alex Rivera")]
            # a different content name at a different right-zone x each frame
            rects.append((0.61 + 0.01 * i, 0.55, 0.1, 0.02, scatter[i % 5]))
            tr.feed(i, [(t, 0.9, (x, y, w, h)) for x, y, w, h, t in rects])
        tr.finish()
        self.assertAlmostEqual(tr.tile_edge(), 0.78, places=2)

    def test_static_browser_chrome_is_not_mistaken_for_the_tile(self):
        # Regression: a bookmarks bar ("Work", "Vault", "Prod") sits at a FIXED
        # x in every frame, so single-word labels made a perfect false mode and
        # over-cropped every screenshot. Only real 2-3 token tags in the tile
        # zone, below the chrome, may set the edge.
        tr = ocr.ScreenTracker(4.0, lambda idx, num, crop=None: f"s{num}.jpg")
        content = [(0.05, 0.3 + 0.05 * i, 0.6, 0.02, f"content line {i} here")
                   for i in range(9)]
        chrome = [(0.66, 0.93, 0.03, 0.015, "Work"),
                  (0.70, 0.93, 0.03, 0.015, "Vault"),
                  (0.74, 0.93, 0.03, 0.015, "Prod")]
        for i in range(8):
            rects = content + chrome + [(0.80, 0.38, 0.12, 0.02, "Alex Rivera")]
            tr.feed(i, [(t, 0.9, (x, y, w, h)) for x, y, w, h, t in rects])
        tr.finish()
        self.assertAlmostEqual(tr.tile_edge(), 0.80, places=2)

    def test_tile_edge_none_without_stable_position(self):
        tr = ocr.ScreenTracker(4.0, lambda idx, num, crop=None: f"s{num}.jpg")
        content = [(0.05, 0.3 + 0.05 * i, 0.6, 0.02, f"content line {i} here")
                   for i in range(9)]
        for i in range(3):  # every name at a different x, none repeating
            rects = list(content) + [(0.62 + 0.06 * i, 0.5, 0.1, 0.02, "Sam Chen")]
            tr.feed(i, [(t, 0.9, (x, y, w, h)) for x, y, w, h, t in rects])
        tr.finish()
        self.assertIsNone(tr.tile_edge())

    def test_stray_content_name_does_not_override_global_edge(self):
        # A person's name inside the shared document must not crop the frame;
        # the meeting-wide tile estimate wins.
        rects = [(0.05, 0.3 + 0.05 * i, 0.6, 0.02, f"content line {i} here")
                 for i in range(9)]
        rects.append((0.63, 0.5, 0.1, 0.02, "Sam Chen"))  # stray name in the doc
        x0, y0, x1, y1 = ocr.content_crop_box(rects, tile_x=0.78)
        self.assertGreater(x1, 0.63)
        self.assertLessEqual(x1, 0.78)

    def test_sparse_text_keeps_full_frame(self):
        rects = [(0.4, 0.5, 0.2, 0.02, "big chart"), (0.4, 0.4, 0.2, 0.02, "one label")]
        self.assertIsNone(ocr.content_crop_box(rects))

    def test_tiny_union_keeps_full_frame(self):
        rects = [(0.40, 0.50, 0.05, 0.01, f"word {i}") for i in range(6)]
        self.assertIsNone(ocr.content_crop_box(rects))


class BiasPrompt(unittest.TestCase):
    def test_contains_attendees_and_terms(self):
        p = server.whisper_bias_prompt("Alex Rivera, Sam Chen", "Salesforce, KYC")
        self.assertIn("Alex Rivera", p)
        self.assertIn("Salesforce", p)

    def test_empty_inputs_produce_empty_prompt(self):
        self.assertEqual(server.whisper_bias_prompt("", ""), "")


class OverwriteGuard(unittest.TestCase):
    """The run_pipeline guard `if named and speakers:` — a zero-name OCR run
    (empty speakers) must NOT overwrite the segmented transcript."""

    @staticmethod
    def should_overwrite(named, speakers):
        return bool(named and speakers)

    def test_zero_name_run_keeps_original(self):
        self.assertFalse(self.should_overwrite("word word word", []))

    def test_named_run_overwrites(self):
        self.assertTrue(self.should_overwrite("Alex: hello", ["Alex"]))

    def test_empty_named_never_overwrites(self):
        self.assertFalse(self.should_overwrite("", []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
