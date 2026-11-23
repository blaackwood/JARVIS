"""Search durable JARVIS memory semantically across facts, projects, tasks and events."""
from __future__ import annotations

from memory.semantic_index import search_semantic_memory


def search_semantic_memory_action(parameters: dict, player=None, speak=None) -> str:
    params = parameters or {}
    query = " ".join(str(params.get("query", "")).split()).strip()
    if not query:
        return "QUERY_REQUIRED: provide a topic, project, person, task or event."
    try:
        limit = max(1, min(10, int(params.get("limit", 6))))
    except (TypeError, ValueError):
        limit = 6
    return search_semantic_memory(query, limit=limit)


TOOL = {
    "name": "search_semantic_memory",
    "description": (
        "Search durable memory by meaning and related entities across personal facts, "
        "projects, tasks and session events. Use when the user refers to an older "
        "project, person, decision, blocker, task or event that is not already in context. "
        "For exact wording from an old conversation, use search_conversation_history instead. "
        "This index excludes raw conversation turns and credential-like content."
    ),
    "brief": "Search remembered facts, projects, people, tasks and events with related links.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "Topic, name, project, task or event to search"},
            "limit": {"type": "INTEGER", "description": "Maximum results, 1 to 10; default 6"},
        },
        "required": ["query"],
    },
    "handler": search_semantic_memory_action,
}
