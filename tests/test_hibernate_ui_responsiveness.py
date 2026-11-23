import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.hibernate import start_hibernate_preparation


class HibernateResponsivenessTests(unittest.TestCase):
    def test_checkpoint_callback_runs_outside_calling_thread(self):
        caller = threading.get_ident()
        entered = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        observed = {}

        def callback(mode):
            observed["mode"] = mode
            observed["thread"] = threading.get_ident()
            entered.set()
            self.assertTrue(release.wait(2))
            return True, "checkpoint complete"

        def report(ok, detail):
            observed["result"] = (ok, detail)
            observed["report_thread"] = threading.get_ident()
            finished.set()

        worker = start_hibernate_preparation(callback, "pause", report)
        try:
            self.assertTrue(entered.wait(1), "checkpoint worker did not start")
            self.assertTrue(worker.is_alive())
            self.assertNotEqual(observed["thread"], caller)
            self.assertFalse(finished.is_set())
        finally:
            release.set()

        self.assertTrue(finished.wait(1), "checkpoint result was not delivered")
        worker.join(timeout=1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(observed["mode"], "pause")
        self.assertEqual(observed["result"], (True, "checkpoint complete"))
        self.assertEqual(observed["report_thread"], observed["thread"])

    def test_callback_exception_is_reported_without_crashing_worker(self):
        finished = threading.Event()
        observed = {}

        def callback(_mode):
            raise RuntimeError("simulated checkpoint failure")

        worker = start_hibernate_preparation(
            callback, "continue",
            lambda ok, detail: (observed.update(ok=ok, detail=detail), finished.set()),
        )
        self.assertTrue(finished.wait(1))
        worker.join(timeout=1)
        self.assertFalse(worker.is_alive())
        self.assertFalse(observed["ok"])
        self.assertIn("simulated checkpoint failure", observed["detail"])


if __name__ == "__main__":
    unittest.main()
