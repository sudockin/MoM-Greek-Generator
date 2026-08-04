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
                   for i in range(7)]
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
                 for i in range(7)] + [(0.78, 0.38, 0.12, 0.02, "Alex Rivera")]
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
                   for i in range(7)]
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
                   for i in range(7)]
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
                   for i in range(7)]
        for i in range(3):  # every name at a different x, none repeating
            rects = list(content) + [(0.62 + 0.06 * i, 0.5, 0.1, 0.02, "Sam Chen")]
            tr.feed(i, [(t, 0.9, (x, y, w, h)) for x, y, w, h, t in rects])
        tr.finish()
        self.assertIsNone(tr.tile_edge())

    def test_stray_content_name_does_not_override_global_edge(self):
        # A person's name inside the shared document must not crop the frame;
        # the meeting-wide tile estimate wins.
        rects = [(0.05, 0.3 + 0.05 * i, 0.6, 0.02, f"content line {i} here")
                 for i in range(7)]
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


class DueText(unittest.TestCase):
    """A bare date gets a 'Due ' prefix; a gating condition is used verbatim;
    a completed item's date reads as the completion date."""

    def test_date_gets_due_prefix(self):
        self.assertEqual(server._due_text("05/08", "blocking"), "Due 05/08")
        self.assertEqual(server._due_text("5.8.2026", "pending"), "Due 5.8.2026")

    def test_done_date_has_no_prefix(self):
        self.assertEqual(server._due_text("04/08", "done"), "04/08")

    def test_gating_condition_verbatim(self):
        self.assertEqual(server._due_text("Gated on domain", "blocked"), "Gated on domain")
        self.assertEqual(server._due_text("After credentials", "pending"), "After credentials")

    def test_empty(self):
        self.assertEqual(server._due_text("", "pending"), "")
        self.assertEqual(server._due_text(None, "pending"), "")


class MomEmailRendering(unittest.TestCase):
    """The reference-MoM structure must survive the deterministic renderer."""

    def render(self, **over):
        d = {"title": "T", "subtitle": "S", "attendees": ["Alex Rivera"]}
        d.update(over)
        return server.mom_json_to_email_html(d)

    def test_blocking_and_blocked_are_distinct(self):
        self.assertNotEqual(server._STATUS["blocking"]["label"],
                            server._STATUS["blocked"]["label"])
        self.assertNotEqual(server._STATUS["blocking"]["bg"],
                            server._STATUS["blocked"]["bg"])
        html = self.render(action_items=[
            {"text": "Gating check", "status": "blocking", "group": "new"},
            {"text": "Downstream build", "status": "blocked", "group": "new"},
        ])
        self.assertIn(">Blocking<", html)
        self.assertIn(">Blocked<", html)

    def test_action_items_grouped_in_order(self):
        html = self.render(action_items=[
            {"text": "old one", "status": "pending", "group": "carried"},
            {"text": "shipped", "status": "done", "group": "closed"},
            {"text": "fresh", "status": "blocking", "group": "new"},
        ])
        i_new = html.index("Action Items — New")
        i_carried = html.index("Action Items — Carried Forward")
        i_closed = html.index("Action Items — Closed")
        self.assertLess(i_new, i_carried)
        self.assertLess(i_carried, i_closed)

    def test_unknown_or_missing_group_falls_back_to_new(self):
        html = self.render(action_items=[
            {"text": "no group", "status": "pending"},
            {"text": "nonsense group", "status": "pending", "group": "banana"},
        ])
        self.assertIn("Action Items — New", html)
        self.assertNotIn("Action Items — Carried Forward", html)
        self.assertIn("no group", html)
        self.assertIn("nonsense group", html)

    def test_empty_groups_are_omitted(self):
        html = self.render(action_items=[{"text": "x", "status": "pending", "group": "new"}])
        self.assertNotIn("Carried Forward", html)
        self.assertNotIn("Action Items — Closed", html)

    def test_done_item_reads_completed_by(self):
        html = self.render(action_items=[
            {"text": "x", "status": "done", "group": "closed",
             "assignee": "Alex Rivera", "due": "04/08"}])
        self.assertIn("Completed by ", html)
        self.assertIn("04/08", html)
        self.assertNotIn("Due 04/08", html)

    def test_open_item_reads_assignee_and_due(self):
        html = self.render(action_items=[
            {"text": "x", "status": "blocking", "group": "new",
             "assignee": "Alex Rivera", "due": "05/08"}])
        self.assertIn("Assignee: ", html)
        self.assertIn("Due 05/08", html)

    def test_status_tag_and_target_render(self):
        html = self.render(discussion=[
            {"topic": "Domain ownership", "status_tag": "New Blocker",
             "summary": "sum", "decision": "dec", "target": "end of next week"}])
        self.assertIn("1. Domain ownership — New Blocker", html)
        self.assertIn("<strong>Decision:</strong>", html)
        self.assertIn("<strong>Target:</strong>", html)
        self.assertIn("end of next week", html)

    def test_discussion_without_tag_has_no_dangling_dash(self):
        html = self.render(discussion=[{"topic": "Plain topic", "summary": "s"}])
        self.assertIn("1. Plain topic<", html)

    def test_opener_and_closing(self):
        html = self.render(opener="Two closed; one new on the critical path.",
                           closing="Anything new goes straight to Slack.")
        self.assertIn("Two closed; one new on the critical path.", html)
        self.assertIn("Anything new goes straight to Slack.", html)
        self.assertIn("Thank you,", html)

    def test_also_discussed_section(self):
        html = self.render(also_discussed=[
            {"headline": "Year-end deadline.", "detail": "No penalty attached."}])
        self.assertIn("Also Discussed", html)
        self.assertIn("<strong>Year-end deadline.</strong>", html)
        self.assertIn("No penalty attached.", html)

    def test_optional_blocks_omitted_when_absent(self):
        html = self.render()
        for absent in ("Also Discussed", "Action Items", "<strong>Target:</strong>"):
            self.assertNotIn(absent, html)

    def test_content_is_escaped(self):
        html = self.render(opener="a < b & c",
                           action_items=[{"text": "<script>x</script>", "status": "pending"}])
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("a &lt; b &amp; c", html)


class MomJsonPromptContract(unittest.TestCase):
    """The prompt and the renderer must agree on the vocabulary, or the model
    emits fields the template silently drops."""

    def test_prompt_declares_every_rendered_key(self):
        for key in ("subject", "opener", "status_tag", "target", "also_discussed",
                    "action_items", "group", "due", "closing"):
            self.assertIn(f'"{key}"', server.MOM_JSON_INSTRUCTIONS, key)

    def test_prompt_declares_every_status(self):
        for status in server._STATUS:
            self.assertIn(status, server.MOM_JSON_INSTRUCTIONS, status)

    def test_prompt_declares_every_group(self):
        for gid, _ in server._GROUPS:
            self.assertIn(gid, server.MOM_JSON_INSTRUCTIONS, gid)

    def test_reasoning_standard_present_in_all_prompt_paths(self):
        import summarize_mom
        self.assertIn("REASONING STANDARD", server.MOM_JSON_INSTRUCTIONS)
        self.assertIn("REASONING STANDARD", server.PROMPT_TEMPLATE)
        self.assertIn("REASONING STANDARD", summarize_mom.PROMPT_TEMPLATE)
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "Gemini MoM Prompt.md"), encoding="utf-8") as f:
            self.assertIn("REASONING STANDARD", f.read())

    def test_markdown_prompts_stay_in_sync(self):
        import summarize_mom
        self.assertEqual(server.PROMPT_TEMPLATE, summarize_mom.PROMPT_TEMPLATE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
