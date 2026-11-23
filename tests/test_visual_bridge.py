import asyncio
import threading
import unittest
from types import SimpleNamespace

from ui import JarvisUI


class _StatusSignal:
    def __init__(self):
        self.payload = None

    def emit(self, payload, ack):
        self.payload = dict(payload)
        ack["ok"] = True
        ack["event"].set()


class _TimedCaptionSignal:
    def __init__(self):
        self.caption = None
        self.audible_at = None

    def emit(self, caption, audible_at):
        self.caption = caption
        self.audible_at = audible_at


class _BoolSignal:
    def __init__(self):
        self.value = None

    def emit(self, value, ack):
        self.value = bool(value)
        ack["ok"] = True
        ack["event"].set()


class _StateSignal:
    def emit(self, ack):
        ack["done"] = True
        ack["event"].set()


class _AcknowledgingSignal:
    def emit(self, payload, ack):
        ack["ok"] = True
        ack["event"].set()


class _FailingSignal:
    def emit(self, payload, ack):
        ack["error"] = "RuntimeError: paint failed"
        ack["event"].set()


class _SilentSignal:
    def emit(self, payload, ack):
        pass


class VisualBridgeTests(unittest.TestCase):
    def _ui(self, signal):
        ui = object.__new__(JarvisUI)
        ui._win = SimpleNamespace(_visual_show_sig=signal)
        return ui

    def test_live_voice_rate_uses_adaptive_smoothing(self):
        ui = object.__new__(JarvisUI)
        ui._visual_voice_cps = 15.0
        self.assertEqual(ui.get_visual_voice_cps(), 15.0)
        self.assertAlmostEqual(ui.update_visual_voice_cps(10.0), 13.0)
        self.assertAlmostEqual(ui.get_visual_voice_cps(), 13.0)
        # Out-of-range observations are bounded before they affect the average.
        self.assertAlmostEqual(ui.update_visual_voice_cps(40.0), 19.8)
        self.assertAlmostEqual(ui.update_visual_voice_cps(1.0), 15.08)

    def test_visual_caption_waits_for_pcm_received_in_the_current_turn(self):
        from main import JarvisLive

        self.assertFalse(JarvisLive._visual_turn_has_received_pcm(0.0))
        self.assertFalse(JarvisLive._visual_turn_has_received_pcm(float("nan")))
        self.assertFalse(JarvisLive._visual_turn_has_received_pcm("invalid"))
        self.assertTrue(JarvisLive._visual_turn_has_received_pcm(0.001))

    def test_ui_sends_timed_caption_and_audible_boundary_in_one_signal(self):
        signal = _TimedCaptionSignal()
        ui = object.__new__(JarvisUI)
        ui._win = SimpleNamespace(_visual_timed_caption_sig=signal)

        ui.set_visual_timed_caption("A hipotenusa é o maior lado.", 123.456)

        self.assertEqual(signal.caption, "A hipotenusa é o maior lado.")
        self.assertEqual(signal.audible_at, 123.456)

    def test_timed_caption_keeps_a_full_length_lesson_transcript(self):
        signal = _TimedCaptionSignal()
        ui = object.__new__(JarvisUI)
        ui._win = SimpleNamespace(_visual_timed_caption_sig=signal)
        transcript = " ".join(["A luz alimenta a planta."] * 80)

        ui.set_visual_timed_caption(transcript, 123.456)

        self.assertGreater(len(transcript), 1200)
        self.assertEqual(signal.caption, transcript)

    def test_visual_checkpoint_keeps_valid_future_speaker_cursor(self):
        from main import JarvisLive
        from unittest.mock import patch

        engine = object.__new__(JarvisLive)
        engine._play_cursor = 100.450
        engine._out_latency = 0.213
        engine.audio_in_queue = SimpleNamespace(_queue=[bytes(24000)])
        with patch("main.time.time", return_value=100.0):
            audible_at = engine._visual_transcript_audible_at()

        # 0.45 s already scheduled at the speaker + 0.50 s still in the
        # Python PCM queue + 18 ms safety margin. The avatar's 363 ms
        # drift guard must not pull this visual timestamp backwards.
        self.assertAlmostEqual(audible_at, 100.968, places=3)

    def test_visual_checkpoint_uses_first_sound_fallback_only_for_stale_cursor(self):
        from main import JarvisLive, _FIRST_SOUND
        from unittest.mock import patch

        engine = object.__new__(JarvisLive)
        engine._play_cursor = 98.0
        engine._out_latency = 0.213
        engine.audio_in_queue = SimpleNamespace(_queue=[])
        with patch("main.time.time", return_value=100.0):
            audible_at = engine._visual_transcript_audible_at()
        self.assertAlmostEqual(audible_at, 100.0 + _FIRST_SOUND + 0.018, places=3)

    def test_transcript_chunk_merge_accepts_cumulative_snapshots(self):
        from main import _append_transcript_chunk

        chunks = []
        self.assertTrue(_append_transcript_chunk("Este e", chunks))
        self.assertTrue(_append_transcript_chunk("Este e um triângulo", chunks))
        self.assertEqual(" ".join(chunks), "Este e um triângulo")

    def test_transcript_chunk_merge_appends_incremental_overlap_once(self):
        from main import _append_transcript_chunk

        chunks = ["Os lados menores"]
        self.assertTrue(_append_transcript_chunk("menores são os catetos", chunks))
        self.assertEqual(" ".join(chunks), "Os lados menores são os catetos")
        self.assertFalse(_append_transcript_chunk("são os catetos", chunks))
        self.assertEqual(" ".join(chunks), "Os lados menores são os catetos")

    def test_incremental_transcript_keeps_repeated_articles_in_spoken_order(self):
        from main import _append_transcript_chunk
        chunks = ["A luz chega"]
        for text in (" à", " folha", " e", " a", " planta", " usa", " a", " energia."):
            self.assertTrue(_append_transcript_chunk(text, chunks, incremental=True))
        self.assertEqual(" ".join(chunks), "A luz chega à folha e a planta usa a energia.")

    def test_transcript_chunk_merge_ignores_stale_embedded_snapshot(self):
        from main import _append_transcript_chunk

        chunks = ["A soma dos quadrados é igual a c ao quadrado"]
        self.assertFalse(_append_transcript_chunk("dos quadrados é igual a c", chunks))
        self.assertEqual(len(chunks), 1)

    def test_lesson_caption_bridge_waits_for_qt_acknowledgement(self):
        signal = _StatusSignal()
        ui = object.__new__(JarvisUI)
        ui._win = SimpleNamespace(_visual_lesson_sig=signal)
        ui.set_visual_lesson_status("Etapa 2", 2, 4, waiting=True, timeout=0.2)
        self.assertEqual(signal.payload, {
            "caption": "Etapa 2", "index": 2, "total": 4,
            "waiting": True, "draw_duration": None,
        })
        ui.set_visual_lesson_status("Etapa 3", 3, 4, draw_duration=4.75, timeout=0.2)
        self.assertEqual(signal.payload["draw_duration"], 4.75)

    def test_main_window_quiz_answer_forwarding_uses_regular_text_command_callback(self):
        import threading
        from gui.window import MainWindow

        received = []
        ready = threading.Event()
        window = MainWindow.__new__(MainWindow)
        window.on_text_command = lambda message: (received.append(message), ready.set())
        window._forward_visual_quiz_answer({
            "element_id": "quiz-1",
            "attempt": 2,
            "question": "Qual é a capital do Brasil?",
            "choice": "Brasília",
            "answer": "B",
            "correct": True,
            "explanation": "Brasília é a capital federal.",
        })
        self.assertTrue(ready.wait(1.0))
        self.assertEqual(len(received), 1)
        self.assertIn("VISUAL_QUIZ_ANSWERED", received[0])
        self.assertIn("Brasília", received[0])
        self.assertIn("Automatic result: correct", received[0])
        self.assertIn("Attempt: 2", received[0])

    def test_mouse_passthrough_bridge_acknowledges_both_modes(self):
        signal = _BoolSignal()
        ui = object.__new__(JarvisUI)
        ui._win = SimpleNamespace(_visual_passthrough_sig=signal)
        ui.set_visual_input_passthrough(True, timeout=0.2)
        self.assertTrue(signal.value)
        ui.set_visual_input_passthrough(False, timeout=0.2)
        self.assertFalse(signal.value)

    def test_visual_animation_state_is_returned_from_qt(self):
        ui = object.__new__(JarvisUI)
        ui._win = SimpleNamespace(_visual_state_sig=_StateSignal())
        self.assertTrue(ui.visual_animation_done(timeout=0.2))

    def test_show_visual_board_returns_only_after_qt_acknowledges(self):
        ui = self._ui(_AcknowledgingSignal())
        self.assertTrue(ui.show_visual_board({"title": "Teste"}, timeout=0.2))

    def test_show_visual_board_propagates_render_failure(self):
        ui = self._ui(_FailingSignal())
        with self.assertRaisesRegex(RuntimeError, "paint failed"):
            ui.show_visual_board({"title": "Teste"}, timeout=0.2)

    def test_show_visual_board_times_out_if_qt_never_responds(self):
        ui = self._ui(_SilentSignal())
        with self.assertRaises(TimeoutError):
            ui.show_visual_board({"title": "Teste"}, timeout=0.1)


class ContinuousLessonTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_packets_reach_qt_as_a_progressive_seven_beat_lesson(self):
        import asyncio
        from unittest.mock import AsyncMock, Mock, patch
        from PyQt6.QtCore import QObject, pyqtSignal, Qt
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtTest import QTest
        from gui.visual_board import VisualBoardOverlay
        from gui.window import MainWindow
        from actions.present_visual_lesson import present_visual_lesson
        from main import JarvisLive, RECEIVE_SAMPLE_RATE

        app = QApplication.instance() or QApplication([])
        board = VisualBoardOverlay()
        class Signals(QObject):
            _visual_show_sig = pyqtSignal(object, object)
            _visual_lesson_sig = pyqtSignal(object, object)
            _visual_audio_sig = pyqtSignal(object)
            _muted = False
        signals = Signals()
        def show(payload, ack):
            board.set_content(payload)
            ack["ok"] = True
            ack["event"].set()
        def status(payload, ack):
            board.set_lesson_status(**{key: payload[key] for key in
                                   ("caption", "index", "total", "waiting", "draw_duration")})
            ack["ok"] = True
            ack["event"].set()
        signals._visual_show_sig.connect(show)
        signals._visual_lesson_sig.connect(status)
        signals._visual_audio_sig.connect(lambda payload: MainWindow._set_visual_audio_window(
            SimpleNamespace(_visual_board=board), payload))
        ui = object.__new__(JarvisUI)
        ui._win = signals
        ui.start_marker_lesson = None
        ui._visual_voice_cps = 13.0
        for name in ("set_state", "write_log", "set_audio_level", "push_visemes"):
            setattr(ui, name, Mock())
        class Session:
            def __init__(self):
                self.packets = asyncio.Queue()
                self.responses = None
            async def receive(self):
                while True:
                    yield await self.packets.get()
            async def send_tool_response(self, function_responses):
                self.responses = function_responses
        output = Mock()
        output.latency = 0.01
        written = [0.0]
        audible = [0.0]
        output.written_seconds.side_effect = lambda: written[0]
        output.audible_seconds.side_effect = lambda: audible[0]
        output.write.side_effect = lambda data: written.__setitem__(
            0, written[0] + len(data) / (2 * RECEIVE_SAMPLE_RATE))
        engine = object.__new__(JarvisLive)
        engine.ui = ui
        engine.session = Session()
        engine.audio_in_queue = asyncio.Queue(maxsize=120)
        engine._action_registry = Mock()
        engine._action_registry.has.return_value = True
        engine._action_registry.scheduling.return_value = None
        engine._action_registry.run.side_effect = lambda name, args, ctx: present_visual_lesson(
            args, player=ctx["player"])
        engine._plugin_registry = Mock()
        engine._plugin_registry.scheduling.return_value = None
        engine._clear_stall = Mock()
        engine._flush_pending_vision = AsyncMock()
        engine._marker_lesson_active = False
        engine._marker_tool_response_sent = None
        engine._marker_tool_reply_complete = None
        engine._interrupted = False
        engine._turn_done_event = None
        engine._pcm_player = None
        engine._visemes = Mock()
        engine._echo = Mock()
        engine.set_speaking = Mock()
        captions = [
            "A fotossíntese é o processo que as plantas usam para criar seu próprio alimento e energia para crescer.",
            "A luz do Sol fornece a energia que chega à folha.",
            "As raízes absorvem água do solo e levam essa água até a folha.",
            "O gás carbônico do ar também entra na folha.",
            "A clorofila captura a luz e participa da transformação dentro da folha.",
            "A planta produz glicose para crescer e libera oxigênio para o ar.",
            "Agora escolha qual é a fonte de energia da fotossíntese.",
        ]
        elements = [
            [{"type": "polygon", "color": "green", "fill": True, "stroke_width": 4,
              "points": [{"x": 45, "y": 55}, {"x": 40, "y": 35}, {"x": 55, "y": 17},
                         {"x": 64, "y": 40}, {"x": 56, "y": 58}]},
             {"type": "text", "x": 45, "y": 63, "width": 15, "text": "Folha"}],
            [{"type": "circle", "x": 15, "y": 15, "radius": 10, "color": "amber", "fill": True},
             {"type": "arrow", "x": 24, "y": 19, "x2": 42, "y2": 32, "color": "amber"},
             {"type": "text", "x": 8, "y": 31, "width": 20, "text": "Energia solar", "color": "amber"}],
            [{"type": "polyline", "color": "blue", "points": [
                {"x": 33, "y": 92}, {"x": 45, "y": 82}, {"x": 53, "y": 92}]},
             {"type": "arrow", "x": 45, "y": 80, "x2": 48, "y2": 58, "color": "blue"},
             {"type": "text", "x": 15, "y": 82, "width": 20, "text": "Água · H₂O", "color": "blue"}],
            [{"type": "arrow", "x": 19, "y": 54, "x2": 40, "y2": 46, "color": "cyan"},
             {"type": "text", "x": 4, "y": 50, "width": 30, "text": "Gás carbônico · CO₂"}],
            [{"type": "circle", "x": 49, "y": 35, "radius": 3, "color": "green", "fill": True},
             {"type": "circle", "x": 55, "y": 43, "radius": 3, "color": "green", "fill": True},
             {"type": "text", "x": 43, "y": 5, "width": 25, "text": "Clorofila", "color": "green"}],
            [{"type": "arrow", "x": 65, "y": 32, "x2": 77, "y2": 24, "color": "green"},
             {"type": "text", "x": 78, "y": 18, "width": 21, "text": "Oxigênio · O₂", "color": "green"},
             {"type": "arrow", "x": 63, "y": 49, "x2": 77, "y2": 48, "color": "pink"},
             {"type": "formula", "x": 77, "y": 43, "width": 22, "height": 14,
              "text": "Glicose", "color": "pink"}],
            [{"type": "quiz", "id": "quiz", "x": 65, "y": 65, "width": 34, "height": 32,
              "title": "De onde vem a energia?", "options": ["Luz do Sol", "Do solo"],
              "answer": "Luz do Sol", "explanation": "A luz solar fornece a energia da transformação."}],
        ]
        args = {"title": "Como funciona a Fotossíntese", "beats": [
            {"say": caption, "elements": group} for caption, group in zip(captions, elements)]}
        def packet(data=None, text=None, tool=None):
            content = (SimpleNamespace(output_transcription=SimpleNamespace(text=text),
                       input_transcription=None, turn_complete=False) if text else None)
            return SimpleNamespace(data=data, server_content=content, tool_call=tool)
        async def wait(predicate):
            deadline = asyncio.get_running_loop().time() + 3
            while not predicate():
                if asyncio.get_running_loop().time() >= deadline:
                    self.fail("Live-to-Qt signal did not arrive")
                app.processEvents()
                await asyncio.sleep(0.001)
            app.processEvents()
        def capture(name):
            app.processEvents()
            board.repaint()
            image = board.grab().toImage()
            directory = getattr(self, "preview_dir", None)
            if directory:
                self.assertTrue(image.save(str(directory / name)))
            return image
        with patch("main.PcmPlayer", return_value=output), \
             patch("main.get_output_device", return_value=None), \
             patch("main.audio_devices.resolve", return_value=None), \
             patch("main._pcm_visemes", return_value=[]):
            receiver = asyncio.create_task(engine._receive_audio())
            speaker = asyncio.create_task(engine._play_audio())
            try:
                fc = SimpleNamespace(id="lesson", name="present_visual_lesson", args=args)
                await engine.session.packets.put(packet(tool=SimpleNamespace(function_calls=[fc])))
                await wait(lambda: engine.session.responses is not None)
                blank = capture("lesson-stream-blank.png")
                await engine.session.packets.put(packet(data=bytes(int(RECEIVE_SAMPLE_RATE * 0.8))))
                await engine.session.packets.put(packet(text="A fotossíntese"))
                await wait(lambda: bool(board._lesson_transcript_checkpoints))
                audible[0] = 0.2
                board._tick_drawing()
                self.assertEqual(board._reveal_index, 0)
                self.assertGreater(board._reveal_progress, 0)
                first = capture("lesson-stream-first-stroke.png")
                self.assertNotEqual(blank, first)
                cumulative = ""
                for index, caption in enumerate(captions):
                    cumulative = (cumulative + " " + caption).strip()
                    start = written[0]
                    await engine.session.packets.put(packet(data=bytes(RECEIVE_SAMPLE_RATE * 2)))
                    await engine.session.packets.put(packet(text=cumulative))
                    expected = len(board._spoken_tokens(caption))
                    await wait(lambda: board._lesson_transcript_checkpoints[-1][1][index] == expected)
                    audible[0] = start + 0.5
                    board._tick_drawing()
                    self.assertEqual(board._lesson_index, index + 1)
                    self.assertFalse(board._quiz_rects)
                    if index == 3:
                        capture("lesson-stream-middle.png")
                    audible[0] = written[0]
                    board._tick_drawing()
                    app.processEvents()
                self.assertEqual(board._lesson_caption, "Etapas concluídas")
                capture("lesson-stream-complete.png")
                self.assertEqual(len(board._quiz_rects), 2)
                answers = []
                board.quiz_answered.connect(answers.append)
                QTest.mouseClick(board, Qt.MouseButton.LeftButton,
                                 pos=board._quiz_rects[0][2].center().toPoint())
                self.assertTrue(answers[0]["correct"])
                capture("lesson-stream-answer.png")
            finally:
                receiver.cancel()
                speaker.cancel()
                await asyncio.gather(receiver, speaker, return_exceptions=True)
                board.close()

    async def test_tool_handoff_streams_first_audio_before_turn_complete(self):
        import asyncio
        from unittest.mock import AsyncMock, Mock, patch
        from actions.present_visual_lesson import present_visual_lesson
        from main import JarvisLive

        class Session:
            def __init__(self):
                self.packets = asyncio.Queue()
                self.tool_sent = asyncio.Event()
                self.responses = None
                self.send_client_content = AsyncMock()

            async def receive(self):
                while True:
                    yield await self.packets.get()

            async def send_tool_response(self, function_responses):
                self.responses = function_responses
                self.tool_sent.set()

        def packet(data=None, server_content=None, tool_call=None):
            return SimpleNamespace(data=data, server_content=server_content,
                                   tool_call=tool_call, session_resumption_update=None)

        engine = object.__new__(JarvisLive)
        engine.session = Session()
        engine.audio_in_queue = asyncio.Queue()
        engine.ui = Mock()
        engine.ui.muted = False
        engine.ui.get_visual_voice_cps.return_value = 13.0
        engine.ui.start_marker_lesson = None
        engine._action_registry = Mock()
        engine._action_registry.has.return_value = True
        engine._action_registry.scheduling.return_value = None
        engine._action_registry.run.side_effect = (
            lambda name, args, ctx: present_visual_lesson(args, player=ctx["player"])
        )
        engine._plugin_registry = Mock()
        engine._plugin_registry.scheduling.return_value = None
        engine._clear_stall = Mock()
        engine._flush_pending_vision = AsyncMock()
        engine._marker_lesson_active = False
        engine._marker_tool_response_sent = None
        engine._marker_tool_reply_complete = None
        engine._interrupted = False
        engine._turn_done_event = None
        engine._play_cursor = 0.0
        engine._visemes = Mock()
        fc = SimpleNamespace(id="lesson", name="present_visual_lesson", args={
            "title": "Fotossíntese",
            "beats": [
                {"say": "A luz chega à folha.", "elements": [
                    {"type": "circle", "x": 20, "y": 20, "radius": 4}]},
                {"say": "A planta produz glicose.", "elements": [
                    {"type": "text", "text": "Glicose"}]},
            ],
        })
        task = asyncio.create_task(engine._receive_audio())
        try:
            await engine.session.packets.put(packet(
                tool_call=SimpleNamespace(function_calls=[fc])
            ))
            await asyncio.wait_for(engine.session.tool_sent.wait(), 2.0)
            result = engine.session.responses[0].response["result"]
            self.assertIn("Begin speaking immediately", result)
            self.assertIn("A planta produz glicose.", result)
            self.assertIsNone(engine.ui.start_marker_lesson)
            engine.session.send_client_content.assert_not_awaited()
            from core.pcm_clock import LessonMark
            self.assertEqual(list(engine.audio_in_queue._queue),
                             [LessonMark("narration_start", 0)])
            engine.audio_in_queue.get_nowait()

            pcm = bytes(4800)
            await engine.session.packets.put(packet(data=pcm))
            first = await asyncio.wait_for(engine.audio_in_queue.get(), 2.0)
            second = await asyncio.wait_for(engine.audio_in_queue.get(), 2.0)
            self.assertEqual(first + second, pcm)
            self.assertTrue(engine.audio_in_queue.empty())

            transcription = SimpleNamespace(text="A luz chega à folha.")
            content = SimpleNamespace(output_transcription=transcription,
                                      input_transcription=None, turn_complete=False)
            await engine.session.packets.put(packet(server_content=content))
            from core.pcm_clock import CaptionMark
            checkpoint = await asyncio.wait_for(engine.audio_in_queue.get(), 2.0)
            self.assertEqual(checkpoint, CaptionMark("A luz chega à folha."))
            engine.ui.set_visual_timed_caption.assert_not_called()
            engine.session.send_client_content.assert_not_awaited()
            engine._last_out_logged = ""
            engine._asst_name = "JARVIS"
            engine._session_log = []
            engine._conversation_id = None
            engine._dashboard = None
            engine._vision_close_pending = False
            engine.ui.update_visual_voice_cps.return_value = 13.0
            done = SimpleNamespace(output_transcription=None,
                                   input_transcription=None, turn_complete=True)
            with patch("main._archive_message"):
                await engine.session.packets.put(packet(server_content=done))
                end = await asyncio.wait_for(engine.audio_in_queue.get(), 2.0)
                self.assertEqual(end, LessonMark("narration_end", 0))
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

    async def test_caption_fifo_is_mapped_after_preceding_pcm_before_following_pcm(self):
        import asyncio
        from unittest.mock import Mock, patch
        from main import JarvisLive, RECEIVE_SAMPLE_RATE
        from core.pcm_clock import CaptionMark

        loop = asyncio.get_running_loop()
        sent = asyncio.Event()
        output = Mock()
        output.latency = 0.01
        position = [5.0]
        output.written_seconds.side_effect = lambda: position[0]
        output.audible_seconds.return_value = 5.0
        def write(data):
            position[0] += len(data) / (2 * RECEIVE_SAMPLE_RATE)
            if position[0] >= 5.3:
                loop.call_soon_threadsafe(sent.set)
        output.write.side_effect = write
        engine = object.__new__(JarvisLive)
        engine.audio_in_queue = asyncio.Queue()
        engine.ui = Mock()
        engine.set_speaking = Mock()
        engine._echo = Mock()
        engine._visemes = Mock()
        engine._turn_done_event = None
        engine._pcm_player = None
        for item in (bytes(9600), CaptionMark("A fotossíntese"), bytes(4800)):
            engine.audio_in_queue.put_nowait(item)
        with patch("main.PcmPlayer", return_value=output), \
             patch("main.get_output_device", return_value=None), \
             patch("main.audio_devices.resolve", return_value=None), \
             patch("main._pcm_visemes", return_value=[]):
            task = asyncio.create_task(engine._play_audio())
            try:
                await asyncio.wait_for(sent.wait(), 2.0)
                engine.ui.push_visual_stream_caption.assert_called_once_with(
                    "A fotossíntese", 5.2, output)
                self.assertEqual(output.write.call_count, 2)
                self.assertEqual(engine.ui.push_visual_stream_audio.call_count, 2)
            finally:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def test_interrupt_stops_the_continuous_lesson_and_flushes_audio(self):
        import asyncio
        from unittest.mock import Mock
        from main import JarvisLive

        engine = object.__new__(JarvisLive)
        engine.audio_in_queue = asyncio.Queue()
        engine.audio_in_queue.put_nowait(bytes(2400))
        engine.ui = Mock()
        engine.set_speaking = Mock()
        engine._visemes = Mock()
        engine._pcm_player = Mock()
        engine._turn_done_event = asyncio.Event()
        engine._turn_done_event.set()
        engine._engine = None
        engine._loop = None
        engine._marker_lesson_active = False
        engine._marker_lesson_task = None
        engine._marker_queue_original_maxsize = None

        engine.interrupt()

        self.assertTrue(engine._interrupted)
        self.assertTrue(engine.audio_in_queue.empty())
        engine._pcm_player.flush.assert_called_once()
        engine.ui.cancel_marker_lesson.assert_called_once()
        engine.ui.clear_visual_audio_clock.assert_called_once()
        engine.ui.set_visual_live_caption.assert_called_once_with("")
        self.assertFalse(engine._turn_done_event.is_set())

    async def test_first_audio_reaches_output_before_the_reply_finishes(self):
        import asyncio
        from unittest.mock import Mock, patch
        from main import JarvisLive

        loop = asyncio.get_running_loop()
        started = asyncio.Event()
        output = Mock()
        output.latency = 0.01
        output.written_seconds.return_value = 0.0
        output.audible_seconds.return_value = 0.0
        output.write.side_effect = lambda _data: loop.call_soon_threadsafe(started.set)
        engine = object.__new__(JarvisLive)
        engine.audio_in_queue = asyncio.Queue()
        engine.ui = Mock()
        engine.set_speaking = Mock()
        engine._echo = Mock()
        engine._visemes = Mock()
        engine._turn_done_event = asyncio.Event()
        engine._pcm_player = None
        engine._out_latency = 0.0
        pcm = bytes(2400)
        with patch("main.PcmPlayer", return_value=output), \
             patch("main.get_output_device", return_value=None), \
             patch("main.audio_devices.resolve", return_value=None), \
             patch("main._pcm_visemes", return_value=[]):
            task = asyncio.create_task(engine._play_audio())
            try:
                await engine.audio_in_queue.put(pcm)
                await asyncio.wait_for(started.wait(), 2.0)
                output.write.assert_called_once_with(pcm)
                self.assertFalse(engine._turn_done_event.is_set())
                engine.ui.push_visual_audio_window.assert_called_once()
            finally:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass


