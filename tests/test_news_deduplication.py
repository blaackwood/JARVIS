import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from actions import web_search


class NewsDeduplicationTests(unittest.TestCase):
    def test_first_startup_announcement_is_saved_and_next_is_suppressed(self):
        with tempfile.TemporaryDirectory() as folder:
            history = Path(folder) / "news_history.json"
            articles = [
                {"title": "Microsoft restores services after global outage", "url": "https://example.com/1", "source": "AP"},
                {"title": "New climate report released", "url": "https://example.com/2", "source": "Reuters"},
            ]
            with patch.object(web_search, "NEWS_HISTORY_PATH", history), \
                 patch.object(web_search, "_rss_news", return_value=articles):
                first = web_search._news("world news", only_new=True)
                self.assertIn("Microsoft restores services", first)
                self.assertIn("New climate report", first)
                # Fetching is not proof that the user heard the briefing.
                self.assertFalse(history.exists())
                committed = web_search._remember_announced_headlines(first, "world news")
                self.assertEqual(committed, 2)
                second = web_search._news("world news", only_new=True)

            self.assertEqual(second, "No new headlines since the previous briefing.")
            saved = json.loads(history.read_text(encoding="utf-8"))
            self.assertEqual(len(saved["items"]), 2)

    def test_headline_case_accents_and_punctuation_do_not_bypass_dedup(self):
        with tempfile.TemporaryDirectory() as folder:
            history = Path(folder) / "news_history.json"
            first = [{"title": "Café: novo relatório — hoje!"}]
            repeated = [{"title": "CAFE novo relatorio hoje"}]
            with patch.object(web_search, "NEWS_HISTORY_PATH", history):
                announced = web_search._filter_and_remember_news(first, remember=True)
                again = web_search._filter_and_remember_news(repeated, remember=True)
            self.assertEqual(len(announced), 1)
            self.assertEqual(again, [])

    def test_manual_news_search_does_not_apply_announcement_history(self):
        with tempfile.TemporaryDirectory() as folder:
            history = Path(folder) / "news_history.json"
            articles = [{"title": "Same headline", "url": "https://example.com/1"}]
            with patch.object(web_search, "NEWS_HISTORY_PATH", history), \
                 patch.object(web_search, "_rss_news", return_value=articles):
                web_search._news("topic", only_new=True)
                manual = web_search._news("topic", only_new=False)
            self.assertIn("Same headline", manual)

    def test_generic_english_news_query_uses_brazilian_portuguese_feed(self):
        articles = [{"title": "Notícia atual do Brasil", "url": "https://example.com"}]
        with patch.object(web_search, "_rss_news", return_value=articles) as rss:
            result = web_search._news("top world news today")
        self.assertIn("Notícia atual do Brasil", result)
        self.assertEqual(rss.call_args.args[0], "notícias do Brasil e do mundo hoje")

    def test_history_is_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            history = Path(folder) / "news_history.json"
            with patch.object(web_search, "NEWS_HISTORY_PATH", history):
                articles = [{"title": f"Headline number {i}"} for i in range(1100)]
                fresh = web_search._filter_and_remember_news(articles, remember=True)
            saved = json.loads(history.read_text(encoding="utf-8"))
            self.assertEqual(len(fresh), 1100)
            self.assertEqual(len(saved["items"]), web_search._NEWS_HISTORY_MAX)


if __name__ == "__main__":
    unittest.main()
