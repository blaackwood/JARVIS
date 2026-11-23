"""Native JARVIS presentation for the engine/provider control plane.

Provider discovery, credential handling, model refresh, probes, persistence
and reconnect signals remain owned by ProvidersOverlay. This class supplies a
separate layout designed for the JARVIS System Workspace rather than inheriting
the old floating-window geometry.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QLabel, QPushButton, QLineEdit, QComboBox, QFrame, QScrollArea,
    QGridLayout, QWidget, QSizePolicy,
)

from gui.providers_panel import ProvidersOverlay as _LegacyProvidersOverlay


class ProvidersHoloOverlay(_LegacyProvidersOverlay):
    """Same provider engine, new workspace-native presentation."""

    def _rebuild_body(self) -> None:
        """Build service stages as a responsive grid, not the legacy long form."""
        if not hasattr(self, "_body_lay"):
            return super()._rebuild_body()

        self._remember_edits()
        self._clear(self._body_lay)
        self._edits.clear()
        self._status.clear()

        board = QWidget(self._body)
        board.setObjectName("EngineRoutingBoard")
        board.setStyleSheet("QWidget#EngineRoutingBoard{background:transparent;border:0;}")
        grid = QGridLayout(board)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        if self._mode == "pipeline":
            slots = (
                ("stt", "①", "HEARING", "Turns your speech into words"),
                ("llm", "②", "REASONING", "Understands, decides and uses tools"),
                ("tts", "③", "SPEAKING", "Turns the answer into natural voice"),
            )
            slot_widgets = [
                self._slot_box(slot, num, name, what)
                for slot, num, name, what in slots
            ]
            for widget in slot_widgets:
                widget.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            grid.addWidget(slot_widgets[0], 0, 0)
            grid.addWidget(slot_widgets[1], 0, 1)
            grid.addWidget(slot_widgets[2], 1, 0, 1, 2)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            sidecar_row = 2
        else:
            card = QFrame()
            card.setObjectName("EngineModeSummary")
            card.setStyleSheet(
                "QFrame#EngineModeSummary{background:rgba(42,57,102,75);"
                "border:1px solid rgba(90,222,220,100);border-radius:13px;}")
            from PyQt6.QtWidgets import QVBoxLayout
            summary = QVBoxLayout(card)
            summary.setContentsMargins(16, 14, 16, 14)
            summary.setSpacing(6)
            title = QLabel("GEMINI LIVE  ·  ONE CONVERSATION ENGINE")
            title.setStyleSheet(
                "color:#6ce8df;background:transparent;font-size:10px;"
                "font-weight:800;letter-spacing:1px;")
            text = QLabel(
                "Your voice, the transcript, reasoning and spoken reply travel "
                "over one Live connection. No separate hearing or speaking "
                "provider is required in this mode.")
            text.setWordWrap(True)
            text.setStyleSheet(
                "color:#aebcdd;background:transparent;font-size:9px;")
            summary.addWidget(title)
            summary.addWidget(text)
            grid.addWidget(card, 0, 0, 1, 2)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            sidecar_row = 1

        sidecar = self._sidecar_box_widget()
        coding = self._coding_box_widget()
        sidecar.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        coding.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        grid.addWidget(sidecar, sidecar_row, 0, 1, 2)
        grid.addWidget(coding, sidecar_row + 1, 0, 1, 2)

        self._body_lay.addWidget(board)
        self._body_lay.addStretch(1)
        self._update_footer()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ProvidersHoloOverlay")
        self.setMinimumWidth(0)
        self.setMaximumWidth(860)
        self.setFixedWidth(860)
        self.setMinimumHeight(0)
        self.setMaximumHeight(16777215)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setStyleSheet("""
            QWidget#ProvidersHoloOverlay {
                background: rgba(7, 10, 27, 250);
                border: 1px solid rgba(111, 91, 255, 190);
                border-radius: 18px;
            }
            QLabel { color: #dce5ff; background: transparent; }
            QLineEdit, QComboBox {
                color: #eff4ff; background: rgba(19, 27, 55, 230);
                border: 1px solid rgba(89, 116, 190, 150);
                border-radius: 9px; padding: 8px 10px; min-height: 19px;
                selection-background-color: #6657d9;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #7e75ff;
                background: rgba(28, 34, 70, 245);
            }
            QComboBox::drop-down { border: 0; width: 28px; }
            QComboBox QAbstractItemView {
                color: #edf1ff; background: #111a35;
                selection-background-color: #5147a8;
                border: 1px solid #6559c8;
            }
            QScrollArea { background: transparent; border: 0; }
            QScrollBar:vertical { background: rgba(20,28,55,150); width: 8px; border-radius: 4px; }
            QScrollBar::handle:vertical { background: #6258bd; border-radius: 4px; min-height: 28px; }
            QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
            QFrame { background: transparent; }
        """)

        outer = self.layout()
        if outer is not None:
            outer.setContentsMargins(16, 14, 16, 14)
            outer.setSpacing(10)

        headings = self.findChildren(QLabel)
        # These are the two root headings created before any provider cards.
        # Find by their current text instead of relying on QObject child order.
        for label in headings:
            if "ENGINE  &  PROVIDERS" in label.text():
                label.setText("JARVIS  /  ENGINE CORE")
                label.setStyleSheet(
                    "color:#b9aaff;background:transparent;font-size:17px;"
                    "font-weight:800;letter-spacing:2px;padding:3px 2px;")
            elif label.text().startswith("Choose what powers"):
                label.setText(
                    "ROUTING  ·  HEARING  ·  REASONING  ·  SPEAKING  ·  BACKGROUND TASKS")
                label.setStyleSheet(
                    "color:#7f94c9;background:transparent;font-size:8px;"
                    "letter-spacing:1.4px;padding:0 3px 5px 3px;")

        for card in (self._card_gemini, self._card_local):
            card.setMinimumHeight(82)
            card.setMaximumHeight(104)
            card.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            card.setStyleSheet("""
                QPushButton {
                    text-align:left; padding:12px 14px;
                    color:#dfe8ff; background:rgba(25,32,66,210);
                    border:1px solid rgba(104,119,190,130);
                    border-radius:12px; font-size:9px;
                }
                QPushButton:checked {
                    color:#ffffff; background:rgba(74,58,150,105);
                    border:1px solid #8b7cff;
                }
                QPushButton:hover { border:1px solid #58e5df; }
            """)

        self._footer.setStyleSheet(
            "color:#8ca5d8;background:rgba(16,23,49,180);"
            "border:1px solid rgba(85,107,170,90);border-radius:10px;"
            "padding:9px;font-size:8px;")

        for button in self.findChildren(QPushButton):
            if button in (self._card_gemini, self._card_local):
                continue
            label = button.text().upper()
            primary = ("SAVE" in label or "APPLY" in label or label == "TEST")
            button.setMinimumHeight(max(32, button.minimumHeight()))
            button.setStyleSheet("""
                QPushButton {
                    color:#e9edff; background:rgba(45,48,103,190);
                    border:1px solid rgba(126,116,232,170);
                    border-radius:9px; padding:8px 13px;
                    font-weight:700; letter-spacing:.4px;
                }
                QPushButton:hover {
                    color:white; background:rgba(80,72,165,220);
                    border:1px solid #5ce4dc;
                }
                QPushButton:pressed { background:rgba(36,91,111,230); }
            """ if primary else """
                QPushButton {
                    color:#b9c8ef; background:rgba(18,28,55,210);
                    border:1px solid rgba(75,103,163,130);
                    border-radius:9px; padding:7px 12px;
                }
                QPushButton:hover { color:white; border:1px solid #5ce4dc; }
            """)

        self._scroll.setMinimumHeight(300)
        self._scroll.setMaximumHeight(390)
        self._body_lay.setSpacing(12)
        self._body_lay.setContentsMargins(2, 6, 10, 8)
        self._rebuild_body()


# gui.window retains the historic import name; point it at the new surface.
ProvidersOverlay = ProvidersHoloOverlay
