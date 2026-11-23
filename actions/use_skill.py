"""Expose installed Agent Skills to JARVIS on demand."""
from core.skills import discover_skills, read_skill

TOOL = {
    "name": "use_skill",
    "description": (
        "Load the full instructions for one installed specialized skill. "
        "Use this BEFORE carrying out a task when it matches a skill listed in "
        "the system prompt (for example pdf, docx, xlsx, pptx, frontend-design, "
        "mcp-builder, skill-creator). Pass the exact skill slug. Returns its "
        "SKILL.md and the path to supporting resources. This reads instructions; "
        "it does not automatically execute scripts or install dependencies."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "skill_name": {
                "type": "STRING",
                "description": "Exact installed skill slug, e.g. pdf, docx, frontend-design, mcp-builder."
            }
        },
        "required": ["skill_name"]
    },
    "handler": lambda parameters: _load(parameters),
}


def _load(parameters):
    name = str((parameters or {}).get("skill_name") or "").strip()
    return read_skill(name)
