"""Persistent local conversation archive for JARVIS.

Stores user/assistant text turns as append-only JSONL so a process crash or
Live-session reconnect cannot erase the conversation. This is separate from
long_term.json: the latter stores durable facts; this archive stores dialogue.
"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from memory.memory_manager import get_base_dir

_ARCHIVE = get_base_dir() / "memory" / "conversations" / "history.jsonl"
_LOCK = threading.RLock()
_SECRET_VALUE = re.compile(
    r"(?i)(\b(?:password|passwd|senha|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|secret)\b\s*[:=]\s*)([^\s,;]+)"
)


_VISUAL_ERROR_TALK = re.compile(
    r"(?is)((desculp|erro|falha|problema|n[aã]o consegui).{0,80}(visualiza|diagrama|tela|desenho)"
    r"|(visualiza|diagrama|desenho).{0,80}(erro|falha|problema))")


def _safe_text(text: str) -> str:
    value = str(text or "").strip()
    return _SECRET_VALUE.sub(r"\1[REDACTED]", value)


def append_message(session_id: str, speaker: str, text: str) -> bool:
    """Durably append one plain-text conversation turn. Returns False if empty."""
    session_id = str(session_id or "").strip()
    speaker = str(speaker or "").strip().lower()
    value = _safe_text(text)
    if not session_id or speaker not in {"user", "assistant"} or not value:
        return False
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "speaker": speaker,
        "text": value,
    }
    encoded = json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
    with _LOCK:
        _ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
        with _ARCHIVE.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
            stream.flush()
            try:
                import os
                os.fsync(stream.fileno())
            except OSError:
                pass
    return True


def recent_messages(limit: int = 12, *, include_session_id: str | None = None) -> list[dict]:
    """Return recent messages, newest-first on disk but chronological to caller."""
    try:
        with _LOCK:
            if not _ARCHIVE.exists():
                return []
            rows = []
            with _ARCHIVE.open("r", encoding="utf-8") as stream:
                for line in stream:
                    try:
                        row = json.loads(line)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if not isinstance(row, dict):
                        continue
                    if include_session_id is not None and row.get("session_id") != include_session_id:
                        continue
                    if row.get("speaker") in {"user", "assistant"} and row.get("text"):
                        rows.append(row)
            return rows[-max(1, int(limit)):]
    except OSError as exc:
        print(f"[History] archive read failed: {exc}")
        return []


def search_messages(query: str, limit: int = 12) -> list[dict]:
    """Search all archived turns by case-insensitive literal phrase."""
    needle = " ".join(str(query or "").casefold().split())
    if not needle:
        return []
    try:
        with _LOCK:
            if not _ARCHIVE.exists():
                return []
            hits = []
            with _ARCHIVE.open("r", encoding="utf-8") as stream:
                for line in stream:
                    try:
                        row = json.loads(line)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if not isinstance(row, dict):
                        continue
                    text = " ".join(str(row.get("text", "")).casefold().split())
                    if needle in text:
                        hits.append(row)
            return hits[-max(1, int(limit)):]
    except OSError as exc:
        print(f"[History] archive search failed: {exc}")
        return []


def format_recent_context(limit: int = 8, *, current_session_id: str | None = None,
                          include_current: bool = False) -> str:
    """Compact prior dialogue for a fresh/rebuilt model context."""
    rows = recent_messages(max(int(limit) * 3, 12),
                           include_session_id=current_session_id if include_current else None)
    # Old apologies about visual errors make the model repeat them instead of
    # calling the visual tool, so they never go back into a fresh context.
    rows = [r for r in rows if not (
        r.get("speaker") == "assistant"
        and _VISUAL_ERROR_TALK.search(str(r.get("text", ""))))][-max(1, int(limit)):]
    if not rows:
        return ""
    lines = [
        "[RECENT CONVERSATION HISTORY — saved locally from earlier turns. Treat as context,",
        "not as a new request. Continue naturally; do not repeat answers already given.]",
    ]
    for row in rows:
        who = "User" if row.get("speaker") == "user" else "JARVIS"
        stamp = str(row.get("timestamp", ""))[:16].replace("T", " ")
        text = " ".join(str(row.get("text", "")).split())
        if text:
            lines.append(f"{stamp} {who}: {text[:700]}")
    return "\n".join(lines)
