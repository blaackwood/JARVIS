"""Read-only local health report for JARVIS."""
from __future__ import annotations


def jarvis_health(parameters: dict, player=None) -> str:
    from core.healthcheck import collect_health, format_health
    scope = str((parameters or {}).get("scope") or "summary").strip().lower()
    full = scope == "full"
    snapshot = collect_health(probe_services=full, include_runtime=True)
    return format_health(snapshot, compact=not full)


TOOL = {
    "name": "jarvis_health",
    "description": (
        "Run a local, read-only health check of JARVIS. Use scope='summary' for a short "
        "status, or scope='full' for memory integrity, task queue/checkpoints, agent profiles, "
        "Windows auto-start, configured cloud providers, local speech input and system memory. "
        "This tool never repairs, restarts, changes settings, or displays API keys, tokens, "
        "private task text, or command lines."
    ),
    "brief": "Read-only JARVIS diagnostics: memory, tasks, agents, startup and local services.",
    "tier": "core",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "scope": {
                "type": "STRING",
                "enum": ["summary", "full"],
                "description": "summary for key status only; full for all local checks",
            },
        },
        "required": [],
    },
    "handler": jarvis_health,
}
