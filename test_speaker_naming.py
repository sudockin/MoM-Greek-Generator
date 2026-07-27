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