class MarkerFifoTests(unittest.IsolatedAsyncioTestCase):
    async def test_complete_beat_is_committed_as_start_pcm_end_in_one_fifo(self):
        import asyncio
        from main import JarvisLive
        from core.pcm_clock import LessonMark

        engine = object.__new__(JarvisLive)
        engine.audio_in_queue = asyncio.Queue(maxsize=120)
        committed = await engine._enqueue_marker_beat(
            4, [b"pcm-a", b"pcm-b", b"pcm-c"]
        )

        self.assertTrue(committed)
        items = [engine.audio_in_queue.get_nowait() for _ in range(5)]
        self.assertEqual(items[0], LessonMark("start", 4, 7))
        self.assertEqual(items[1:4], [b"pcm-a", b"pcm-b", b"pcm-c"])
        self.assertEqual(items[4], LessonMark("end", 4))
        self.assertEqual(engine._marker_end_enqueued_for, 4)

    async def test_beat_end_is_known_before_speaker_finishes_writing_pcm(self):
        import asyncio
        from unittest.mock import Mock, patch
        from main import JarvisLive, RECEIVE_SAMPLE_RATE

        engine = object.__new__(JarvisLive)
        engine.audio_in_queue = asyncio.Queue()
        engine.ui = Mock()
        engine.set_speaking = Mock()
        engine._echo = Mock()
        engine._visemes = Mock()
        engine._turn_done_event = None
        engine._pcm_player = None
        loop = asyncio.get_running_loop()
        write_started = asyncio.Event()
        release_write = threading.Event()
        player = Mock()
        player.latency = 0.01
        player.written_seconds.return_value = 3.0
        player.audible_seconds.return_value = 3.0

        def write(_data):
            loop.call_soon_threadsafe(write_started.set)
            release_write.wait(2.0)

        player.write.side_effect = write
        await engine._enqueue_marker_beat(1, [bytes(RECEIVE_SAMPLE_RATE * 2)])
        with patch("main.PcmPlayer", return_value=player), \
             patch("main.get_output_device", return_value=None), \
             patch("main.audio_devices.resolve", return_value=None), \
             patch("main._pcm_visemes", return_value=[]):
            task = asyncio.create_task(engine._play_audio())
            try:
                await asyncio.wait_for(write_started.wait(), timeout=2.0)
                self.assertEqual(engine.ui.push_lesson_mark.call_count, 2)
                self.assertEqual(engine.ui.push_lesson_mark.call_args_list[0].args,
                                 ("start", 1, 3.0, player))
                self.assertEqual(engine.ui.push_lesson_mark.call_args_list[1].args,
                                 ("end", 1, 4.0, player))
            finally:
                release_write.set()
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def test_prepared_audio_is_ordered_without_extra_conversation_turns(self):
        from unittest.mock import AsyncMock, Mock, patch
        from core.pcm_clock import LessonMark
        from main import JarvisLive

        engine = object.__new__(JarvisLive)
        engine.audio_in_queue = asyncio.Queue(maxsize=120)
        engine.session = SimpleNamespace(send_client_content=AsyncMock())
        engine._pcm_player = object()
        engine._marker_lesson_active = False
        engine._marker_lesson_task = None
        engine._marker_end_enqueued_for = 0
        engine._interrupted = False
        engine._loop = asyncio.get_running_loop()
        engine._turn_done_event = asyncio.Event()
        engine._visemes = Mock()
        engine.ui = Mock()
        gates = {caption: asyncio.Event() for caption in ("Primeira.", "Segunda.")}
        begun = set()

        async def speech(caption, voice):
            begun.add(caption)
            await gates[caption].wait()
            return b"\x01\x00" * (10 if caption == "Primeira." else 20)

        with patch("core.gemini.speech_pcm", new=AsyncMock(side_effect=speech), create=True), \
                patch("main.get_voice", return_value="Kore"):
            self.assertTrue(await engine._register_marker_lesson(list(gates), "Ordem"))
            task = engine._marker_lesson_task
            engine._marker_tool_response_sent.set()
            try:
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                self.assertEqual(begun, set(gates))
                gates["Segunda."].set()
                await asyncio.sleep(0)
                self.assertTrue(engine.audio_in_queue.empty())
                gates["Primeira."].set()
                for _ in range(100):
                    if engine.audio_in_queue.qsize() == 6:
                        break
                    await asyncio.sleep(0.001)
                self.assertTrue(engine._marker_lesson_active)
                self.assertFalse(await engine._register_marker_lesson(["Outra."], "Não sobrepor"))
                engine._marker_playback_done.set()
                await asyncio.wait_for(task, 1)
                items = list(engine.audio_in_queue._queue)
                self.assertEqual([item.index for item in items if isinstance(item, LessonMark)],
                                 [1, 1, 2, 2])
                self.assertEqual([item.frames for item in items if isinstance(item, LessonMark)
                                  and item.kind == "start"], [10, 20])
                self.assertEqual([item for item in items if isinstance(item, bytes)],
                                 [b"\x01\x00" * 10, b"\x01\x00" * 20])
                engine.session.send_client_content.assert_not_called()
            finally:
                if not task.done():
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task

    async def test_empty_beat_does_not_create_unsounded_markers(self):
        import asyncio
        from main import JarvisLive

        engine = object.__new__(JarvisLive)
        engine.audio_in_queue = asyncio.Queue()
        committed = await engine._enqueue_marker_beat(2, [])

        self.assertFalse(committed)
        self.assertTrue(engine.audio_in_queue.empty())

    async def test_marker_lesson_temporarily_expands_fifo_and_restores_it(self):
        import asyncio
        from main import JarvisLive

        engine = object.__new__(JarvisLive)
        engine.audio_in_queue = asyncio.Queue(maxsize=120)
        engine.session = object()
        engine._pcm_player = object()
        engine._marker_lesson_active = False
        engine._marker_lesson_task = None
        engine._marker_end_enqueued_for = 0
        engine._loop = asyncio.get_running_loop()
        engine.ui = SimpleNamespace(cancel_marker_lesson=lambda: None)
        engine._turn_done_event = asyncio.Event()
        engine._interrupted = False
        from unittest.mock import AsyncMock, patch

        with patch("core.gemini.speech_pcm", new=AsyncMock(return_value=None)), \
                patch("main.get_voice", return_value="Kore"):
            registered = await engine._register_marker_lesson(
                ["A fala curta da etapa."], "Teste"
            )
            self.assertTrue(registered)
            self.assertEqual(engine.audio_in_queue.maxsize, 1200)
            await asyncio.sleep(0)
            task = engine._marker_lesson_task
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(engine.audio_in_queue.maxsize, 120)
        self.assertIsNone(engine._marker_queue_original_maxsize)


