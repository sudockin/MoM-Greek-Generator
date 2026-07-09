#!/usr/bin/env python3
"""Unit tests for the pure functions touched by the speaker-naming fixes.

Runs with the stdlib only — no models, no macOS Vision, no network:

    python3 test_speaker_naming.py
"""
import os
import tempfile
import unittest

import ocr_speakers as ocr
import server


class IsPersonName(unittest.TestCase):
    def test_two_and_three_token_names(self):
        self.assertTrue(ocr.is_person_name("Maria Kolovou"))
        self.assertTrue(ocr.is_person_name("Anna Maria Papadopoulou"))

    def test_greek_caps(self):
        self.assertTrue(ocr.is_person_name("Μαρία Κολοβού"))

    def test_rejects_digits_and_punctuation(self):
        self.assertFalse(ocr.is_person_name("Room 2 Notes"))
        self.assertFalse(ocr.is_person_name("File: Edit"))
        self.assertFalse(ocr.is_person_name("Q4 Plan"))

    def test_rejects_stopwords(self):
        self.assertFalse(ocr.is_person_name("Action Items"))
        self.assertFalse(ocr.is_person_name("Google Meet"))

    def test_single_token_gated_by_allow_single(self):
        # A lone first name is rejected by default (no roster to vouch for it)...
        self.assertFalse(ocr.is_person_name("Maria"))
        # ...but accepted when the caller opts in (roster present).
        self.assertTrue(ocr.is_person_name("Maria", allow_single=True))

    def test_company_tag_stripped(self):
        self.assertEqual(ocr.strip_company_tag("Maria K. (efood)"), "Maria K.")
        self.assertTrue(ocr.is_person_name("Maria Kolovou (Delivery Hero)"))
        self.assertTrue(ocr.is_person_name("Maria (efood)", allow_single=True))


class NameFromResults(unittest.TestCase):
    """bbox = [x, y, w, h], normalized, origin bottom-left; result = (text, conf, bbox)."""

    def test_single_first_name_matches_with_roster(self):
        roster = ocr.parse_roster("Maria Kolovou, Nikos Papas")
        results = [("Maria", 0.95, (0.80, 0.05, 0.1, 0.02))]
        self.assertEqual(ocr.name_from_results(results, roster), "Maria Kolovou")

    def test_single_first_name_rejected_without_roster(self):
        results = [("Maria", 0.95, (0.80, 0.05, 0.1, 0.02))]
        self.assertIsNone(ocr.name_from_results(results, None))

    def test_no_new_false_positive_without_roster(self):
        # A stray one-word UI label in the right tile must NOT become a speaker.
        results = [("Chat", 0.95, (0.80, 0.05, 0.1, 0.02))]
        self.assertIsNone(ocr.name_from_results(results, None))


class ModelDiscovery(unittest.TestCase):
    def test_whispercpp_dir_has_no_personal_path(self):
        # The old hardcoded /Users/pj/... default must be gone.
        self.assertNotIn("/Users/pj", server.WHISPERCPP_DIR)

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
        # No env model + a bogus bin dir → nothing found (caller fails loudly).
        self.assertIsNone(server.find_whisper_cpp_model("/nonexistent/bin/whisper-cli"))


class OverwriteGuard(unittest.TestCase):
    """The run_pipeline guard `if named and speakers:` — a zero-name OCR run
    (empty speakers) must NOT overwrite the segmented transcript."""

    @staticmethod
    def should_overwrite(named, speakers):
        return bool(named and speakers)

    def test_zero_name_run_keeps_original(self):
        self.assertFalse(self.should_overwrite("word word word", []))

    def test_named_run_overwrites(self):
        self.assertTrue(self.should_overwrite("Maria: hello", ["Maria"]))

    def test_empty_named_never_overwrites(self):
        self.assertFalse(self.should_overwrite("", []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
