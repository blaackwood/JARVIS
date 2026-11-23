"""Persistent, per-project working memory for Jarvis.

Project records are kept separate from personal facts in memory/long_term.json.
Only explicit project updates are written; this module never infers progress.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from threading import RLock

from memory.memory_manager import BASE_DIR

PROJECTS_DIR = BASE_DIR / "memory" / "projects"
_LOCK = RLock()
_FIELDS = ("decisions", "blockers", "next_steps", "notes")
_MAX_ITEMS = 40
_MAX_TEXT = 700


def _slug(name: str) -> str:
    raw = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(name or "").strip().lower())
    raw = re.sub(r"-+", "-", raw).strip("-_")
    if not raw:
        raise ValueError("Project name is required.")
    return raw[:64]


def _path(name: str) -> Path:
    return PROJECTS_DIR / f"{_slug(name)}.json"


def _clean_items(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        raise ValueError("Project notes must be text or a list of text.")
    result = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text[:_MAX_TEXT])
    return result


def get_project(name: str) -> dict | None:
    path = _path(name)
    with _LOCK:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except (OSError, json.JSONDecodeError):
            return None


def update_project(name: str, *, status: str | None = None,
                   decisions=None, blockers=None, next_steps=None,
                   notes=None) -> dict:
    """Create/update a project record. Lists append unique entries."""
    path = _path(name)
    with _LOCK:
        data = get_project(name) or {
            "name": str(name).strip()[:100],
            "status": "",
            "decisions": [],
            "blockers": [],
            "next_steps": [],
            "notes": [],
            "created": datetime.now().isoformat(timespec="seconds"),
        }
        if status is not None and str(status).strip():
            data["status"] = str(status).strip()[:_MAX_TEXT]
        for field in _FIELDS:
            incoming = _clean_items(locals()[field])
            existing = data.setdefault(field, [])
            for item in incoming:
                if item not in existing:
                    existing.append(item)
            data[field] = existing[-_MAX_ITEMS:]
        data["updated"] = datetime.now().isoformat(timespec="seconds")
        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
        return data


def list_projects() -> list[dict]:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in PROJECTS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                rows.append(data)
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(rows, key=lambda row: row.get("updated", ""), reverse=True)


def format_project_for_prompt(project: dict, max_chars: int = 1200) -> str:
    lines = [f"Project: {project.get('name', 'Unnamed')}"]
    if project.get("status"):
        lines.append(f"Status: {project['status']}")
    for field, label in (("decisions", "Decisions"), ("blockers", "Blockers"),
                         ("next_steps", "Next steps"), ("notes", "Notes")):
        items = project.get(field) or []
        if items:
            lines.append(f"{label}:")
            lines.extend(f"- {str(item)[:_MAX_TEXT]}" for item in items[-5:])
    text = "\n".join(lines)
    return text[:max_chars]


def search_projects(query: str = "", limit: int = 5) -> str:
    """Rank project records by name and by the fields most useful for current work."""
    projects = list_projects()
    raw_query = str(query or "").strip().casefold()
    stop_words = {"para", "com", "uma", "uns", "das", "dos", "que", "por", "the", "and", "for"}
    words = [
        word for word in re.split(r"[^\w]+", raw_query)
        if len(word) > 2 and word not in stop_words
    ]
    if words:
        def score(project):
            name = str(project.get("name", "")).casefold()
            status = str(project.get("status", "")).casefold()
            weighted = {
                "name": name,
                "status": status,
                "decisions": " ".join(project.get("decisions") or []).casefold(),
                "blockers": " ".join(project.get("blockers") or []).casefold(),
                "next_steps": " ".join(project.get("next_steps") or []).casefold(),
                "notes": " ".join(project.get("notes") or []).casefold(),
            }
            total = 20 if raw_query and raw_query in name else 0
            for word in words:
                if word in name:
                    total += 12
                if word in status:
                    total += 6
                if word in weighted["decisions"]:
                    total += 4
                if word in weighted["blockers"]:
                    total += 4
                if word in weighted["next_steps"]:
                    total += 3
                if word in weighted["notes"]:
                    total += 1
            return total
        ranked = [(score(project), project) for project in projects]
        projects = [project for points, project in ranked if points > 0]
        projects.sort(key=lambda project: (score(project), project.get("updated", "")), reverse=True)
    if not projects:
        return "No project records found." if query else "No projects have been recorded yet."
    return "\n\n".join(format_project_for_prompt(p) for p in projects[:max(1, limit)])


def save_session_summary_for_projects(conversation: str, summary: str) -> list[str]:
    """Attach a factual session summary as a note to projects explicitly mentioned."""
    conversation = str(conversation or "").casefold()
    summary = str(summary or "").strip()
    if not conversation or not summary:
        return []
    stamp = datetime.now().strftime("%Y-%m-%d")
    updated = []
    for project in list_projects():
        name = str(project.get("name", "")).strip()
        if len(name) < 3 or name.casefold() not in conversation:
            continue
        note = f"Session summary ({stamp}): {summary[:_MAX_TEXT]}"
        update_project(name, notes=[note])
        updated.append(name)
    return updated
