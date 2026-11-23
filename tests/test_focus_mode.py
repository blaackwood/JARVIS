import unittest

from core.focus import (
    DEFAULT_DISTRACTIONS,
    FocusManager,
    check_block,
    distraction,
    parse_distractions,
    start_block,
)


class FocusModeTests(unittest.TestCase):
    def test_default_duration_is_25_minutes(self):
        block = start_block(None, now=1000)
        self.assertEqual(block.minutes, 25)
        self.assertEqual(block.until, 2500)

    def test_duration_is_clamped_to_supported_range(self):
        self.assertEqual(start_block(1, now=1000000).minutes, 5)
        self.assertEqual(start_block(999, now=1000000).minutes, 240)

    def test_task_is_trimmed_and_bounded(self):
        block = start_block(25, "  study math  ", now=1000000)
        self.assertEqual(block.task, "study math")
        self.assertEqual(len(start_block(25, "x" * 200, now=1000000).task), 120)

    def test_site_matches_exact_host_and_subdomain(self):
        self.assertEqual(distraction({"app": "chrome", "url": "https://www.youtube.com/watch?v=1"}), "youtube.com")
        self.assertEqual(distraction({"app": "chrome", "url": "https://music.youtube.com/"}), "youtube.com")

    def test_site_does_not_match_lookalike_domain(self):
        self.assertIsNone(distraction({"app": "chrome", "url": "https://notyoutube.com/"}))

    def test_app_name_matches_case_insensitively(self):
        self.assertEqual(distraction({"app": "Steam", "title": "Library"}), "Steam")

    def test_window_title_is_used_when_url_is_unavailable(self):
        self.assertEqual(distraction({"app": "chrome", "title": "Reddit - Home"}), "Reddit")

    def test_assistant_window_is_never_a_distraction(self):
        self.assertIsNone(distraction({"app": "JARVIS", "title": "YouTube"}))

    def test_domain_match_does_not_use_ambiguous_short_site_name(self):
        self.assertIsNone(distraction({"app": "chrome", "title": "youtube-dl documentation"}, entries=("youtube.com",)))

    def test_two_consecutive_checks_are_required_before_nudge(self):
        block = start_block(25, now=1000000)
        front = {"app": "Steam", "title": "Library"}
        self.assertEqual(check_block(block, front, now=1000020), {})
        self.assertEqual(check_block(block, front, now=1000040), {"nudge": "Steam"})

    def test_returning_to_work_resets_distraction_streak(self):
        block = start_block(25, now=1000000)
        distract = {"app": "Steam", "title": "Library"}
        work = {"app": "Code", "title": "project.py"}
        check_block(block, distract, now=1000020)
        self.assertEqual(check_block(block, work, now=1000040), {})
        self.assertEqual(block.streak, 0)
        self.assertEqual(check_block(block, distract, now=1000060), {})

    def test_nudge_cooldown_is_three_minutes(self):
        block = start_block(25, now=1000000)
        front = {"app": "Steam", "title": "Library"}
        check_block(block, front, now=1000020)
        self.assertEqual(check_block(block, front, now=1000040), {"nudge": "Steam"})
        self.assertEqual(check_block(block, front, now=1000060), {})
        block.streak = 1
        self.assertEqual(check_block(block, front, now=1000219), {})
        self.assertEqual(check_block(block, front, now=1000220), {"nudge": "Steam"})

    def test_block_ends_at_deadline(self):
        block = start_block(5, now=1000000)
        self.assertEqual(check_block(block, {"app": "Steam"}, now=1000300), {"end": True})

    def test_custom_distraction_list_is_cleaned_and_deduplicated(self):
        self.assertEqual(parse_distractions("https://www.youtube.com/watch, Steam, steam, chess.com"),
                         ("youtube.com", "Steam", "chess.com"))
        self.assertEqual(parse_distractions(None), DEFAULT_DISTRACTIONS)

    def test_manager_start_status_stop_lifecycle(self):
        messages = []
        logs = []
        manager = FocusManager(lambda: {"app": "Code"}, messages.append, logs.append, interval=60)
        self.assertIn("started", manager.start(5, "write tests"))
        status = manager.status()
        self.assertEqual(status["minutes"], 5)
        self.assertEqual(status["task"], "write tests")
        self.assertEqual(status["remaining_seconds"], 300)
        self.assertIn("ended", manager.stop())
        self.assertIsNone(manager.status())
        self.assertIn("No focus session", manager.stop())


if __name__ == "__main__":
    unittest.main()
