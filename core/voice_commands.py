"""Narrow, explicit voice-command parsing for local microphone controls.

Only address-prefixed imperatives are accepted. This avoids muting on ordinary
conversation such as asking how to mute a microphone.
"""
from __future__ import annotations

import re
import unicodedata


_PATTERNS = tuple(re.compile(pattern) for pattern in (
    r"^(?:hey )?jarvis (?:(?:por favor|pode) )?(?:mutar|muta|mute|silenciar|silencia|silencie|desligar|desliga|desligue|desativar|desative) (?:o )?(?:meu )?(?:microfone|mic)$",
    r"^(?:hey )?jarvis (?:(?:por favor|pode) )?(?:coloca|coloque|bota|bote) (?:o )?(?:meu )?(?:microfone|mic) (?:no )?mudo$",
    r"^(?:hey )?jarvis (?:o )?(?:meu )?(?:microfone|mic) (?:no )?mudo$",
    r"^(?:hey )?jarvis (?:please )?mute (?:the )?(?:my )?(?:microphone|mic)$",
    r"^(?:hey )?jarvis (?:please )?turn off (?:the )?(?:microphone|mic)$",
))


def normalize_voice_command(text: str) -> str:
    """Normalize accents and punctuation while retaining word order."""
    value = unicodedata.normalize("NFKD", str(text or "").casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def is_microphone_mute_command(text: str) -> bool:
    """True only for a short, explicit command addressed to JARVIS."""
    normalized = normalize_voice_command(text)
    return bool(normalized and any(pattern.fullmatch(normalized) for pattern in _PATTERNS))
