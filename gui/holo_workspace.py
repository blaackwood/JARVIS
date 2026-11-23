"""JARVIS System Workspace — native shell for the new assistant UI.

The workspace owns navigation and presentation. Existing provider/audio/memory
services are embedded as functional modules; they are never opened as legacy
floating windows over the new visual.
"""
from __future__ import annotations

import threading

from PyQt6.QtCore import Qt, pyqtSignal, QEvent
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QRadialGradient
from PyQt6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QScrollArea, QSizePolicy, QGridLayout, QLineEdit,
    QComboBox, QTextEdit, QPlainTextEdit, QProgressBar, QSlider,
    QCheckBox, QInputDialog, QMessageBox, QApplication,
)

BG = "#070a16"
SURFACE = "#0d1326"
SURFACE_2 = "#111b33"
LINE = "rgba(126,112,255,105)"
VIOLET = "#9b8cff"
CYAN = "#55e7de"
TEXT = "#edf1ff"
MUTED = "#8998bd"
DANGER = "#ff829d"


class JARVISWorkspace(QWidget):
    """Full-surface control center, attached to MainWindow.centralWidget()."""

    closed = pyqtSignal()
    audio_test_finished = pyqtSignal(str, bool, str)
    plugin_test_finished = pyqtSignal(str, bool, str)
    setup_validation_finished = pyqtSignal(object)

    NAV = (
        ("overview", "OVERVIEW"),
        ("setup", "SETUP"),
        ("engine", "ENGINE"),
        ("audio", "AUDIO"),
        ("memory", "MEMORY"),
        ("plugins", "EXTENSIONS"),
        ("identity", "IDENTITY"),
        ("plugin_settings", "PLUGIN CFG"),
        ("remote", "REMOTE"),
    )

    def __init__(self, win, parent=None, embedded=False):
        super().__init__(parent)
        self.win = win
        from memory.config_manager import get_app_language
        self._language = get_app_language()
        self.embedded = bool(embedded)
        self._pages = {}
        self._panels = {}
        self._nav = {}
        self._audio_test_widgets = {}
        self._plugin_status_labels = {}
        self._plugin_setting_widgets = {}
        self.audio_test_finished.connect(self._on_audio_test_finished)
        self.plugin_test_finished.connect(self._on_plugin_test_finished)
        self.setup_validation_finished.connect(self._on_setup_validation_finished)
        self.setObjectName("JarvisSystemWorkspace")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFont(QFont("Segoe UI", 9))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(f"""
            QWidget#JarvisSystemWorkspace {{
                background: transparent;
                color: {TEXT};
                border: 0;
                border-radius: 18px;
            }}
            QLabel {{ color: {TEXT}; background: transparent; }}
            QFrame#WorkspaceNav {{
                background: rgba(8, 11, 25, 178);
                border: 1px solid rgba(126, 112, 255, 72);
                border-radius: 15px;
            }}
            QStackedWidget {{ background: transparent; border: 0; }}
            QScrollArea {{ background: transparent; border: 0; }}
            QScrollBar:vertical {{ background: rgba(24,32,58,105); width: 7px; margin: 4px; border-radius: 3px; }}
            QScrollBar::handle:vertical {{ background: rgba(130,98,255,145); min-height: 26px; border-radius: 3px; }}
            QScrollBar::handle:vertical:hover {{ background: rgba(85,231,222,175); }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0) if self.embedded else root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(0 if self.embedded else 14)

        top_container = QWidget(self)
        top = QHBoxLayout(top_container)
        top.setContentsMargins(0, 0, 0, 0)
        brand = QHBoxLayout()
        mark = QLabel("◈")
        mark.setStyleSheet(f"color:{CYAN};font-size:25px;font-weight:700;")
        brand.addWidget(mark)
        names = QVBoxLayout()
        names.setSpacing(0)
        title = QLabel("JARVIS  /  SYSTEMS")
        title.setStyleSheet(f"color:{TEXT};font-size:15px;font-weight:800;letter-spacing:3px;")
        sub = QLabel("NEURAL INTERFACE  ·  CONTROL PLANE")
        sub.setStyleSheet(f"color:{MUTED};font-size:8px;letter-spacing:2px;")
        names.addWidget(title)
        names.addWidget(sub)
        brand.addLayout(names)
        top.addLayout(brand)
        top.addStretch(1)
        self.status = QLabel("●  SYSTEM ONLINE")
        self.status.setStyleSheet(f"color:{CYAN};font-size:9px;font-weight:700;letter-spacing:1px;")
        top.addWidget(self.status)
        close = QPushButton("×")
        close.setFixedSize(38, 34)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet(f"""
            QPushButton {{ color:{MUTED}; background:{SURFACE_2}; border:1px solid {LINE};
                           border-radius:10px; font-size:20px; }}
            QPushButton:hover {{ color:white; border-color:{CYAN}; background:#1b2543; }}
        """)
        close.clicked.connect(self._close)
        top.addWidget(close)
        root.addWidget(top_container)

        nav_frame = QFrame()
        nav_frame.setObjectName("WorkspaceNav")
        nav = QHBoxLayout(nav_frame)
        nav.setContentsMargins(7, 6, 7, 6)
        nav.setSpacing(4)
        for key, label in self.NAV:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setMinimumHeight(35)
            b.setMinimumWidth(0)
            b.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            b.setToolTip(label.title())
            b.clicked.connect(lambda _=False, k=key: self.set_page(k))
            self._nav[key] = b
            nav.addWidget(b)
        root.addWidget(nav_frame)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        signature_row = QHBoxLayout()
        signature_row.addStretch(1)
        signature = QLabel("By blaackwood")
        signature.setStyleSheet("color:rgba(177,190,224,175);font-size:8px;font-weight:600;letter-spacing:1px;padding:2px 5px;")
        signature_row.addWidget(signature)
        root.addLayout(signature_row)
        if self.embedded:
            # Main HUD keeps its own brand, tabs, command capsule and signature.
            top_container.hide()
            nav_frame.hide()
            signature.hide()
        self._build_overview()
        self.set_page("overview")
        self._apply_translations()
        if parent is not None:
            parent.installEventFilter(self)
            self._fit_to_parent(parent)

    def paintEvent(self, event):
        """Paint a standalone canvas only; embedded pages reveal the live HUD below."""
        if self.embedded:
            return
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(0, 0, w, h, QColor(6, 7, 15))

        glow = QRadialGradient(w * 0.50, h * 0.38, max(w, h) * 0.82)
        glow.setColorAt(0.0, QColor(28, 22, 61, 190))
        glow.setColorAt(0.42, QColor(15, 15, 35, 130))
        glow.setColorAt(1.0, QColor(6, 7, 15, 0))
        p.fillRect(0, 0, w, h, glow)

        # Fine neural grid: almost invisible at rest, but gives the canvas depth.
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(164, 157, 255, 15))
        for x in range(18, w - 12, 32):
            for y in range(18, h - 12, 32):
                p.drawEllipse(x, y, 2, 2)

        # Large orbital traces stay behind the controls, echoing the neural core.
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(130, 98, 255, 17), 1))
        p.drawEllipse(int(w * 0.55), int(-h * 0.53), int(w * 0.78), int(h * 1.30))
        p.setPen(QPen(QColor(60, 255, 200, 10), 1))
        p.drawEllipse(int(w * 0.61), int(-h * 0.44), int(w * 0.69), int(h * 1.18))
        p.setPen(QPen(QColor(130, 98, 255, 11), 1))
        p.drawEllipse(int(-w * 0.48), int(h * 0.61), int(w * 0.78), int(h * 0.90))

        # HUD frame and short signature strokes.
        p.setPen(QPen(QColor(139, 124, 255, 108), 1))
        p.drawRoundedRect(0, 0, w - 1, h - 1, 17, 17)
        p.setPen(QPen(QColor(60, 255, 200, 160), 2))
        p.drawLine(20, 20, 74, 20)
        p.drawLine(20, 20, 20, 54)
        p.setPen(QPen(QColor(130, 98, 255, 105), 1))
        p.drawLine(w - 78, h - 20, w - 22, h - 20)
        p.end()

    def _fit_to_parent(self, parent):
        rect = parent.rect()
        if self.embedded:
            rect = rect.adjusted(18, 76, -18, -96)
        self.setGeometry(rect)

    def eventFilter(self, obj, event):
        if obj is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self._fit_to_parent(obj)
        return False

    def _close(self):
        self.hide()
        self.closed.emit()

    def set_page(self, key: str):
        if key not in self._pages:
            self._build_panel_page(key)
        page = self._pages.get(key)
        if page is None:
            key = "overview"
            page = self._pages[key]
        self.stack.setCurrentWidget(page)
        self._apply_translations()
        for name, button in self._nav.items():
            on = name == key
            button.setChecked(on)
            button.setStyleSheet(f"""
                QPushButton {{
                    color: {'#ffffff' if on else 'rgba(188,198,226,190)'};
                    background: {'qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(130,98,255,82),stop:1 rgba(60,255,200,20))' if on else 'transparent'};
                    border: {'1px solid rgba(155,139,255,155)' if on else '1px solid transparent'};
                    border-radius: 10px;
                    padding: 0 5px;
                    font-size: 7px;
                    font-weight: 800;
                    letter-spacing: .45px;
                }}
                QPushButton:hover {{
                    color: white;
                    background: rgba(110,95,220,32);
                    border: 1px solid rgba(85,231,222,95);
                }}
            """)
        status_source = "●  " + dict(self.NAV).get(key, "SYSTEM ONLINE")
        self.status.setProperty("_jarvis_i18n_source", status_source)
        status_text = self._tr(status_source)
        self.status.setText(status_text)
        self.status.setProperty("_jarvis_i18n_last_text", status_text)
        self.status.setStyleSheet(f"color:{CYAN};font-size:9px;font-weight:700;letter-spacing:1px;")

    def set_language(self, language: str) -> None:
        """Refresh every static label in the current live settings workspace."""
        from memory.config_manager import normalize_app_language
        self._language = normalize_app_language(language)
        self._apply_translations()

    def _tr(self, text):
        from core.i18n import tr
        return tr(text, self._language)

    def _set_i18n_text(self, widget, source_text) -> None:
        source = str(source_text or "")
        translated = self._tr(source)
        widget.setProperty("_jarvis_i18n_source", source)
        widget.setText(translated)
        widget.setProperty("_jarvis_i18n_last_text", translated)

    def _apply_translations(self) -> None:
        """Translate static widgets while leaving user-entered content untouched."""
        from core.i18n import tr
        for widget in [self, *self.findChildren(QWidget)]:
            if isinstance(widget, (QLabel, QPushButton, QCheckBox)):
                source = widget.property("_jarvis_i18n_source")
                last = widget.property("_jarvis_i18n_last_text")
                if source is None or (last is not None and widget.text() != last):
                    source = widget.text()
                    widget.setProperty("_jarvis_i18n_source", source)
                translated = tr(source, self._language)
                if widget.text() != translated:
                    widget.setText(translated)
                widget.setProperty("_jarvis_i18n_last_text", translated)
                tip = widget.property("_jarvis_i18n_tooltip")
                if tip is None:
                    tip = widget.toolTip()
                    widget.setProperty("_jarvis_i18n_tooltip", tip)
                if tip:
                    widget.setToolTip(tr(tip, self._language))
            elif isinstance(widget, QLineEdit):
                source = widget.property("_jarvis_i18n_placeholder")
                last = widget.property("_jarvis_i18n_last_placeholder")
                if source is None or (last is not None and widget.placeholderText() != last):
                    source = widget.placeholderText()
                    widget.setProperty("_jarvis_i18n_placeholder", source)
                if source:
                    translated = tr(source, self._language)
                    widget.setPlaceholderText(translated)
                    widget.setProperty("_jarvis_i18n_last_placeholder", translated)
            elif isinstance(widget, QComboBox):
                originals = widget.property("_jarvis_i18n_items")
                if not isinstance(originals, list) or len(originals) != widget.count():
                    originals = [widget.itemText(i) for i in range(widget.count())]
                    widget.setProperty("_jarvis_i18n_items", originals)
                current_data = widget.currentData()
                current_index = widget.currentIndex()
                for index, original in enumerate(originals):
                    widget.setItemText(index, tr(original, self._language))
                if current_data is not None:
                    restored = widget.findData(current_data)
                    if restored >= 0:
                        widget.setCurrentIndex(restored)
                elif current_index >= 0:
                    widget.setCurrentIndex(current_index)

    def _make_page(self, key, title, detail):
        page = QWidget()
        page.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)
        heading = QVBoxLayout()
        heading.setSpacing(4)
        eyebrow = QLabel("JARVIS  /  CONFIGURAÇÕES DO SISTEMA")
        eyebrow.setStyleSheet(f"color:{CYAN};font-size:8px;font-weight:800;letter-spacing:1.8px;")
        h = QLabel(title)
        h.setStyleSheet(f"color:{TEXT};font-size:23px;font-weight:700;")
        d = QLabel(detail)
        d.setWordWrap(True)
        d.setStyleSheet(f"color:rgba(174,188,220,205);font-size:10px;")
        heading.addWidget(eyebrow)
        heading.addWidget(h)
        heading.addWidget(d)
        layout.addLayout(heading)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner.setStyleSheet("background:transparent;")
        body = QVBoxLayout(inner)
        body.setContentsMargins(0, 4, 10, 12)
        body.setSpacing(12)
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)
        self._pages[key] = page
        self.stack.addWidget(page)
        return body, inner

    def _card(self, title, detail, action, key, accent=VIOLET):
        card = QFrame()
        card.setObjectName("WorkspaceOverviewCard")
        card.setMinimumHeight(154)
        card.setStyleSheet(f"""
            QFrame#WorkspaceOverviewCard {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 rgba(24,24,51,190), stop:1 rgba(9,15,31,205));
                border: 1px solid rgba(130,145,198,58);
                border-radius: 17px;
            }}
            QFrame#WorkspaceOverviewCard:hover {{
                border: 1px solid rgba(85,231,222,145);
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 rgba(32,29,66,205), stop:1 rgba(10,21,38,220));
            }}
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(17, 15, 17, 15)
        lay.setSpacing(8)

        head = QHBoxLayout()
        glyph = QLabel("◈")
        glyph.setStyleSheet(f"color:{accent};font-size:16px;font-weight:700;background:transparent;")
        cap = QLabel(title)
        cap.setStyleSheet(f"color:{accent};font-size:9px;font-weight:800;letter-spacing:1.15px;background:transparent;")
        tag = QLabel("MODULE")
        tag.setStyleSheet("color:rgba(150,166,205,125);font-size:7px;font-weight:700;letter-spacing:1.3px;background:transparent;")
        head.addWidget(glyph)
        head.addWidget(cap, 1)
        head.addWidget(tag)
        lay.addLayout(head)

        desc = QLabel(detail)
        desc.setWordWrap(True)
        desc.setMinimumHeight(30)
        desc.setStyleSheet(f"color:rgba(177,190,220,210);font-size:9px;background:transparent;")
        lay.addWidget(desc, 1)

        separator = QFrame()
        separator.setFixedHeight(1)
        separator.setStyleSheet(f"background:rgba(145,158,205,34);border:0;")
        lay.addWidget(separator)

        btn = QPushButton(action)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumHeight(34)
        btn.clicked.connect(lambda _=False, k=key: self.set_page(k))
        btn.setStyleSheet(f"""
            QPushButton {{
                color: {TEXT};
                background: rgba(255,255,255,8);
                border: 1px solid rgba(150,145,210,95);
                border-left: 2px solid {accent};
                border-radius: 10px;
                padding: 6px 12px;
                text-align: left;
                font-size: 8px;
                font-weight: 800;
                letter-spacing: .7px;
            }}
            QPushButton:hover {{
                color: white;
                background: rgba(85,231,222,25);
                border: 1px solid {CYAN};
            }}
        """)
        lay.addWidget(btn)
        return card

    def _style_action(self, button, accent=VIOLET, primary=False):
        button.setStyleSheet(f"""
            QPushButton {{
                color:{TEXT};
                background:{'rgba(105,88,205,105)' if primary else 'rgba(255,255,255,7)'};
                border:1px solid {accent};
                border-radius:11px;
                padding:8px 14px;
                font-size:9px;
                font-weight:800;
                letter-spacing:.65px;
            }}
            QPushButton:hover {{ color:white; background:rgba(55,205,199,34); border-color:{CYAN}; }}
            QPushButton:pressed {{ background:rgba(105,88,205,145); }}
            QPushButton:disabled {{ color:#59627e; border-color:#333d59; }}
        """)

    def _build_overview(self):
        body, inner = self._make_page(
            "overview", "Neural control center",
            "Live configuration and system modules — connected directly to this JARVIS installation."
        )
        try:
            from memory.config_manager import get_provider_mode, get_pipeline
            mode = get_provider_mode()
            pipe = get_pipeline() or {}
            engine_text = ("GEMINI LIVE" if mode != "pipeline" else
                           "PIPELINE  ·  %s / %s / %s" %
                           tuple(str(pipe.get(k) or "not set").upper() for k in ("stt", "llm", "tts")))
        except Exception:
            engine_text = "ENGINE STATUS UNAVAILABLE"
        try:
            cfg = self.win._read_full_config() if hasattr(self.win, "_read_full_config") else {}
        except Exception:
            cfg = {}
        name = (getattr(self.win, "_assistant_name", None) or cfg.get("assistant_name") or "JARVIS")
        identity_detail = (
            f"{name} · Nome, voz, aparência e motor de conversa."
            if self._language == "pt-BR"
            else f"{name} · Assistant name, voice, color and conversation mode."
        )
        grid = QGridLayout()
        grid.setSpacing(12)
        cards = [
            self._card("ENGINE CORE", engine_text, "MANAGE MODELS  →", "engine", VIOLET),
            self._card("VOICE & AUDIO", "Microphone, speakers, voice route and input/output levels.", "CONFIGURE AUDIO  →", "audio", CYAN),
            self._card("MEMORY", "Inspect, search, update and remove stored memories.", "OPEN MEMORY  →", "memory", "#b49aff"),
            self._card("EXTENSIONS", "Installed plugins, capabilities and their configuration.", "MANAGE EXTENSIONS  →", "plugins", "#ffb45d"),
            self._card("IDENTITY", identity_detail, "CUSTOMIZE JARVIS  →", "identity", "#77b9ff"),
            self._card("REMOTE ACCESS", "Secure access session and device pairing.", "OPEN REMOTE  →", "remote", "#ff829d"),
        ]
        for i, card in enumerate(cards):
            grid.addWidget(card, i // 3, i % 3)
        body.addLayout(grid)
        note = QLabel("LIVE CONFIGURATION  ·  LOCAL SECRETS STAY MASKED  ·  CHANGES APPLY THROUGH THE ORIGINAL ENGINE")
        note.setStyleSheet(f"color:{MUTED};font-size:8px;letter-spacing:1px;padding:6px;")
        body.addWidget(note)
        body.addStretch(1)

    def _build_panel_page(self, key):
        titles = {
            "engine": ("Engine core", "Routing for hearing, reasoning, speaking, background requests and coding."),
            "audio": ("Voice & audio", "Select the real input/output devices and test the signal path."),
            "memory": ("Memory", "Review and maintain the assistant's persistent memory."),
            "plugins": ("Extensions", "Enable or disable installed capabilities."),
            "plugin_settings": ("Extension setup", "Configure credentials and settings for connected modules."),
            "identity": ("Identity", "Assistant identity, voice, appearance and conversation engine."),
            "remote": ("Remote access", "Generate a secure pairing session for another device."),
            "setup": ("Initial setup", "Connect JARVIS to its conversation service and finish the local setup."),
        }
        if key not in titles:
            return
        title, detail = titles[key]
        body, inner = self._make_page(key, title, detail)

        back = QPushButton("←  VOLTAR ÀS CONFIGURAÇÕES" if self.embedded else "←  BACK TO SYSTEM")
        self._style_action(back, VIOLET)
        if self.embedded:
            back.clicked.connect(self._close)
        else:
            back.clicked.connect(lambda: self.set_page("overview"))
        body.addWidget(back, 0, Qt.AlignmentFlag.AlignLeft)
        if key == "plugins":
            setup = QPushButton("CONFIGURE EXTENSION SETTINGS  →")
            self._style_action(setup, CYAN)
            setup.clicked.connect(lambda: self.set_page("plugin_settings"))
            body.addWidget(setup)

        try:
            panel = self._create_panel(key, inner)
            self._panels[key] = panel
            if panel is not None:
                body.addWidget(panel, 0)
            else:
                msg = QLabel("This module is not available in the current installation.")
                msg.setStyleSheet(f"color:{MUTED};padding:20px;")
                body.addWidget(msg)
        except Exception as exc:
            err = QLabel("%s  ·  %s" % (type(exc).__name__, str(exc)[:220]))
            err.setWordWrap(True)
            err.setStyleSheet(f"color:{DANGER};padding:18px;")
            body.addWidget(err)
            if hasattr(self.win, "_log"):
                self.win._log.append_log("ERR: %s page failed: %s" % (key, type(exc).__name__))
        body.addStretch(1)


    def _module_frame(self, parent, title, detail="", width=920):
        frame = QFrame(parent)
        frame.setObjectName("WorkspaceModule")
        frame.setMinimumWidth(0)
        frame.setMaximumWidth(width)
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        frame.setStyleSheet(f"""
            QFrame#WorkspaceModule {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 rgba(18,20,43,194), stop:1 rgba(8,13,29,220));
                border: 1px solid rgba(135,122,220,92);
                border-radius: 17px;
            }}
            QLabel {{ color:{TEXT}; background:transparent; }}
            QLineEdit, QComboBox, QTextEdit, QPlainTextEdit {{
                color:{TEXT};
                background: rgba(255,255,255,8);
                border:1px solid rgba(130,145,195,88);
                border-radius:11px;
                padding:9px 11px;
                selection-background-color:rgba(105,88,205,170);
            }}
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{
                background:rgba(20,28,52,220);
                border:1px solid {CYAN};
            }}
            QComboBox QAbstractItemView {{
                color:{TEXT}; background:#101a32;
                selection-background-color:#50479b;
            }}
            QScrollArea {{ background:transparent; border:0; }}
            QCheckBox {{ color:{TEXT}; spacing:8px; }}
            QSlider::groove:horizontal {{
                height:4px; background:rgba(145,155,200,45); border-radius:2px;
            }}
            QSlider::handle:horizontal {{
                width:14px; margin:-5px 0; border-radius:7px;
                background:{CYAN}; border:1px solid rgba(255,255,255,150);
            }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        head = QVBoxLayout()
        head.setSpacing(4)
        h = QLabel(title.upper())
        h.setStyleSheet(f"color:{CYAN};font-size:10px;font-weight:800;letter-spacing:1.4px;background:transparent;")
        head.addWidget(h)
        if detail:
            d = QLabel(detail)
            d.setWordWrap(True)
            d.setStyleSheet(f"color:{MUTED};font-size:9px;background:transparent;")
            head.addWidget(d)
        layout.addLayout(head)
        return frame, layout

    def _section_card(self, parent_layout, title, detail=""):
        card = QFrame()
        card.setObjectName("WorkspaceSection")
        card.setStyleSheet(f"""
            QFrame#WorkspaceSection {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 rgba(25,31,60,175), stop:1 rgba(13,20,40,155));
                border:1px solid rgba(120,139,196,78);
                border-radius:14px;
            }}
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        label = QLabel(title.upper())
        label.setStyleSheet(f"color:{VIOLET};font-size:9px;font-weight:800;letter-spacing:1px;background:transparent;")
        lay.addWidget(label)
        if detail:
            sub = QLabel(detail)
            sub.setWordWrap(True)
            sub.setStyleSheet(f"color:{MUTED};font-size:8px;background:transparent;")
            lay.addWidget(sub)
        parent_layout.addWidget(card)
        return card, lay

    def _field(self, layout, label, widget, hint=""):
        cap = QLabel(label.upper())
        cap.setStyleSheet(f"color:rgba(155,174,218,220);font-size:8px;font-weight:800;letter-spacing:1px;background:transparent;")
        layout.addWidget(cap)
        layout.addWidget(widget)
        if hint:
            note = QLabel(hint)
            note.setWordWrap(True)
            note.setStyleSheet(f"color:{MUTED};font-size:8px;background:transparent;")
            layout.addWidget(note)

    def _action_button(self, label, accent=VIOLET, primary=False):
        button = QPushButton(label)
        button.setMinimumHeight(38)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(f"""
            QPushButton {{
                color:{TEXT};
                background:{'rgba(105,88,205,105)' if primary else 'rgba(255,255,255,8)'};
                border:1px solid {accent};
                border-radius:11px;
                padding:8px 14px;
                font-size:9px;
                font-weight:800;
                letter-spacing:.65px;
            }}
            QPushButton:hover {{ background:rgba(55,205,199,35); border-color:{CYAN}; }}
            QPushButton:disabled {{ color:#59627e; border-color:#333d59; }}
        """)
        return button

    def _status_label(self, text=""):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(f"color:{MUTED};font-size:8px;background:transparent;")
        return label

    def _create_panel(self, key, parent):
        if key == "engine":
            from gui.providers_holo import ProvidersHoloOverlay
            panel = ProvidersHoloOverlay(parent=parent)
            panel.changed.connect(self.win._on_providers_applied)
            return panel
        if key == "audio":
            return self._build_audio_panel(parent)
        if key == "memory":
            return self._build_memory_panel(parent)
        if key == "plugins":
            return self._build_plugins_panel(parent)
        if key == "plugin_settings":
            return self._build_plugin_settings_panel(parent)
        if key == "identity":
            return self._build_identity_panel(parent)
        if key == "remote":
            return self._build_remote_panel(parent)
        if key == "setup":
            return self._build_setup_panel(parent)
        return None

    def _build_identity_panel(self, parent):
        from gui.theme import DEFAULT_UI_COLOR, _read_full_config
        from memory.config_manager import AVAILABLE_VOICES, DEFAULT_VOICE, get_provider_mode, get_app_language
        from core.i18n import LANGUAGE_CHOICES, tr
        cfg = _read_full_config()
        frame, root = self._module_frame(
            parent, "Assistant identity",
            "Personalize the JARVIS interface and conversation. Changes are applied to the running session."
        )
        card, form = self._section_card(root, "Profile", "The assistant name appears throughout the desktop interface.")
        name = QLineEdit(str(cfg.get("assistant_name") or "JARVIS"))
        user = QLineEdit(str(cfg.get("user_name") or ""))
        user.setPlaceholderText("Optional")
        self._field(form, "Assistant name", name)
        self._field(form, "Your name", user, "Leave blank when you prefer the assistant to address you automatically.")
        card, form = self._section_card(root, "Voice and engine", "Choose the Live voice and the conversation engine.")
        voice = QComboBox()
        voice.addItems(AVAILABLE_VOICES)
        voice.setCurrentText(str(cfg.get("voice_name") or DEFAULT_VOICE))
        engine = QComboBox()
        engine.addItem("Gemini Live", "gemini")
        engine.addItem("JARVIS Voice pipeline", "pipeline")
        current_mode = get_provider_mode()
        engine.setCurrentIndex(max(0, engine.findData(current_mode)))
        self._field(form, "Assistant voice", voice)
        self._field(form, "Conversation engine", engine)
        language = QComboBox()
        for label, code in LANGUAGE_CHOICES:
            language.addItem(label, code)
        language.setCurrentIndex(max(0, language.findData(get_app_language())))
        self._field(
            form, "JARVIS language", language,
            "Choose the language used for the interface, assistant replies and speech."
        )
        card, form = self._section_card(root, "Visual identity", "Set the accent color used by the JARVIS HUD and controls.")
        color = QLineEdit(str(cfg.get("ui_color") or DEFAULT_UI_COLOR))
        color.setPlaceholderText("#8262ff")
        self._field(form, "Accent color (hex)", color, "Enter a six-digit color such as #8262ff. A valid value previews immediately.")
        def preview(value):
            value = str(value or "").strip()
            if len(value) == 7 and value.startswith("#"):
                try:
                    int(value[1:], 16)
                    self.win._preview_ui_color(value)
                except ValueError:
                    pass
        color.textEdited.connect(preview)
        card, form = self._section_card(root, "Gemini credentials", "Leave blank to keep the currently saved key. Secret values are never displayed.")
        key = QLineEdit()
        key.setEchoMode(QLineEdit.EchoMode.Password)
        key.setPlaceholderText("Paste a new Gemini API key to replace it")
        self._field(form, "Gemini API key", key)
        status = self._status_label()
        root.addWidget(status)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        save = self._action_button("SAVE IDENTITY", CYAN, True)
        save.clicked.connect(lambda: self._save_identity(name, user, color, voice, engine, language, key, status))
        buttons.addWidget(save)
        root.addLayout(buttons)
        return frame

    def _save_identity(self, name, user, color, voice, engine, language, key, status):
        hex_color = color.text().strip() or "#8262ff"
        from core.i18n import tr
        if len(hex_color) != 7 or not hex_color.startswith("#"):
            self._set_i18n_text(status, "Use a valid hexadecimal color, for example #8262ff.")
            status.setStyleSheet(f"color:{DANGER};background:transparent;")
            return
        try:
            int(hex_color[1:], 16)
        except ValueError:
            self._set_i18n_text(status, "Use a valid hexadecimal color, for example #8262ff.")
            status.setStyleSheet(f"color:{DANGER};background:transparent;")
            return
        self.win._apply_name_update(
            name.text().strip(), user.text().strip(), hex_color,
            voice.currentText(), engine.currentData(), key.text().strip(),
            language.currentData()
        )
        self._set_i18n_text(status, "Identity saved. The JARVIS interface has been updated.")
        status.setStyleSheet(f"color:{CYAN};background:transparent;")

    def _build_setup_panel(self, parent):
        from gui.theme import _read_full_config
        import platform

        cfg = _read_full_config()
        frame, root = self._module_frame(
            parent,
            "Connect your JARVIS",
            "Each installation uses its owner's Gemini API key. No developer key is bundled or shared."
        )

        card, form = self._section_card(
            root,
            "Primary AI engine",
            "This key powers the main JARVIS conversation and its tool orchestration."
        )
        key = QLineEdit()
        key.setEchoMode(QLineEdit.EchoMode.Password)
        key.setPlaceholderText("Paste your personal Gemini API key")
        self._field(form, "Your Gemini API key", key)

        help_link = QLabel(
            '<a href="https://aistudio.google.com/apikey">Create or manage a key in Google AI Studio ↗</a>'
        )
        help_link.setOpenExternalLinks(True)
        help_link.setStyleSheet(f"color:{CYAN};font-size:9px;background:transparent;")
        form.addWidget(help_link)

        if cfg.get("gemini_api_key"):
            saved = self._status_label(
                "A key is already present in this local profile. Enter the key "
                "you want this installation to use; the saved value is never shown."
            )
            form.addWidget(saved)

        card, form = self._section_card(
            root,
            "Installation",
            "The operating system is stored locally with your preferences."
        )
        os_box = QComboBox()
        for label, value in (
            ("Windows", "Windows"),
            ("macOS", "Darwin"),
            ("Linux", "Linux"),
        ):
            os_box.addItem(label, value)
        detected = platform.system()
        os_box.setCurrentIndex(max(0, os_box.findData(detected)))
        self._field(form, "Operating system", os_box)

        status = self._status_label(
            "The key is checked with Google before it is saved. It stays on this "
            "computer in config/api_keys.json and must never be committed to Git."
        )
        root.addWidget(status)

        button = self._action_button("VALIDATE AND CONNECT", CYAN, True)
        button.clicked.connect(
            lambda: self._start_setup_validation(key, os_box, status, button)
        )
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button)
        root.addLayout(row)
        return frame

    def _start_setup_validation(self, key_widget, os_box, status, button):
        key = key_widget.text().strip()
        if len(key) < 20:
            self._set_i18n_text(status, "Paste a complete Gemini API key before continuing.")
            status.setStyleSheet(f"color:{DANGER};background:transparent;")
            key_widget.setFocus()
            return

        os_name = os_box.currentData()
        button.setEnabled(False)
        self._set_i18n_text(button, "VALIDATING WITH GOOGLE...")
        self._set_i18n_text(status, "Checking the API key securely. The secret is not displayed or logged.")
        status.setStyleSheet(f"color:{MUTED};background:transparent;")

        def worker():
            try:
                from core.api_key_validation import validate_gemini_api_key
                ok, message = validate_gemini_api_key(key)
            except Exception:
                ok = False
                message = (
                    "The API validation service could not start. Check the "
                    "installation and try again."
                )
            self.setup_validation_finished.emit({
                "ok": bool(ok),
                "message": str(message),
                "key": key,
                "os_name": os_name,
                "status": status,
                "button": button,
                "key_widget": key_widget,
            })

        threading.Thread(
            target=worker,
            name="jarvis-api-key-validation",
            daemon=True,
        ).start()

    def _on_setup_validation_finished(self, result):
        status = result.get("status")
        button = result.get("button")
        if button is not None:
            button.setEnabled(True)
            self._set_i18n_text(button, "VALIDATE AND CONNECT")

        if not result.get("ok"):
            if status is not None:
                self._set_i18n_text(status, str(result.get("message") or "The API key could not be validated."))
                status.setStyleSheet(f"color:{DANGER};background:transparent;")
            return

        try:
            self.win._on_setup_done(
                result.get("key", ""),
                result.get("os_name", ""),
                validated=True,
            )
        except Exception as exc:
            if status is not None:
                self._set_i18n_text(status, "The API key was validated, but local setup could not be saved: " + type(exc).__name__)
                status.setStyleSheet(f"color:{DANGER};background:transparent;")
            return

        key_widget = result.get("key_widget")
        if key_widget is not None:
            key_widget.clear()
        if status is not None:
            self._set_i18n_text(status, "API key validated and saved locally. JARVIS is ready.")
            status.setStyleSheet(f"color:{CYAN};background:transparent;")
        self.set_page("overview")

    def _build_audio_panel(self, parent):
        from core.audio_devices import list_devices, DEFAULT_LABEL, get_output_volume, set_output_volume
        from memory.config_manager import (
            get_input_device, get_output_device, save_input_device, save_output_device,
        )
        frame, root = self._module_frame(
            parent, "Voice and audio",
            "Select the actual microphone and speakers used by JARVIS. Device tests run in a worker and do not freeze the interface."
        )
        self._audio_test_widgets = {}
        card, form = self._section_card(root, "Microphone", "This is the input device JARVIS listens to.")
        inp = QComboBox()
        inp.addItem(DEFAULT_LABEL, "")
        for device in list_devices("input"):
            inp.addItem(device, device)
        selected = get_input_device()
        idx = inp.findData(selected)
        if selected and idx < 0:
            inp.addItem(selected + "  (not connected)", selected)
            idx = inp.count() - 1
        inp.setCurrentIndex(max(0, idx))
        self._field(form, "Input device", inp)
        in_status = self._status_label()
        form.addWidget(in_status)
        in_test = self._action_button("TEST MICROPHONE", VIOLET)
        in_test.clicked.connect(lambda: self._run_audio_test("input", inp.currentData() or "", in_test, in_status))
        form.addWidget(in_test)
        card, form = self._section_card(root, "Speakers", "This is the output device used for spoken replies.")
        out = QComboBox()
        out.addItem(DEFAULT_LABEL, "")
        for device in list_devices("output"):
            out.addItem(device, device)
        selected_out = get_output_device()
        idx = out.findData(selected_out)
        if selected_out and idx < 0:
            out.addItem(selected_out + "  (not connected)", selected_out)
            idx = out.count() - 1
        out.setCurrentIndex(max(0, idx))
        self._field(form, "Output device", out)
        out_status = self._status_label()
        form.addWidget(out_status)
        out_test = self._action_button("PLAY TEST TONE", CYAN)
        out_test.clicked.connect(lambda: self._run_audio_test("output", out.currentData() or "", out_test, out_status))
        form.addWidget(out_test)
        volume = None
        try:
            volume = get_output_volume(out.currentData() or "")
        except Exception:
            volume = None
        if volume is not None:
            card, form = self._section_card(root, "Output level", "The slider applies to the selected output device.")
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(int(volume))
            label = QLabel(str(int(volume)) + "%")
            label.setStyleSheet(f"color:{CYAN};font-weight:700;background:transparent;")
            slider.valueChanged.connect(lambda v: label.setText(str(v) + "%"))
            slider.sliderReleased.connect(lambda s=slider, cb=out: self._save_output_volume(s.value(), cb.currentData() or "", out_status))
            form.addWidget(slider)
            form.addWidget(label)
        status = self._status_label("Applying device changes reconnects the conversation. Your transcript and memory remain saved.")
        root.addWidget(status)
        row = QHBoxLayout()
        row.addStretch(1)
        apply_btn = self._action_button("APPLY DEVICES", CYAN, True)
        apply_btn.clicked.connect(lambda: self._save_audio_devices(inp, out, status))
        row.addWidget(apply_btn)
        root.addLayout(row)
        return frame

    def _run_audio_test(self, kind, name, button, status):
        button.setEnabled(False)
        self._set_i18n_text(status, "Testing…")
        status.setStyleSheet(f"color:{MUTED};background:transparent;")
        self._audio_test_widgets[kind] = (button, status)
        def worker():
            try:
                from core.audio_devices import measure_input, play_tone
                result = measure_input(name, seconds=2.5) if kind == "input" else play_tone(name, seconds=0.6)
                self.audio_test_finished.emit(kind, bool(result.get("ok")), str(result.get("verdict") or "Test completed."))
            except Exception as exc:
                self.audio_test_finished.emit(kind, False, str(exc))
        import threading
        threading.Thread(target=worker, daemon=True, name="jarvis-audio-settings-test").start()

    def _on_audio_test_finished(self, kind, ok, message):
        button, status = self._audio_test_widgets.get(kind, (None, None))
        if button is not None:
            button.setEnabled(True)
        if status is not None:
            self._set_i18n_text(status, message)
            status.setStyleSheet(f"color:{CYAN if ok else DANGER};background:transparent;")

    def _save_output_volume(self, value, name, status):
        try:
            from core.audio_devices import set_output_volume
            if set_output_volume(value, name):
                self._set_i18n_text(status, "Output level updated.")
            else:
                self._set_i18n_text(status, "The selected output does not expose a software volume control.")
        except Exception as exc:
            self._set_i18n_text(status, "Could not change output level: " + str(exc)[:140])

    def _save_audio_devices(self, inp, out, status):
        try:
            from memory.config_manager import save_input_device, save_output_device
            save_input_device(inp.currentData() or "")
            save_output_device(out.currentData() or "")
            self.win._on_audio_devices_applied()
            self._set_i18n_text(status, "Devices saved. JARVIS is reconnecting to the selected audio path.")
            status.setStyleSheet(f"color:{CYAN};background:transparent;")
        except Exception as exc:
            self._set_i18n_text(status, "Could not save audio devices: " + str(exc)[:180])
            status.setStyleSheet(f"color:{DANGER};background:transparent;")

    def _build_memory_panel(self, parent):
        from memory.memory_manager import all_entries_for_ui
        frame, root = self._module_frame(
            parent, "Persistent memory",
            "Review exactly what JARVIS remembers. Edit, search, import, or remove entries stored locally."
        )
        tools_card, tools = self._section_card(root, "Search and filter")
        row = QHBoxLayout()
        search = QLineEdit()
        search.setPlaceholderText("Search by category, key, value or date…")
        category = QComboBox()
        category.addItem("All categories", "all")
        for cat in ("identity", "preferences", "projects", "relationships", "wishes", "notes", "sessions"):
            category.addItem(cat.replace("_", " ").title(), cat)
        row.addWidget(search, 1)
        row.addWidget(category)
        tools.addLayout(row)
        list_card, list_layout = self._section_card(root, "Stored entries")
        summary = self._status_label()
        list_layout.addWidget(summary)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(250)
        scroll.setMaximumHeight(500)
        inner = QWidget()
        rows_layout = QVBoxLayout(inner)
        rows_layout.setContentsMargins(0, 0, 8, 0)
        rows_layout.setSpacing(8)
        scroll.setWidget(inner)
        list_layout.addWidget(scroll)
        actions = QHBoxLayout()
        import_btn = self._action_button("IMPORT NOTE", VIOLET)
        import_btn.clicked.connect(lambda: self._import_memory_note())
        actions.addWidget(import_btn)
        actions.addStretch(1)
        list_layout.addLayout(actions)
        def refresh():
            while rows_layout.count():
                item = rows_layout.takeAt(0)
                child = item.widget()
                if child is not None:
                    child.hide()
                    child.deleteLater()
            rows = all_entries_for_ui()
            q = search.text().casefold().strip()
            cat = category.currentData() or "all"
            rows = [r for r in rows if (cat == "all" or r.get("category") == cat) and
                    (not q or q in str(r.get("key", "")).casefold() or
                     q in str(r.get("label", "")).casefold() or
                     q in str(r.get("value", "")).casefold() or
                     q in str(r.get("category", "")).casefold() or
                     q in str(r.get("updated", "")).casefold())]
            total_entries = len(all_entries_for_ui())
            summary_text = (
                f"{len(rows)} de {total_entries} registros exibidos · mais recentes primeiro · salvos neste computador"
                if self._language == "pt-BR"
                else f"{len(rows)} of {total_entries} entries shown · newest first · stored on this computer"
            )
            summary.setText(summary_text)
            if not rows:
                empty = QLabel("No memories match this filter.")
                empty.setStyleSheet(f"color:{MUTED};background:transparent;padding:18px;")
                rows_layout.addWidget(empty)
            for r in rows:
                item_card = QFrame()
                item_card.setObjectName("MemoryEntry")
                item_card.setStyleSheet("QFrame#MemoryEntry{background:rgba(8,14,31,190);border:1px solid rgba(110,128,188,70);border-radius:10px;}")
                row_l = QVBoxLayout(item_card)
                row_l.setContentsMargins(12, 10, 12, 10)
                row_l.setSpacing(5)
                top = QHBoxLayout()
                title = QLabel(r.get("label") or str(r.get("key", "Memory")).replace("_", " "))
                title.setStyleSheet(f"color:{TEXT};font-weight:700;background:transparent;")
                top.addWidget(title, 1)
                meta = QLabel((str(r.get("category") or "notes").upper() + "  ·  " + str(r.get("updated") or "—")))
                meta.setStyleSheet(f"color:{CYAN};font-size:8px;background:transparent;")
                top.addWidget(meta)
                row_l.addLayout(top)
                value = QLabel(str(r.get("value", "")))
                value.setWordWrap(True)
                value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                value.setStyleSheet(f"color:{MUTED};font-size:9px;background:transparent;")
                row_l.addWidget(value)
                buttons = QHBoxLayout()
                if r.get("category") != "sessions":
                    edit = self._action_button("EDIT", VIOLET)
                    edit.setMinimumHeight(28)
                    edit.clicked.connect(lambda _=False, rr=dict(r), fn=refresh: self._edit_memory_entry(rr, fn))
                    buttons.addWidget(edit)
                forget_btn = self._action_button("FORGET", DANGER)
                forget_btn.setMinimumHeight(28)
                forget_btn.clicked.connect(lambda _=False, rr=dict(r), fn=refresh: self._forget_memory_entry(rr, fn))
                buttons.addWidget(forget_btn)
                buttons.addStretch(1)
                row_l.addLayout(buttons)
                rows_layout.addWidget(item_card)
            rows_layout.addStretch(1)
            self._apply_translations()
        search.textChanged.connect(refresh)
        category.currentIndexChanged.connect(refresh)
        refresh()
        return frame

    def _edit_memory_entry(self, row, refresh):
        from memory.memory_manager import save_memory_item
        value, ok = QInputDialog.getMultiLineText(self, self._tr("Edit memory"), str(row.get("key", "")), str(row.get("value", "")))
        if not ok or not value.strip() or value.strip() == str(row.get("value", "")):
            return
        answer = QMessageBox.question(self, self._tr("Confirm update"), self._tr("Replace this saved memory item?"), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            result = save_memory_item(str(row["category"]), str(row["key"]), value.strip(), confirm_overwrite=True)
            if result.get("status") in {"duplicate", "possible_duplicate"}:
                duplicate = QMessageBox.question(self, self._tr("Possible duplicate"), self._tr("This memory resembles another saved entry. Store it anyway?"), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if duplicate != QMessageBox.StandardButton.Yes:
                    return
                result = save_memory_item(str(row["category"]), str(row["key"]), value.strip(), confirm_overwrite=True, confirm_duplicate=True)
            if result.get("status") != "saved":
                QMessageBox.warning(self, self._tr("Memory unchanged"), self._tr("The item was not updated: ") + str(result.get("status")))
                return
        except Exception as exc:
            QMessageBox.warning(self, self._tr("Memory error"), str(exc))
            return
        refresh()

    def _forget_memory_entry(self, row, refresh):
        answer = QMessageBox.question(self, self._tr("Confirm deletion"), self._tr("Forget this saved memory?") + "\n\n" + str(row.get("key", "")), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        from memory.memory_manager import forget
        result = forget(str(row.get("key", "")), str(row.get("category", "notes")))
        if not str(result).startswith("Forgotten:"):
            QMessageBox.warning(self, self._tr("Memory unchanged"), str(result))
            return
        refresh()

    def _import_memory_note(self):
        title, ok = QInputDialog.getText(self, self._tr("Import memory"), self._tr("Short title:"))
        if not ok or not title.strip():
            return
        content, ok = QInputDialog.getMultiLineText(self, self._tr("Import memory"), self._tr("Paste information JARVIS should remember (up to 12,000 characters):"))
        if not ok or not content.strip():
            return
        try:
            from memory.memory_manager import import_memory_text
            result = import_memory_text(title.strip(), content)
            QMessageBox.information(self, self._tr("Memory imported"), f"Saved {result.get('entries', 0)} searchable memory part(s).")
        except Exception as exc:
            QMessageBox.warning(self, self._tr("Import failed"), str(exc))

    def _build_plugins_panel(self, parent):
        from memory.config_manager import save_plugin_enabled
        plugins = self.win.get_plugins() if self.win.get_plugins else []
        frame, root = self._module_frame(
            parent, "Extensions",
            "Enable or disable installed JARVIS capabilities. Changes are stored in the local configuration."
        )
        discovered = (
            f"{len(plugins)} módulos encontrados"
            if self._language == "pt-BR"
            else f"{len(plugins)} modules discovered"
        )
        card, body = self._section_card(root, "Installed extensions", discovered)
        if not plugins:
            body.addWidget(self._status_label("No extensions were discovered in the plugins folder."))
            return frame
        for plugin in plugins:
            line = QFrame()
            line.setObjectName("PluginEntry")
            line.setStyleSheet("QFrame#PluginEntry{background:rgba(8,14,31,190);border:1px solid rgba(110,128,188,65);border-radius:10px;}")
            row = QHBoxLayout(line)
            row.setContentsMargins(12, 9, 12, 9)
            text_col = QVBoxLayout()
            name = QLabel(str(plugin.get("name") or plugin.get("file") or "Extension"))
            name.setStyleSheet(f"color:{TEXT};font-weight:700;background:transparent;")
            desc = QLabel(str(plugin.get("description") or plugin.get("error") or "Installed module"))
            desc.setWordWrap(True)
            desc.setStyleSheet(f"color:{MUTED};font-size:8px;background:transparent;")
            text_col.addWidget(name)
            text_col.addWidget(desc)
            row.addLayout(text_col, 1)
            toggle = self._action_button("ON" if plugin.get("enabled", True) else "OFF", CYAN if plugin.get("enabled", True) else VIOLET)
            toggle.setCheckable(True)
            toggle.setChecked(bool(plugin.get("enabled", True)))
            toggle.setMinimumWidth(72)
            if not plugin.get("valid", True):
                self._set_i18n_text(toggle, "ERROR")
                toggle.setEnabled(False)
            else:
                toggle.clicked.connect(lambda checked, n=str(plugin.get("name")), b=toggle: self._toggle_plugin(n, checked, b))
            row.addWidget(toggle)
            body.addWidget(line)
        return frame

    def _toggle_plugin(self, name, enabled, button):
        from memory.config_manager import save_plugin_enabled
        try:
            save_plugin_enabled(name, bool(enabled))
            self._set_i18n_text(button, "ON" if enabled else "OFF")
            button.setStyleSheet(f"QPushButton{{color:{TEXT};background:{'rgba(55,205,199,42)' if enabled else SURFACE_2};border:1px solid {CYAN if enabled else VIOLET};border-radius:9px;padding:7px 14px;font-size:9px;font-weight:800;}}")
        except Exception as exc:
            button.setChecked(not enabled)
            self.win._log.append_log("ERR: Could not save extension setting: " + str(exc)[:160])

    def _build_plugin_settings_panel(self, parent):
        sections = self.win.get_plugin_settings() if self.win.get_plugin_settings else []
        frame, root = self._module_frame(
            parent, "Extension setup",
            "Configure each extension through its declared settings schema. Password values stay masked."
        )
        self._plugin_setting_widgets = {}
        self._plugin_status_labels = {}
        if not sections:
            root.addWidget(self._status_label("No installed extensions currently declare configurable settings."))
            return frame
        for sec in sections:
            if not isinstance(sec, dict):
                continue
            namespace = str(sec.get("namespace") or sec.get("plugin") or "plugin")
            title = str(sec.get("title") or namespace)
            fields = sec.get("fields") or []
            values = sec.get("values") or {}
            card, body = self._section_card(root, title, "Configuration namespace: " + namespace)
            controls = {}
            for field in fields:
                if not isinstance(field, dict) or not field.get("key"):
                    continue
                k = str(field["key"])
                kind = str(field.get("type") or "text").lower()
                label = str(field.get("label") or k)
                value = values.get(k, field.get("default"))
                if kind == "choice":
                    widget = QComboBox()
                    widget.addItems([str(v) for v in field.get("options", [])])
                    if value is not None:
                        widget.setCurrentText(str(value))
                elif kind == "toggle":
                    widget = QCheckBox("Enabled")
                    widget.setChecked(bool(value))
                    widget.setStyleSheet(f"color:{TEXT};background:transparent;")
                else:
                    widget = QLineEdit("" if value is None else str(value))
                    if kind == "password":
                        widget.setEchoMode(QLineEdit.EchoMode.Password)
                    widget.setPlaceholderText(str(field.get("placeholder") or ""))
                self._field(body, label, widget)
                controls[k] = (kind, widget)
            status = self._status_label()
            body.addWidget(status)
            self._plugin_status_labels[namespace] = status
            self._plugin_setting_widgets[namespace] = controls
            action = sec.get("action")
            row = QHBoxLayout()
            save = self._action_button("SAVE SETTINGS", CYAN, True)
            save.clicked.connect(lambda _=False, ns=namespace: self._save_plugin_settings(ns))
            row.addWidget(save)
            if isinstance(action, dict) and callable(action.get("run")):
                test = self._action_button(str(action.get("label") or "TEST CONNECTION"), VIOLET)
                test.clicked.connect(lambda _=False, ns=namespace, fn=action.get("run"): self._run_plugin_test(ns, fn))
                row.addWidget(test)
            row.addStretch(1)
            body.addLayout(row)
        return frame

    def _gather_plugin_settings(self, namespace):
        result = {}
        for key, (kind, widget) in self._plugin_setting_widgets.get(namespace, {}).items():
            if kind == "choice":
                result[key] = widget.currentText()
            elif kind == "toggle":
                result[key] = widget.isChecked()
            else:
                result[key] = widget.text().strip()
        return result

    def _save_plugin_settings(self, namespace):
        from memory.config_manager import save_plugin_config
        try:
            save_plugin_config(namespace, self._gather_plugin_settings(namespace))
            status = self._plugin_status_labels.get(namespace)
            if status:
                self._set_i18n_text(status, "Settings saved.")
                status.setStyleSheet(f"color:{CYAN};background:transparent;")
        except Exception as exc:
            status = self._plugin_status_labels.get(namespace)
            if status:
                self._set_i18n_text(status, "Could not save settings: " + str(exc)[:160])
                status.setStyleSheet(f"color:{DANGER};background:transparent;")

    def _run_plugin_test(self, namespace, runner):
        self._save_plugin_settings(namespace)
        status = self._plugin_status_labels.get(namespace)
        if status:
            self._set_i18n_text(status, "Testing…")
        values = self._gather_plugin_settings(namespace)
        import threading
        def worker():
            try:
                result = runner(values)
                if isinstance(result, tuple) and len(result) == 2:
                    ok, message = bool(result[0]), str(result[1])
                else:
                    ok, message = bool(result), str(result)
            except Exception as exc:
                ok, message = False, str(exc)
            self.plugin_test_finished.emit(namespace, ok, message)
        threading.Thread(target=worker, daemon=True, name="jarvis-plugin-settings-test").start()

    def _on_plugin_test_finished(self, namespace, ok, message):
        status = self._plugin_status_labels.get(namespace)
        if status:
            self._set_i18n_text(status, message)
            status.setStyleSheet(f"color:{CYAN if ok else DANGER};background:transparent;")

    def _build_remote_panel(self, parent):
        frame, root = self._module_frame(
            parent, "Remote access",
            "Create a temporary pairing session to connect another device to this JARVIS installation."
        )
        result = self.win.on_remote_clicked() if self.win.on_remote_clicked else None
        if not result:
            card, body = self._section_card(root, "Dashboard unavailable")
            body.addWidget(self._status_label("The remote dashboard is not running or has not started yet. Start JARVIS again or enable its dashboard integration."))
            return frame
        url, secret = str(result[0]), str(result[1])
        auto = result[2] if len(result) >= 3 else ""
        manual = result[3] if len(result) >= 4 else url
        bind_error = result[4] if len(result) >= 5 else ""
        card, body = self._section_card(root, "Pairing session", "Use the temporary link or copy the access key to the other device.")
        if bind_error:
            warn = self._status_label(bind_error)
            warn.setStyleSheet(f"color:{DANGER};background:transparent;")
            body.addWidget(warn)
        link_input = QLineEdit(str(auto or manual))
        link_input.setReadOnly(True)
        self._field(body, "Connection link", link_input)
        secret_input = QLineEdit(secret)
        secret_input.setReadOnly(True)
        self._field(body, "Temporary access key", secret_input)
        buttons = QHBoxLayout()
        copy_link = self._action_button("COPY LINK", VIOLET)
        copy_link.clicked.connect(lambda: QApplication.clipboard().setText(link_input.text()))
        copy_key = self._action_button("COPY KEY", CYAN)
        copy_key.clicked.connect(lambda: QApplication.clipboard().setText(secret_input.text()))
        buttons.addWidget(copy_link)
        buttons.addWidget(copy_key)
        buttons.addStretch(1)
        body.addLayout(buttons)
        note = self._status_label("Pairing keys expire automatically. Keep them private and only share with a device you control.")
        root.addWidget(note)
        return frame

    def _prepare_embedded_panel(self, panel):
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        panel.setMinimumWidth(0)
        panel.setMaximumWidth(16777215)
        panel.setMinimumHeight(0)
        panel.setMaximumHeight(16777215)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        # Panels were designed as independent floating windows. In the workspace
        # they become content modules, so the parent stylesheet owns their surface.
        panel.setStyleSheet(f"""
            QWidget {{ color:{TEXT}; }}
            QLineEdit, QTextEdit, QPlainTextEdit {{
                color:{TEXT}; background:#101a32; border:1px solid rgba(108,128,190,120);
                border-radius:9px; padding:8px; selection-background-color:#6158b8;
            }}
            QComboBox {{
                color:{TEXT}; background:#101a32; border:1px solid rgba(108,128,190,120);
                border-radius:9px; padding:7px 10px; min-height:20px;
            }}
            QComboBox QAbstractItemView {{ color:{TEXT}; background:#101a32;
                selection-background-color:#50479b; border:1px solid {LINE}; }}
            QPushButton {{
                color:{TEXT}; background:#182341; border:1px solid rgba(126,112,255,140);
                border-radius:9px; padding:7px 12px; font-weight:700;
            }}
            QPushButton:hover {{ border-color:{CYAN}; background:#202c50; }}
            QScrollArea {{ background:transparent; border:0; }}
            QProgressBar {{ background:#101a32; border:1px solid {LINE}; border-radius:4px; }}
            QProgressBar::chunk {{ background:{CYAN}; border-radius:4px; }}
        """)
        # Reapply the new palette to controls that carry their own legacy inline
        # stylesheet. Secrets and stateful controls keep their original behavior.
        for control in panel.findChildren(QWidget):
            if isinstance(control, QLineEdit):
                control.setStyleSheet(
                    f"QLineEdit{{color:{TEXT};background:#101a32;border:1px solid rgba(108,128,190,120);"
                    "border-radius:9px;padding:8px;selection-background-color:#6158b8;}"
                    f"QLineEdit:focus{{border:1px solid {CYAN};}}")
            elif isinstance(control, QComboBox):
                control.setStyleSheet(
                    f"QComboBox{{color:{TEXT};background:#101a32;border:1px solid rgba(108,128,190,120);"
                    "border-radius:9px;padding:7px 10px;min-height:20px;}"
                    f"QComboBox QAbstractItemView{{color:{TEXT};background:#101a32;selection-background-color:#50479b;}}")
            elif isinstance(control, QPushButton):
                label = control.text().upper()
                primary = any(token in label for token in ("APPLY", "SAVE", "TEST", "CONFIRM"))
                accent = CYAN if primary else VIOLET
                control.setStyleSheet(
                    f"QPushButton{{color:{TEXT};background:{'#26315a' if primary else '#182341'};"
                    f"border:1px solid {accent};border-radius:9px;padding:7px 12px;font-weight:700;}}"
                    f"QPushButton:hover{{background:#202c50;border-color:{CYAN};}}"
                    "QPushButton:disabled{color:#59627e;border-color:#333d59;}")
            elif isinstance(control, QLabel):
                # Override only the color, keeping alignment, font and wrapping.
                control.setStyleSheet(control.styleSheet().replace("#00d4ff", VIOLET))
        panel.adjustSize()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self.embedded:
                self._close()
            else:
                self.set_page("overview")
            event.accept()
            return
        super().keyPressEvent(event)
