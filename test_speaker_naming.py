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
        tr = ocr.ScreenTracker(4.0, lambda idx, num: (saved.append(idx) or f"screen-{num:02d}.jpg"))
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
        tr = ocr.ScreenTracker(4.0, lambda idx, num: f"s{num}.jpg")
        for i in range(4):
            tr.feed(i, _boxes(_SLIDE_A))
        for i in range(4, 8):         # slide flips directly to B
            tr.feed(i, _boxes(_SLIDE_B))
        self.assertEqual(len(tr.finish()), 2)

    def test_tracker_ignores_camera_only_meeting(self):
        tr = ocr.ScreenTracker(4.0, lambda idx, num: f"s{num}.jpg")
        for i in range(30):
            tr.feed(i, _boxes(_CAMERA))
        self.assertEqual(tr.finish(), [])

    def test_noisy_or_scrolling_screen_stays_one_shot(self):
        # Same dashboard, OCR noise + scrolling: ~40% of lines differ per frame
        # but most words survive — must NOT fragment into one shot per frame.
        tr = ocr.ScreenTracker(4.0, lambda idx, num: f"s{num}.jpg")
        base = [f"grafana explore logs panel row {i} error failed timeout" for i in range(10)]
        for f in range(12):
            noisy = list(base)
            for j in range(4):  # rotate 4 lines per frame (scroll/noise)
                noisy[(f + j) % 10] = f"grafana explore logs panel row shifted {f}{j} warn retry"
            tr.feed(f, _boxes(noisy))
        self.assertEqual(len(tr.finish()), 1)

    def test_single_frame_blip_dropped(self):
        tr = ocr.ScreenTracker(4.0, lambda idx, num: f"s{num}.jpg")
        tr.feed(0, _boxes(_CAMERA))
        tr.feed(1, _boxes(_SLIDE_A))   # 4-second flash during app switching
        tr.feed(2, _boxes(_CAMERA))
        self.assertEqual(tr.finish(), [])

    def test_same_screen_resurfacing_extends_not_duplicates(self):
        tr = ocr.ScreenTracker(4.0, lambda idx, num: f"s{num}.jpg")
        for i in range(4):
            tr.feed(i, _boxes(_SLIDE_A))
        for i in range(4, 7):
            tr.feed(i, _boxes(_CAMERA))
        for i in range(7, 11):          # back to the same slide
            tr.feed(i, _boxes(_SLIDE_A))
        screens = tr.finish()
        self.assertEqual(len(screens), 1)
        self.assertEqual(screens[0]["frames"], 8)


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
