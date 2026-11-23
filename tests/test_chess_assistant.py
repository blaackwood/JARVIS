"""Tests for actions/chess_assistant.py (board reading, tracking, tool wiring).

Boards are rendered synthetically with OpenCV, so no screen, engine or voice is needed
except where a test says so.
"""
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2
import numpy as np

import chess
from actions import chess_assistant as ca

_TEST_TMP = None
_TEST_PATCHES = []


def setUpModule():
    global _TEST_TMP, _TEST_PATCHES
    _TEST_TMP = tempfile.TemporaryDirectory(prefix="jarvis-test-chess-assistant-")
    root = Path(_TEST_TMP.name)
    _TEST_PATCHES = [
        patch.object(ca, "_DATA", root / "memory"),
        patch.object(ca, "_CFG", root / "memory" / "config.json"),
        patch.object(ca, "_TPL", root / "memory" / "templates.npz"),
    ]
    for item in _TEST_PATCHES:
        item.start()


def tearDownModule():
    for item in reversed(_TEST_PATCHES):
        item.stop()
    if _TEST_TMP is not None:
        _TEST_TMP.cleanup()


SQ = 80
LIGHT, DARK = (200, 220, 235), (90, 130, 100)


def render(board, white_bottom=True, highlight=None):
    img = np.zeros((8 * SQ, 8 * SQ, 3), np.uint8)
    for r in range(8):
        for c in range(8):
            sq = ca.sq_from_rc(r, c, white_bottom)
            col = LIGHT if (chess.square_file(sq) + chess.square_rank(sq)) % 2 else DARK
            if highlight and sq in highlight:
                col = (120, 220, 230)
            img[r * SQ:(r + 1) * SQ, c * SQ:(c + 1) * SQ] = col
            p = board.piece_at(sq)
            if not p:
                continue
            cx, cy = c * SQ + SQ // 2, r * SQ + SQ // 2
            white = p.color == chess.WHITE
            fill, edge, txt = ((245, 245, 245), (20, 20, 20), (20, 20, 20)) if white else ((30, 30, 30), (240, 240, 240), (240, 240, 240))
            cv2.circle(img, (cx, cy), 28, fill, -1)
            cv2.circle(img, (cx, cy), 28, edge, 2)
            cv2.putText(img, p.symbol().upper(), (cx - 11, cy + 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, txt, 2)
    return img


class VisionTests(unittest.TestCase):
    def _templates(self, wb):
        return ca.build_templates(render(chess.Board(), wb), wb)

    def test_reads_initial_position_both_orientations(self):
        for wb in (True, False):
            T, L, thr = self._templates(wb)
            got = ca.read_position(render(chess.Board(), wb), T, L, thr, wb)
            self.assertEqual(got, ca.symmap(chess.Board()))

    def test_tracks_random_games_with_highlighted_last_move(self):
        rnd = random.Random(7)
        for wb in (True, False):
            T, L, thr = self._templates(wb)
            for _ in range(3):
                b = chess.Board()
                tr = ca.Tracker()
                tr.init_from(ca.symmap(b), chess.WHITE)
                for _ply in range(30):
                    if b.is_game_over():
                        break
                    m = rnd.choice(list(b.legal_moves))
                    b.push(m)
                    img = render(b, wb, highlight={m.from_square, m.to_square})
                    pl = ca.read_position(img, T, L, thr, wb)
                    self.assertEqual(pl, ca.symmap(b))
                    self.assertEqual(tr.update(pl), "mov")
                    self.assertEqual(ca.symmap(tr.board), ca.symmap(b))

    def test_guess_orientation(self):
        self.assertTrue(ca.guess_white_bottom(render(chess.Board(), True)))
        self.assertFalse(ca.guess_white_bottom(render(chess.Board(), False)))


class SpeechTests(unittest.TestCase):
    def test_phrases(self):
        b = chess.Board()
        self.assertEqual(ca.frase(b, chess.Move.from_uci("g1f3")), "cavalo, g 1 para f 3")
        b = chess.Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
        self.assertEqual(ca.frase(b, chess.Move.from_uci("e1g1")), "roque pequeno")
        self.assertEqual(ca.frase(b, chess.Move.from_uci("e1c1")), "roque grande")
        b = chess.Board("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1")
        self.assertTrue(ca.frase(b, chess.Move.from_uci("a1a8")).endswith("xeque-mate"))


class WiringTests(unittest.TestCase):
    def test_tool_is_discoverable(self):
        from core.action_loader import _validate
        import actions.chess_assistant as mod
        rec = _validate(mod, "chess_assistant.py")
        self.assertTrue(rec.valid, rec.error)
        self.assertEqual(rec.name, "chess_assistant")

    def test_authorization_allows_it(self):
        from core.authorization import classify_action
        self.assertEqual(classify_action("chess_assistant", {"action": "start"}), "reversible_change")
        self.assertEqual(classify_action("chess_assistant", {"action": "status"}), "read_only")

    def test_arrow_payload_is_accepted_by_overlay(self):
        from gui.screen_marks import normalize_screen_marks

        class P:
            got = None

            def show_screen_marks(self, payload, operation="append"):
                P.got = (payload, operation)

        mon = {"left": 0, "top": 0, "width": 1920, "height": 1080}
        ca._desenhar_seta(P(), mon, [400, 100, 800, 800], True, chess.E2, chess.E4)
        import time as _t
        for _ in range(40):          # a seta agora e desenhada numa thread propria
            if P.got is not None:
                break
            _t.sleep(0.05)
        self.assertIsNotNone(P.got)
        marks = P.got[0]["marks"]
        self.assertEqual([m["kind"] for m in marks], ["ring", "arrow", "ring"])
        # e2 fica na coluna 4, linha 6 do tabuleiro: x = 400+4.5*100, y = 100+6.5*100
        ax, ay = marks[1]["points"][0]
        self.assertAlmostEqual(ax, 850 * 1000 / 1920, delta=0.5)
        self.assertAlmostEqual(ay, 750 * 1000 / 1080, delta=0.5)
        normalize_screen_marks(P.got[0])

    def test_actions_without_setup_fail_politely(self):
        self.assertIn("CHESS_UNAVAILABLE", ca.chess_assistant({"action": "calibrate"}, player=None))
        self.assertIn("CHESS_INVALID_ACTION", ca.chess_assistant({"action": "dance"}))
        self.assertTrue(ca.chess_assistant({"action": "status"}).startswith("CHESS_"))

    def test_stockfish_found_and_plays(self):
        path = ca._achar_stockfish()
        if not path:
            self.skipTest("stockfish not installed")
        eng = chess.engine.SimpleEngine.popen_uci(path)
        try:
            move = eng.play(chess.Board(), chess.engine.Limit(time=0.1)).move
            self.assertIn(move, list(chess.Board().legal_moves))
        finally:
            eng.quit()


class ResyncTests(unittest.TestCase):
    def test_turn_inferred_from_who_just_moved(self):
        b = chess.Board()
        antigo = b.copy()
        b.push_san("e4")  # brancas mexeram -> vez das pretas
        self.assertEqual(ca._vez_provavel(antigo, ca.symmap(b), chess.WHITE), chess.BLACK)
        antigo = b.copy()
        b.push_san("e5")  # pretas mexeram -> vez das brancas
        self.assertEqual(ca._vez_provavel(antigo, ca.symmap(b), chess.BLACK), chess.WHITE)
        self.assertEqual(ca._vez_provavel(None, ca.symmap(b), chess.BLACK), chess.BLACK)

    def test_resync_action_requires_running_session(self):
        self.assertIn("CHESS_NOT_RUNNING", ca.chess_assistant({"action": "resync"}))


if __name__ == "__main__":
    unittest.main()

