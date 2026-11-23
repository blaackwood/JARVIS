"""
JARVIS - visual novo ao vivo.

Pele (skin) do visual novo que roda DENTRO do Jarvis de verdade: cobre a janela
principal e usa os dados e as acoes reais dela. Nada e simulado:

  - estado, nivel de voz, log, tarefas e rotinas vem do proprio Jarvis;
  - controles e configuracoes usam as paginas integradas do JARVIS Workspace;
  - o campo de comando envia pelo mesmo caminho do campo original.

O visual novo e a unica interface desktop. A janela hospedeira fornece
sinais e servicos internos; nao existe alternancia para outra interface.
"""
import math
import os
import sys
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import numpy as np
from PyQt6.QtCore import QEvent, QRectF, Qt
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

import preview as _pv
from preview import STATES, NovoVisual, mk_font

try:
    import psutil
except Exception:
    psutil = None

PALETTE = [(130, 98, 255), (60, 255, 200), (255, 176, 64), (255, 100, 140), (120, 190, 255)]
DAYN = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
REAL_STATE = {"LISTENING": "listening", "SPEAKING": "speaking",
              "THINKING": "thinking", "PROCESSING": "thinking"}



class LiveSkin(NovoVisual):
    def __init__(self, win, parent):
        super().__init__()
        self.setParent(parent)            # vira filho do widget central
        self.setMinimumSize(0, 0)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.win = win
        self.live = True
        self.auto = False
        self.name = (getattr(win, "_assistant_name", "JARVIS") or "JARVIS").upper()
        self.tasks, self.routines = [], []
        self.tasks_hint = "(clique num cartão para ver os detalhes)"
        self.log = []
        self._workspace_open = False
        self.workspace = None
        self._poll_t = 99.0
        self._cache_t = 0.0
        self._cache = {}
        self.quiz_card = None
        self._quiz_answer_widgets = []
        self._media_attached = False
        self._media_splitter_sizes = None
        self._media_original_index = 0
        self._news_html_cache = None

        # campo de comando de verdade, por cima da capsula desenhada
        self.edit = QLineEdit(self)
        self.edit.setFrame(False)
        self.edit.setFont(mk_font(11))
        self.edit.setPlaceholderText("Fale com o Jarvis ou digite um comando...")
        self.edit.setStyleSheet(
            "QLineEdit{background:transparent;color:rgba(255,255,255,235);border:none;"
            "selection-background-color:rgba(130,98,255,140);}")
        self.edit.returnPressed.connect(self._send)

        # Texto nativo e selecionavel: o usuario escolhe exatamente o trecho que copia.
        self.activity_select = QTextEdit(self)
        self.activity_select.setReadOnly(True)
        self.activity_select.setFrameShape(QFrame.Shape.NoFrame)
        self.activity_select.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.activity_select.viewport().setAutoFillBackground(False)
        self.activity_select.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.activity_select.setStyleSheet(
            "QTextEdit{background:transparent;color:rgba(255,255,255,235);border:none;"
            "font:10pt 'Segoe UI';selection-background-color:rgba(110,90,230,180);padding:2px;}"
            "QTextEdit::viewport{background:transparent;border:none;}"
            "QScrollBar:vertical{width:5px;background:transparent;}"
            "QScrollBar::handle:vertical{background:rgba(160,150,255,100);border-radius:2px;}")
        self.activity_select.hide()
        self.news_select = QTextEdit(self)
        self.news_select.setReadOnly(True)
        self.news_select.setFrameShape(QFrame.Shape.NoFrame)
        self.news_select.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.news_select.viewport().setAutoFillBackground(False)
        self.news_select.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.news_select.setStyleSheet(
            "QTextEdit{background:transparent;color:rgba(255,255,255,235);border:none;"
            "font:10pt 'Segoe UI';selection-background-color:rgba(110,90,230,180);padding:6px;}"
            "QTextEdit::viewport{background:transparent;border:none;}"
            "QScrollBar:vertical{width:5px;background:transparent;}"
            "QScrollBar::handle:vertical{background:rgba(160,150,255,100);border-radius:2px;}")
        self.news_select.hide()


        parent.installEventFilter(self)
        self.setGeometry(0, 0, parent.width(), parent.height())
        self._layout_edit()

        # log real: todas as linhas passam por este sinal
        try:
            win._log._sig.connect(self._on_log)
        except Exception:
            pass
        # conteudo real (busca, noticias, resumos) vai para o painel desta pele
        try:
            win._content_sig.connect(self._on_content)
        except Exception:
            pass

        self.show()
        self.raise_()
        self.edit.setFocus()

    # ------------------------------------------------------------- layout
    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.Resize and obj is self.parent():
            self.setGeometry(0, 0, obj.width(), obj.height())
            self._position_workspace()
        return False

    def _position_workspace(self):
        if self.workspace is None:
            return
        # Keep the HUD masthead, main tabs, command capsule and author credit
        # visible. Settings occupy only the content viewport of the live HUD.
        w, h = self.width(), self.height()
        top, bottom = 76, 96
        self.workspace.setGeometry(18, top, max(120, w - 36), max(120, h - top - bottom))

    def _goto(self, tab):
        if self._workspace_open and tab != "settings":
            self._workspace_closed()
        super()._goto(tab)

    def open_workspace(self, page="overview"):
        """Open a native settings module inside the existing live HUD."""
        try:
            from gui.holo_workspace import JARVISWorkspace
            if self.workspace is None:
                self.workspace = JARVISWorkspace(self.win, self, embedded=True)
                self.workspace.closed.connect(self._workspace_closed)
                self.win._jarvis_workspace = self.workspace
            self._workspace_open = True
            if self.tab != "settings":
                self._goto("settings")
            self._position_workspace()
            self.workspace.set_page(page)
            self.workspace.show()
            self.workspace.raise_()
            self.workspace.setFocus()
            return True
        except Exception as exc:
            self._note("Workspace indisponível: %s" % type(exc).__name__)
            return False

    def _workspace_closed(self):
        self._workspace_open = False
        if self.workspace is not None:
            self.workspace.hide()
        self.update()
        self.show()
        self.raise_()
        self.edit.setFocus()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._layout_edit()
        self._selection_widgets_layout()
        self._position_quiz_card()
        self._position_media_surface()
        self._position_workspace()

    def _selection_widgets_layout(self):
        W, H = self.width(), self.height()
        # Sobrepor somente o corpo do card ATIVIDADE (coluna direita).
        # Coordenadas acompanham exatamente _home() -> _right().
        cw = max(190, min(260, W * 0.2))
        card_x = W - 28 - cw
        card_y = 84
        card_h = H - 84 - 110
        activity_rect = (
            int(card_x + 10), int(card_y + 44),
            max(80, int(cw - 20)), max(40, int(card_h - 52)),
        )
        self.activity_select.setGeometry(*activity_rect)
        activity_text = "\n\n".join(f"{ts}\n{entry}" for ts, entry in self.log)
        if self.activity_select.toPlainText() != activity_text:
            self.activity_select.setPlainText(activity_text)
        quiz_open = self.quiz_card is not None and self.quiz_card.isVisible()
        show_activity = self.tab == "home" and self.panel is None and not quiz_open and not self._media_attached
        self.activity_select.setVisible(show_activity)
        if show_activity:
            self.activity_select.raise_()

        # Texto completo do painel atual (noticias/resumo), selecionavel sem abrir
        # outro painel nem acionar links ao clicar.
        if self.panel is not None and self._panel_last:
            c = self._panel_last
            px = 28 + cw + 20
            ptop = H - 96 - min(H * 0.44, 360.0)
            ph = min(H * 0.44, 360.0)
            body_x, body_y = int(px + 16), int(ptop + 60)
            body_w, body_h = int(W - 2 * px - 32), int(ph - 76)
            self.news_select.setGeometry(body_x, body_y, max(50, body_w), max(40, body_h))
            rich_html = c.get("_rich_html")
            if rich_html is not None:
                rich_html = str(rich_html)
                if self._news_html_cache != rich_html:
                    self.news_select.setHtml(rich_html)
                    self._news_html_cache = rich_html
                    self._panel_copy_text = self.news_select.toPlainText()
            else:
                self._news_html_cache = None
                if c.get("items"):
                    lines = []
                    for i, it in enumerate(c.get("items", []), 1):
                        lines.append(f"{i}. {it.get('h','')}\nFonte: {it.get('src','')} | {it.get('when','')}\n{it.get('url','')}")
                    news_text = "\n\n".join(lines)
                else:
                    news_text = "\n\n".join(str(v) for v in c.get("paras", []))
                    if c.get("sources"):
                        news_text += "\n\nFontes: " + ", ".join(c.get("sources", []))
                if self.news_select.toPlainText() != news_text:
                    self.news_select.setPlainText(news_text)
            show_news = self.tab == "home" and not quiz_open and not self._media_attached
            self.news_select.setVisible(show_news)
            if show_news:
                self.news_select.raise_()
        else:
            self.news_select.hide()

    def _position_media_surface(self):
        if not self._media_attached:
            return
        stack = getattr(self.win, "_hud_cam_stack", None)
        if stack is None:
            return
        W, H = self.width(), self.height()
        right_w = max(190, min(260, W * 0.2))
        x = max(220, int(W * 0.235))
        right_edge = W - 28 - right_w - 10
        width = max(280, int(right_edge - x))
        y = 104
        height = max(220, int(H - 210))
        stack.setGeometry(x, y, width, height)
        stack.raise_()

    def _sync_media_surface(self):
        stack = getattr(self.win, "_hud_cam_stack", None)
        splitter = getattr(self.win, "_center_split", None)
        if stack is None or splitter is None:
            return
        index = stack.currentIndex()
        if index in (1, 2) and not self._media_attached:
            original_index = splitter.indexOf(stack)
            if original_index < 0:
                return
            self._media_original_index = original_index
            self._media_splitter_sizes = splitter.sizes()
            stack.setParent(self)
            stack.setStyleSheet(
                "QStackedWidget{background:rgba(9,11,27,245);"
                "border:1px solid rgba(130,98,255,170);border-radius:17px;}")
            for page_index in (1, 2):
                page = stack.widget(page_index)
                if page is not None:
                    page.setStyleSheet(
                        "background:rgba(8,10,26,245);"
                        "border:1px solid rgba(90,220,205,80);border-radius:15px;")
            self._media_attached = True
            stack.show()
            self._position_media_surface()
        elif index == 0 and self._media_attached:
            stack.hide()
            stack.setParent(splitter)
            splitter.insertWidget(min(self._media_original_index, splitter.count()), stack)
            self._media_attached = False
            stack.show()
            if self._media_splitter_sizes and len(self._media_splitter_sizes) == splitter.count():
                splitter.setSizes(self._media_splitter_sizes)
            self._media_splitter_sizes = None

    def _ensure_quiz_card(self):
        if self.quiz_card is not None:
            return
        card = QFrame(self)
        card.setObjectName("LiveQuizCard")
        card.setStyleSheet("""
            QFrame#LiveQuizCard {
                background: rgba(13, 11, 30, 248);
                border: 1px solid rgba(137, 111, 255, 210);
                border-radius: 20px;
            }
            QLabel { color: #f1efff; background: transparent; }
            QPushButton {
                color: #f1efff; background: rgba(255,255,255,13);
                border: 1px solid rgba(170,160,255,65); border-radius: 10px;
                padding: 10px 14px; text-align: left; font: 10pt 'Segoe UI';
            }
            QPushButton:hover { background: rgba(130,98,255,65); border-color: #9e8cff; }
            QPushButton:disabled { color: rgba(235,232,255,130); background: rgba(255,255,255,8); }
            QPushButton#QuizPrimary {
                color: white; background: #7657e8; border: 1px solid #a28cff;
                padding: 9px 18px; font-weight: 700;
            }
            QPushButton#QuizClose {
                color: #d8d1ff; background: rgba(255,255,255,12);
                border: 1px solid rgba(255,255,255,25); padding: 5px 10px;
            }
            QLineEdit {
                color: white; background: rgba(255,255,255,12);
                border: 1px solid rgba(170,160,255,90); border-radius: 9px;
                padding: 10px; selection-background-color: rgba(130,98,255,170);
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)
        head = QHBoxLayout()
        self.quiz_title = QLabel("JARVIS · QUIZ")
        self.quiz_title.setStyleSheet("color:#b8aaff;font:700 9pt 'Segoe UI';letter-spacing:1.5px;")
        head.addWidget(self.quiz_title, 1)
        self.quiz_count = QLabel("")
        self.quiz_count.setStyleSheet("color:#9c91d8;font:9pt 'Consolas';")
        head.addWidget(self.quiz_count)
        close = QPushButton("FECHAR")
        close.setObjectName("QuizClose")
        close.clicked.connect(self._close_live_quiz)
        head.addWidget(close)
        layout.addLayout(head)
        self.quiz_question = QLabel("")
        self.quiz_question.setWordWrap(True)
        self.quiz_question.setStyleSheet("color:#fff;font:600 15pt 'Segoe UI';padding:5px 0;")
        layout.addWidget(self.quiz_question)
        self.quiz_answers_host = QWidget(card)
        self.quiz_answers_layout = QVBoxLayout(self.quiz_answers_host)
        self.quiz_answers_layout.setContentsMargins(0, 0, 0, 0)
        self.quiz_answers_layout.setSpacing(8)
        layout.addWidget(self.quiz_answers_host, 1)
        self.quiz_note = QLabel("")
        self.quiz_note.setWordWrap(True)
        self.quiz_note.hide()
        layout.addWidget(self.quiz_note)
        foot = QHBoxLayout()
        foot.addStretch(1)
        self.quiz_next = QPushButton("PRÓXIMA  →")
        self.quiz_next.setObjectName("QuizPrimary")
        self.quiz_next.clicked.connect(self._next_live_quiz)
        self.quiz_next.hide()
        foot.addWidget(self.quiz_next)
        layout.addLayout(foot)
        self.quiz_card = card
        self._position_quiz_card()

    def _position_quiz_card(self):
        if self.quiz_card is None:
            return
        W, H = self.width(), self.height()
        w = min(650, max(360, W - 64))
        h = min(460, max(300, H - 112))
        self.quiz_card.setGeometry((W - w) // 2, max(54, (H - h) // 2), w, h)

    def show_quiz(self, topic, questions, grader=None):
        if not questions:
            return False
        self.win._quiz = {
            "topic": topic or "", "questions": list(questions), "grader": grader,
            "i": 0, "results": [], "answered": False,
        }
        self._ensure_quiz_card()
        self.quiz_title.setText((topic or "JARVIS · QUIZ").upper()[:48])
        self._render_live_quiz()
        self.quiz_card.show()
        self.quiz_card.raise_()
        return True

    def _clear_live_quiz_answers(self):
        while self.quiz_answers_layout.count():
            item = self.quiz_answers_layout.takeAt(0)
            child = item.widget()
            if child is not None:
                child.deleteLater()
        self._quiz_answer_widgets = []

    def _render_live_quiz(self):
        quiz = self.win._quiz
        if quiz is None:
            self.quiz_card.hide()
            return
        question = quiz["questions"][quiz["i"]]
        self.quiz_count.setText(f"{quiz['i'] + 1:02d} / {len(quiz['questions']):02d}")
        self.quiz_question.setText(str(question.get("question", "")))
        self.quiz_note.clear()
        self.quiz_note.hide()
        self.quiz_next.hide()
        quiz["answered"] = False
        self._clear_live_quiz_answers()
        options = question.get("options") or []
        if options:
            for option in options:
                value = str(option)
                button = QPushButton(value, self.quiz_answers_host)
                button.setMinimumHeight(42)
                button.clicked.connect(lambda checked=False, answer=value: self._submit_live_quiz(answer))
                self.quiz_answers_layout.addWidget(button)
                self._quiz_answer_widgets.append(button)
        else:
            row = QWidget(self.quiz_answers_host)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            self.quiz_input = QLineEdit(row)
            self.quiz_input.setPlaceholderText("Digite sua resposta...")
            send = QPushButton("RESPONDER", row)
            send.setObjectName("QuizPrimary")
            send.clicked.connect(lambda: self._submit_live_quiz(self.quiz_input.text()))
            self.quiz_input.returnPressed.connect(lambda: self._submit_live_quiz(self.quiz_input.text()))
            row_layout.addWidget(self.quiz_input, 1)
            row_layout.addWidget(send)
            self.quiz_answers_layout.addWidget(row)
            self._quiz_answer_widgets.extend((self.quiz_input, send))
            self.quiz_input.setFocus()

    def _submit_live_quiz(self, answer):
        quiz = self.win._quiz
        if quiz is None or quiz.get("answered"):
            return
        self.win._quiz_submit(str(answer or ""))
        quiz = self.win._quiz
        if quiz is None or not quiz.get("results"):
            return
        result = quiz["results"][-1]
        verdict = result.get("correct")
        if verdict is True:
            mark, colour = "✓  Resposta correta", "#58edc4"
        elif verdict is False:
            mark, colour = "✕  Resposta esperada: " + str(result.get("answer", "")), "#ff829d"
        else:
            mark, colour = "…  Resposta registrada para revisão", "#ffc36e"
        note = quiz["questions"][quiz["i"]].get("note") or ""
        self.quiz_note.setText(mark + (("\n" + str(note)) if note else ""))
        self.quiz_note.setStyleSheet(f"color:{colour};background:transparent;font:10pt 'Segoe UI';")
        self.quiz_note.show()
        for widget in self._quiz_answer_widgets:
            widget.setEnabled(False)
        last = quiz["i"] >= len(quiz["questions"]) - 1
        self.quiz_next.setText("FINALIZAR  →" if last else "PRÓXIMA  →")
        self.quiz_next.show()

    def _next_live_quiz(self):
        quiz = self.win._quiz
        if quiz is None:
            self.quiz_card.hide()
            return
        if quiz["i"] >= len(quiz["questions"]) - 1:
            self.quiz_card.hide()
            self.win._quiz_finish()
        else:
            self.win._quiz_next()
            self._render_live_quiz()

    def _close_live_quiz(self):
        self.quiz_card.hide()
        self.win._hide_quiz()

    def _layout_edit(self):
        W, H = self.width(), self.height()
        w, h = min(760.0, W * 0.56), 52.0
        x, y = (W - w) / 2.0, H - 84.0
        self.edit.setGeometry(int(x + 62), int(y + 10), int(w - 124), int(h - 20))

    def _capsule(self, p, W, H):
        super()._capsule(p, W, H)
        w, h = min(760.0, W * 0.56), 52.0
        x, y = (W - w) / 2.0, H - 84.0
        self._hit(QRectF(x + 12, y + 8, 36, 36), self.do_mute, ("cap", "mic"))
        self._hit(QRectF(x + w - 48, y + 8, 36, 36), self._send, ("cap", "send"))

    # -------------------------------------------------------------- input
    def keyPressEvent(self, e):
        t = e.text()
        if t and t.isprintable() and not (e.modifiers() & (Qt.KeyboardModifier.ControlModifier
                                                            | Qt.KeyboardModifier.AltModifier)):
            self.edit.setFocus()
            self.edit.insert(t)
        else:
            super(NovoVisual, self).keyPressEvent(e)

    def open_news(self):
        """Run a real current-news request through JARVIS, never demo headlines."""
        self.edit.setText(
            "Busque e apresente as principais notícias atuais do Brasil e do mundo."
        )
        self._send()

    def open_search(self):
        """Prepare the live command field for a user-defined web search."""
        self._focus_prompt("Pesquise na web: ")

    def _send(self):
        txt = self.edit.text().strip()
        if not txt:
            return
        try:
            self.win._input.setText(txt)     # mesmo caminho do campo original
            self.edit.clear()
            self.win._send()
        except Exception as ex:
            self._note("Erro ao enviar: %s" % ex)

    def _focus_prompt(self, prefix=""):
        self.edit.setText(prefix)
        self.edit.setFocus()
        self.edit.end(False)

    # ---------------------------------------------------------- real data
    def _note(self, txt):
        self.log.append((time.strftime("%H:%M:%S"), str(txt)))
        self.log = self.log[-50:]

    def copy_activity_log(self):
        text = "\n".join(f"{ts}  {entry}" for ts, entry in self.log)
        QApplication.clipboard().setText(text)
        return text

    def _show_activity_detail(self, index):
        try:
            ts, text = self.log[index]
        except (IndexError, TypeError):
            return
        full = f"{ts}\n\n{text}"
        self.open_panel({
            "kind": "ATIVIDADE", "title": text[:70], "paras": [ts, text],
            "sources": [], "_copy_text": full,
        })

    def _on_log(self, text):
        t = str(text or "").strip()
        if not t:
            return
        low = t.lower()
        if low.startswith("you:"):
            t = "Você:" + t[4:]
        elif low.startswith("sys:"):
            t = t[4:].strip()
        self._note(t)

    def _on_content(self, title, text):
        try:
            self.win._content_panel.hide()
        except Exception:
            pass
        self._text_panel(title, text)

    def _text_panel(self, title, text):
        full_text = str(text or "")
        paras = [ln.strip() for ln in full_text.splitlines() if ln.strip()]
        kind = (str(title or "INFO").upper())[:22]
        head = paras[0][:70] if paras else ""
        self.open_panel({
            "kind": kind, "title": head, "paras": paras, "sources": [],
            "_copy_text": full_text,
        })

    def show_rich_panel(self, title, html):
        """Display rich review/job content in the new selectable content surface."""
        rich = str(html or "")
        self.panel = {
            "kind": (str(title or "INFO").upper())[:22],
            "title": str(title or "")[:70],
            "ts": time.strftime("%H:%M:%S"),
            "paras": [], "sources": [], "_rich_html": rich,
        }
        self._panel_last = self.panel
        self._panel_copy_text = None
        self._news_html_cache = None
        self.panel_scroll = 0.0
        self._goto("home")
        try:
            self.win._content_panel.hide()
        except Exception:
            pass
        self._selection_widgets_layout()
        self.news_select.show()
        self.news_select.raise_()
        self._panel_copy_text = self.news_select.toPlainText()

    def _via_real(self, fn, arg, kind):
        """Abre o detalhe pelo codigo real e mostra o texto no painel desta pele."""
        try:
            fn(arg)
            txt = self.win._content_display.toPlainText()
            self.win._content_panel.hide()
            self._text_panel(kind, txt)
        except Exception as ex:
            self._note("Detalhe indisponível: %s" % ex)

    def _poll_real(self):
        # tarefas
        try:
            from core.tasks import desktop as td
            eng = td.engine()
            raw = eng.list(50) if eng else []
        except Exception:
            raw = []
        tasks = []
        for t in raw:
            stt = str(t.get("status") or "")
            if stt in ("queued", "scheduled", "waiting_quota"):
                col = 0
            elif stt in ("running", "pausing", "paused"):
                col = 1
            else:
                col = 2
            used = (t.get("used") or {}).get("seconds") or 0
            mins = (t.get("budget") or {}).get("minutes") or 0
            pg = 1.0 if col == 2 else (min(1.0, (used / 60.0) / mins) if mins else 0.0)
            tasks.append({"id": t.get("id"), "t": str(t.get("title") or "Tarefa"),
                          "tag": "Falhou" if stt == "failed" else "Tarefa",
                          "due": stt.replace("_", " ") + (" · %.1f/%s min" % (used / 60.0, mins) if mins else ""),
                          "pr": 2 if stt == "failed" else (1 if col == 1 else 0), "st": col, "pg": pg})
        done = [t for t in tasks if t["st"] == 2][:8]
        self.tasks = [t for t in tasks if t["st"] < 2] + done
        # rotinas
        routines = []
        try:
            from core.routines import desktop as rd
            eng = rd.engine()
            items = eng.list() if eng else []
        except Exception:
            eng, items = None, []
        for i, r in enumerate(items):
            trig = r.get("trigger") or {}
            nt = r.get("next_ts")
            h = m = None
            chip = "Evento"
            days = list(range(7))
            ttype = trig.get("type")
            if ttype == "time":
                rule = trig.get("rule") or {}
                rt = rule.get("type")
                d = rule.get("days")
                if isinstance(d, (list, tuple)) and d:
                    try:
                        days = sorted({(int(x) - 1) % 7 for x in d})   # regras usam 1=seg ... 7=dom
                    except Exception:
                        days = list(range(7))
                if rt in ("weekly", "monthly") and ":" in str(rule.get("time") or ""):
                    try:
                        h, m = int(str(rule["time"]).split(":")[0]), int(str(rule["time"]).split(":")[1][:2])
                    except Exception:
                        h = m = None
                if h is not None:
                    chip = _pv.sched_label(days) if rt == "weekly" else "Mensal"
                elif rt == "interval":
                    chip = "A cada %s min" % rule.get("minutes", "?")
                if h is None and rt != "interval" and nt:
                    lt = time.localtime(nt)
                    h, m = lt.tm_hour, lt.tm_min
                    chip = "Uma vez"
            elif ttype == "startup":
                chip = "Ao abrir"
            elif ttype == "idle":
                chip = "Ocioso %s min" % trig.get("minutes", "?")
            try:
                desc = eng.describe(r)
            except Exception:
                desc = ""
            lr = r.get("last_run")
            last = ("ok · " + time.strftime("%d/%m %H:%M", time.localtime(lr))) if lr else "nunca rodou"
            if r.get("enabled") and nt:
                lt = time.localtime(nt)
                nxt = "%s %02d:%02d" % (DAYN[lt.tm_wday].lower(), lt.tm_hour, lt.tm_min)
            else:
                nxt = "-"
            routines.append({"id": r.get("id"), "n": str(r.get("name") or "Rotina"), "d": desc[:90],
                             "h": h, "m": m, "days": days, "on": bool(r.get("enabled")), "last": last,
                             "next": nxt, "chip": chip, "_nt": float(nt or 0),
                             "hm": ("%02d:%02d" % (h, m)) if h is not None else "--:--",
                             "c": PALETTE[i % len(PALETTE)]})
        routines.sort(key=lambda r: (not r["on"], r["_nt"] == 0, r["_nt"]))
        self.routines = routines

    def _advance(self, i):                       # clique no cartao de tarefa
        t = self.tasks[i]
        if t.get("id"):
            self._via_real(self.win._open_task, t["id"], "TAREFA")

    def _open_routine_i(self, i):                # clique no cartao de rotina
        r = self.routines[i]
        if r.get("id"):
            self._via_real(self.win._open_routine, r["id"], "ROTINA")

    def _toggle(self, i):                        # interruptor de rotina
        r = self.routines[i]
        try:
            self.win._toggle_routine(r["id"], not r["on"])
        except Exception as ex:
            self._note("Rotina não alterada: %s" % ex)
        self._poll_t = 99.0

    def _new_task(self):
        self._goto("home")
        self._focus_prompt("Crie uma tarefa em segundo plano: ")

    # ------------------------------------------------------------ actions
    def _safe(self, fn):
        def run():
            try:
                fn()
            except Exception as ex:
                self._note("Falhou: %s" % ex)
            self._cache_t = 0.0
        return run

    def do_mute(self):
        self._safe(self.win._toggle_mute)()

    def do_stop(self):
        self._safe(self.win._do_interrupt)()

    def do_fs(self):
        self._safe(self.win._toggle_fullscreen)()

    def do_sleep(self):
        st = self._real_flags()
        if st["wake_ready"] and st["wake"]:
            self._safe(self.win._tap_wake_manual)()
        else:
            self._note("Ligue a palavra de ativação para usar o modo de espera.")

    # ----------------------------------------------------- real states
    def _real_flags(self):
        now = time.time()
        if now - self._cache_t < 0.5 and self._cache:
            return self._cache
        w = self.win
        c = {"brief": False, "ptt": False, "auto": False, "chord": "",
             "wake": False, "wake_ready": False, "awake": True}
        try:
            from memory.config_manager import get_brief_enabled, get_push_to_talk_enabled
            c["brief"] = bool(get_brief_enabled())
            c["ptt"] = bool(get_push_to_talk_enabled())
        except Exception:
            pass
        try:
            from core.hotkey import chord_label
            c["chord"] = str(chord_label())
        except Exception:
            pass
        try:
            s = w._wake_state()
            c["wake"], c["wake_ready"], c["awake"] = s["enabled"], s["ready"], s["awake"]
        except Exception:
            pass
        try:
            c["auto"] = bool(w._check_autostart())
        except Exception:
            pass
        self._cache, self._cache_t = c, now
        return c

    def _ctl_items(self):
        f = self._real_flags()
        S = self._safe
        w = self.win
        wake_ok = f["wake_ready"]
        return [
            {"k": "mute", "t": "Microfone", "d": "Desligado, o Jarvis para de escutar", "kind": "sw",
             "on": not self.muted, "c": (60, 255, 200), "fn": self.do_mute},
            {"k": "stop", "t": "Interromper", "d": "Para a fala do assistente agora", "kind": "act",
             "lbl": "PARAR", "c": (255, 130, 150), "fn": self.do_stop},
            {"k": "fs", "t": "Tela cheia", "d": "Alterna o modo tela cheia (F11)", "kind": "act",
             "lbl": "SAIR" if self.isFullScreen() or w.isFullScreen() else "ENTRAR", "c": (176, 156, 255),
             "fn": self.do_fs},
            {"k": "sleep", "t": "Dormir agora" if f["awake"] else "Acordar agora",
             "d": "Espera até ouvir a palavra de ativação" if wake_ok and f["wake"]
             else "Precisa da palavra de ativação ligada", "kind": "act",
             "lbl": ("DORMIR" if f["awake"] else "ACORDAR") if wake_ok and f["wake"] else "INDISPONÍVEL",
             "c": (120, 190, 255), "fn": self.do_sleep},
            {"k": "brief", "t": "Resumo da manhã", "d": "Fala notícias e agenda ao acordar", "kind": "sw",
             "on": f["brief"], "c": (255, 176, 64), "fn": S(w._toggle_brief)},
            {"k": "wake", "t": "Palavra de ativação",
             "d": "Responde quando ouvir o nome dele" if wake_ok else "Baixa o modelo na primeira vez",
             "kind": "sw" if wake_ok else "act", "lbl": "BAIXAR", "on": f["wake"], "c": (60, 255, 200),
             "fn": S(w._toggle_wake_word)},
            {"k": "ptt", "t": "Apertar para falar",
             "d": ("Segure %s para falar" % f["chord"]) if f["ptt"] and f["chord"] else "Só escuta com a tecla pressionada",
             "kind": "sw", "on": f["ptt"], "c": (176, 156, 255), "fn": S(w._toggle_ptt)},
            {"k": "style", "t": "Visual da esfera", "d": "Alterna holograma e núcleo neural", "kind": "act",
             "lbl": "HOLOGRAMA" if self.orb_style == "holo" else "NEURAL", "c": (255, 176, 64),
             "fn": self.do_style},
            {"k": "agent", "t": "Agent UI", "d": "Abre o aplicativo Jarvis Agent", "kind": "act",
             "lbl": "ABRIR", "c": (60, 255, 200), "fn": S(w._open_agent_ui)},
        ]

    def _set_items(self):
        f = self._real_flags()
        S = self._safe
        w = self.win
        op = lambda k, t, d, fn, c: {"k": k, "t": t, "d": d, "kind": "act", "lbl": "ABRIR", "c": c, "fn": S(fn)}
        return [
            op("remote", "Acesso remoto", "Pareamento seguro com outro dispositivo", lambda: self.open_workspace("remote"), (130, 98, 255)),
            {"k": "shortcut", "t": "Atalho na área de trabalho", "d": "Cria um ícone para abrir o JARVIS", "kind": "act",
             "lbl": "CRIAR", "c": (120, 190, 255), "fn": S(w._create_desktop_shortcut)},
            {"k": "autostart", "t": "Iniciar com o Windows", "d": "Abre junto com o computador",
             "kind": "sw", "on": f["auto"], "c": (60, 255, 200), "fn": S(w._toggle_autostart)},
            op("customize", "Identidade do JARVIS", "Nome, voz, aparência e motor", lambda: self.open_workspace("identity"), (255, 176, 64)),
            op("audio", "Voz e áudio", "Microfone, saída e níveis", lambda: self.open_workspace("audio"), (60, 255, 200)),
            op("memory", "Memória", "Inspecione o que o JARVIS guardou", lambda: self.open_workspace("memory"), (176, 156, 255)),
            op("plugins", "Extensões", "Gerencie as capacidades instaladas", lambda: self.open_workspace("plugins"), (255, 130, 150)),
            op("pluginset", "Configuração de extensões", "Ajuste os módulos conectados", lambda: self.open_workspace("plugin_settings"), (120, 190, 255)),
            op("engine", "Motor e provedores", "Rotas de escuta, raciocínio e fala", lambda: self.open_workspace("engine"), (255, 176, 64)),
        ]

    def _settings_view(self, p, W, H):
        # A module is already rendered in the live HUD's content viewport.
        # Do not draw the settings launcher cards underneath it.
        if self._workspace_open:
            return
        self._controls_view(
            p, W, H, self._set_items(),
            "CONFIGURAÇÕES DO JARVIS  ·  CONTROLE E PERSONALIZAÇÃO"
        )

    # --------------------------------------------------------------- tick
    def _set(self, s):                           # sem log sintetico
        self.state = s

    def _tick(self):
        if self._workspace_open and self.workspace is not None:
            if not self.workspace.isVisible():
                self.workspace.show()
                self.workspace.raise_()
        now = time.perf_counter()
        dt = min(0.05, now - self._last)
        self._last = now
        self.t += dt
        w = self.win
        self._sync_media_surface()
        # The new skin is the sole desktop visual. Never reveal the retired
        # host layout when an underlying feature changes visibility.
        if not self.isVisible():
            self.show()
            self.raise_()
        self._poll_t += dt
        if self._poll_t > 2.0:
            self._poll_t = 0.0
            try:
                self._poll_real()
            except Exception:
                pass

        self.muted = bool(getattr(w, "_muted", False))
        try:
            rs = str(w.hud.state or "").upper()
            real = float(getattr(w.hud, "_amp_disp", 0.0) or 0.0)
        except Exception:
            rs, real = "", 0.0
        s = "idle" if self.muted else REAL_STATE.get(rs, "idle")
        self.state = s
        t = self.t
        if s == "speaking":
            tgt = max(0.10 + 0.05 * math.sin(t * 5.0), min(0.85, real * 1.25))
        elif s == "listening":
            tgt = 0.06 + min(0.6, real * 1.6)
        elif s == "thinking":
            tgt = 0.10 + 0.05 * math.sin(t * 4)
        else:
            tgt = 0.03 + 0.02 * math.sin(t)
        self.amp += (tgt - self.amp) * (1 - math.exp(-dt / 0.07))
        i = np.arange(96)
        base = np.abs(np.sin(i * 0.41 + t * 3.1) * np.sin(i * 0.13 - t * 1.9))
        self.spec += (self.amp * (0.25 + 0.9 * base) + 0.02 - self.spec) * (1 - math.exp(-dt / 0.06))
        pc, ac = STATES[s][1], STATES[s][2]
        k = 1 - math.exp(-dt / 0.25)
        for j in range(3):
            self.col[j] += (pc[j] - self.col[j]) * k
            self.acc[j] += (ac[j] - self.acc[j]) * k
        self.think_v += ((1.0 if s == "thinking" else 0.0) - self.think_v) * (1 - math.exp(-dt / 0.4))
        self._stat_t += dt
        if self._stat_t > 1.0:
            self._stat_t = 0.0
            if psutil:
                try:
                    self.cpu = psutil.cpu_percent()
                    self.mem = psutil.virtual_memory().percent
                    self.disk = psutil.disk_usage(os.path.abspath(os.sep)).percent
                except Exception:
                    pass
        self.panel_p += ((1.0 if self.panel is not None else 0.0) - self.panel_p) * (1 - math.exp(-dt / 0.12))
        self.update()
        self._selection_widgets_layout()


def attach(win):
    """Install the single supported JARVIS desktop visual."""
    sk = LiveSkin(win, win.centralWidget())
    win._holo_skin = sk
    return sk