class ExplanationRoutingTests(unittest.IsolatedAsyncioTestCase):
    def test_explanation_intent_patterns(self):
        from main import _looks_like_explanation_request
        for text in ("Como funciona a fotossíntese?",
                     "Como que funciona um motor?",
                     "me explica o teorema de Pitágoras",
                     "explique a fotossíntese",
                     "o que é fotossíntese",
                     "por que o céu é azul",
                     "me ensina a fazer café",
                     "qual é a diferença entre mitose e meiose"):
            self.assertTrue(_looks_like_explanation_request(text), text)
        for text in ("que horas são", "toca uma música", "bom dia senhor",
                     "abre o navegador", "obrigado, ficou ótimo"):
            self.assertFalse(_looks_like_explanation_request(text), text)

    @staticmethod
    def _engine_with_session():
        from unittest.mock import AsyncMock, Mock
        from main import JarvisLive

        class Session:
            def __init__(self):
                self.packets = asyncio.Queue()
                self.send_client_content = AsyncMock()
                self.responses = None

            async def receive(self):
                while True:
                    yield await self.packets.get()

            async def send_tool_response(self, function_responses):
                self.responses = function_responses

        engine = object.__new__(JarvisLive)
        engine.session = Session()
        engine.audio_in_queue = asyncio.Queue()
        engine.ui = Mock()
        engine.ui.muted = False
        engine._action_registry = Mock()
        engine._action_registry.scheduling.return_value = None
        engine._plugin_registry = Mock()
        engine._plugin_registry.scheduling.return_value = None
        engine._clear_stall = Mock()
        engine._flush_pending_vision = AsyncMock()
        engine._marker_lesson_active = False
        engine._marker_tool_response_sent = None
        engine._marker_tool_reply_complete = None
        engine._interrupted = False
        engine._turn_done_event = None
        engine._visemes = Mock()
        engine._last_out_logged = ""
        engine._session_log = []
        engine._asst_name = "JARVIS"
        engine._conversation_id = "test"
        engine._wake_enabled = False
        engine._dashboard = None
        engine._vision_close_pending = False
        return engine

    @staticmethod
    def _packet(input_text=None, output_text=None, turn_complete=False):
        return SimpleNamespace(
            data=None, tool_call=None, session_resumption_update=None,
            server_content=SimpleNamespace(
                input_transcription=SimpleNamespace(text=input_text) if input_text else None,
                output_transcription=SimpleNamespace(text=output_text) if output_text else None,
                turn_complete=turn_complete,
            ),
        )

    async def test_explanation_question_sends_one_same_turn_visual_routing_reminder(self):
        engine = self._engine_with_session()
        task = asyncio.create_task(engine._receive_audio())
        try:
            await engine.session.packets.put(self._packet(input_text=" como"))
            await engine.session.packets.put(
                self._packet(input_text=" funciona a fotossíntese"))
            # A repeated transcript delta must not send the reminder twice.
            await engine.session.packets.put(
                self._packet(input_text=" funciona a fotossíntese"))
            await asyncio.sleep(0.05)
            self.assertEqual(engine.session.send_client_content.await_count, 1)
            kwargs = engine.session.send_client_content.await_args.kwargs
            self.assertFalse(kwargs.get("turn_complete"))
            note = kwargs["turns"]["parts"][0]["text"]
            self.assertIn("building and narrating", note)
            self.assertIn("como funciona a fotossíntese", note)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def test_casual_speech_sends_no_visual_routing_reminder(self):
        engine = self._engine_with_session()
        task = asyncio.create_task(engine._receive_audio())
        try:
            await engine.session.packets.put(self._packet(input_text=" bom"))
            await engine.session.packets.put(self._packet(input_text=" dia senhor"))
            await asyncio.sleep(0.05)
            engine.session.send_client_content.assert_not_awaited()
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def test_voice_only_explanation_turn_uses_the_lesson_director_to_generate_a_3d_board(self):
        import unittest.mock as mock

        engine = self._engine_with_session()
        shown = []
        engine._action_registry.run.side_effect = lambda name, args, ctx: (
            shown.append((name, args)) or
            ("PRESENTATION_SHOWN: 3D lesson accepted" if name == "present_visual_lesson"
             else "VISUAL_SHOWN: unexpected fallback"))
        semantic_lesson = {
            "title": "Fotossíntese", "archetype": "anatomy", "beats": [
                {"say": "A luz chega à folha.", "add": [
                    {"id": "sun", "label": "Sol", "role": "energy", "place": "center"}]},
                {"say": "A folha capta energia luminosa.", "add": [
                    {"id": "leaf", "label": "Folha", "role": "living", "place": "right", "of": "sun"}],
                 "links": [{"from": "sun", "to": "leaf", "label": "luz"}]},
                {"say": "Água e gás carbônico entram no processo.", "add": [
                    {"id": "water", "label": "Água", "role": "flow", "place": "below", "of": "leaf"},
                    {"id": "co2", "label": "CO2", "role": "small", "place": "left", "of": "leaf"}],
                 "links": [{"from": "water", "to": "leaf", "label": "absorve"},
                           {"from": "co2", "to": "leaf", "label": "entra"}]},
            ],
        }
        task = asyncio.create_task(engine._receive_audio())
        try:
            with mock.patch("core.gemini.as_json", return_value=semantic_lesson) as as_json, \
                 mock.patch("main._archive_message"):
                await engine.session.packets.put(self._packet(input_text=" como"))
                await engine.session.packets.put(self._packet(input_text=" funciona a fotossíntese"))
                await engine.session.packets.put(self._packet(
                    output_text="A fotossíntese é o processo que as plantas usam "
                                "para criar o próprio alimento."))
                await engine.session.packets.put(self._packet(turn_complete=True))
                for _ in range(300):
                    await asyncio.sleep(0.01)
                    if shown:
                        break
            self.assertEqual(len(shown), 1)
            self.assertEqual(shown[0][0], "present_visual_lesson")
            payload = shown[0][1]
            self.assertEqual(payload["title"], "Fotossíntese")
            self.assertEqual(len(payload["beats"]), 3)
            self.assertTrue(all(
                [item["type"] for item in beat["elements"]] == ["model3d"]
                for beat in payload["beats"]
            ))
            as_json.assert_called_once()
            prompt = as_json.call_args.args[0]
            self.assertIn("fotossíntese", prompt)
            self.assertIn("Never write coordinates", prompt)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


if __name__ == "__main__":
    unittest.main()
