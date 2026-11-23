"""Search JARVIS's persistent local conversation archive."""
from __future__ import annotations

from memory.conversation_history import search_messages


def search_conversation_history(parameters: dict, player=None, speak=None) -> str:
    params = parameters or {}
    query = " ".join(str(params.get("query", "")).split()).strip()
    if not query:
        return "QUERY_REQUIRED: provide a topic, phrase, project name or decision to search."
    if len(query) > 160:
        return "QUERY_TOO_LONG: keep the search phrase under 160 characters."
    try:
        limit = max(1, min(12, int(params.get("limit", 8))))
    except (TypeError, ValueError):
        limit = 8
    rows = search_messages(query, limit=limit)
    if not rows:
        return f"NO_MATCHES: no archived conversation turns matched {query!r}."
    lines = [f"ARCHIVED_CONVERSATION_RESULTS: {len(rows)} matching turn(s) for {query!r}."]
    for row in rows:
        timestamp = str(row.get("timestamp", ""))[:19].replace("T", " ")
        speaker = "User" if row.get("speaker") == "user" else "JARVIS"
        text = " ".join(str(row.get("text", "")).split())
        lines.append(f"[{timestamp}] {speaker}: {text[:900]}")
    return "\n".join(lines)


TOOL = {
    "name": "search_conversation_history",
    "description": (
        "Search the full local archive of past JARVIS conversations by exact phrase, "
        "project, decision, person or topic. Use this whenever the user refers to "
        "a previous chat, says 'we discussed this before', asks what was decided, "
        "or expects continuity beyond the recent context already shown. Do not claim "
        "you have no memory until you search. Returns matching original user and "
        "assistant turns in chronological order. Local archive only; credentials "
        "are redacted before storage."
    ),
    "brief": "Search old JARVIS conversations by keyword or phrase and retrieve original turns.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "Topic or phrase to search in past conversations"},
            "limit": {"type": "INTEGER", "description": "Maximum matching turns, 1 to 12; default 8"},
        },
        "required": ["query"],
    },
    "handler": search_conversation_history,
}
