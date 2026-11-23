"""Local semantic index for durable facts, projects, tasks and session events.

Uses SQLite FTS5 (Unicode/diacritic aware) plus explicit "mentions" edges.
Raw conversation turns are intentionally left in the separate conversation archive.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from memory.memory_manager import BASE_DIR, _SECRET_PATTERNS

MEMORY_DIR = BASE_DIR / "memory"
LONG_TERM_PATH = MEMORY_DIR / "long_term.json"
PROJECTS_DIR = MEMORY_DIR / "projects"
TASKS_DIR = MEMORY_DIR / "tasks"
DB_PATH = MEMORY_DIR / "semantic_index.sqlite3"
_SECRET_KEY = re.compile(r"(?i)(password|passwd|senha|api[_ -]?key|token|secret|credential)")
_WORDS = re.compile(r"[\w-]+", re.UNICODE)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")
    return slug[:80] or hashlib.sha1(str(value).encode("utf-8", "replace")).hexdigest()[:12]


def _normalize(value: str) -> str:
    return " ".join(_WORDS.findall(str(value or "").casefold()))


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _flatten(value, depth: int = 0) -> str:
    if depth > 4 or value is None:
        return ""
    if isinstance(value, dict):
        parts = []
        for key, child in value.items():
            if _SECRET_KEY.search(str(key)):
                continue
            rendered = _flatten(child, depth + 1)
            if rendered:
                parts.append(f"{key}: {rendered}")
        return " | ".join(parts)
    if isinstance(value, (list, tuple)):
        return " | ".join(part for item in value if (part := _flatten(item, depth + 1)))
    return str(value).strip()[:1800]


def _safe_body(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if any(pattern.search(text) for pattern in _SECRET_PATTERNS):
        return ""
    return text[:12000]


def _source_paths() -> list[Path]:
    paths = [LONG_TERM_PATH]
    if PROJECTS_DIR.exists():
        paths.extend(sorted(PROJECTS_DIR.glob("*.json")))
    if TASKS_DIR.exists():
        paths.extend(
            p for p in sorted(TASKS_DIR.glob("*.json"))
            if ".turns." not in p.name and not p.name.endswith(".turns.json")
        )
    return paths


def _fingerprint(paths: list[Path]) -> str:
    state = []
    for path in paths:
        try:
            stat = path.stat()
            state.append((str(path), stat.st_mtime_ns, stat.st_size))
        except OSError:
            state.append((str(path), 0, 0))
    raw = json.dumps(state, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _collect():
    docs: dict[str, dict] = {}
    entities: dict[str, dict] = {}
    relations: set[tuple[str, str, str, str]] = set()

    def add(entity_id: str, entity_type: str, name: str, body: str, source_id: str):
        raw_name = str(name or "").strip()
        safe_name = _safe_body(raw_name)
        body = _safe_body(body)
        if raw_name and not safe_name:
            return
        if not body and not safe_name:
            return
        safe_name = safe_name[:160] or entity_id
        entities[entity_id] = {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "name": safe_name,
            "source_id": source_id,
        }
        existing = docs.get(entity_id)
        if existing:
            if body and body not in existing["body"]:
                existing["body"] = (existing["body"] + "\n" + body)[:16000]
        else:
            docs[entity_id] = {
                "doc_id": entity_id,
                "kind": entity_type,
                "title": safe_name,
                "body": body[:12000],
            }

    # Durable personal facts and recent session summaries.
    memory = _read_json(LONG_TERM_PATH) or {}
    if isinstance(memory, dict):
        for category, items in memory.items():
            if category == "sessions" and isinstance(items, list):
                for index, item in enumerate(items):
                    if not isinstance(item, dict):
                        continue
                    summary = str(item.get("summary", "")).strip()
                    if not summary:
                        continue
                    event_key = item.get("id") or f"{item.get('date', 'undated')}-{index}"
                    event_id = f"event:{_slug(event_key)}"
                    title = f"Session {item.get('date', '')}".strip()
                    add(event_id, "event", title, summary, "long_term.json")
                continue
            if not isinstance(items, dict):
                continue
            for key, entry in items.items():
                value = entry.get("value", "") if isinstance(entry, dict) else entry
                value = str(value or "").strip()
                if not value:
                    continue
                if category == "relationships":
                    entity_type, entity_id = "person", f"person:{_slug(key)}"
                elif category == "projects":
                    entity_type, entity_id = "project", f"project:{_slug(key)}"
                else:
                    entity_type, entity_id = "fact", f"fact:{category}:{_slug(key)}"
                add(entity_id, entity_type, str(key), value, "long_term.json")

    # Structured project records.
    project_names: dict[str, str] = {}
    if PROJECTS_DIR.exists():
        for path in sorted(PROJECTS_DIR.glob("*.json")):
            data = _read_json(path)
            if not isinstance(data, dict):
                continue
            name = str(data.get("name") or path.stem).strip()
            if not name:
                continue
            project_id = f"project:{_slug(name)}"
            body = _flatten({
                "status": data.get("status"),
                "decisions": data.get("decisions"),
                "blockers": data.get("blockers"),
                "next_steps": data.get("next_steps"),
                "notes": data.get("notes"),
            })
            add(project_id, "project", name, body, path.name)
            project_names[project_id] = name

    # Completed, active and cancelled task records; turn transcripts are not indexed.
    if TASKS_DIR.exists():
        for path in sorted(TASKS_DIR.glob("*.json")):
            if ".turns." in path.name or path.name.endswith(".turns.json"):
                continue
            data = _read_json(path)
            if not isinstance(data, dict) or not (data.get("title") or data.get("task")):
                continue
            task_id = str(data.get("id") or path.stem)
            title = str(data.get("title") or data.get("task") or task_id)
            body = _flatten({
                "task": data.get("task"),
                "status": data.get("status"),
                "result": data.get("result"),
                "wrap_up": data.get("wrap_up"),
                "notes": data.get("notes_in"),
                "events": data.get("events"),
            })
            task_entity_id = f"task:{_slug(task_id)}"
            add(task_entity_id, "task", title, body, path.name)

    # Link documents to named people/projects only when the name appears in the source text.
    link_targets = [
        entity for entity in entities.values()
        if entity["entity_type"] in {"project", "person"} and len(_normalize(entity["name"])) >= 3
    ]
    for doc_id, doc in docs.items():
        body_norm = _normalize(doc["title"] + " " + doc["body"])
        for target in link_targets:
            if target["entity_id"] == doc_id:
                continue
            name_norm = _normalize(target["name"])
            if name_norm and name_norm in body_norm:
                edge_type = "MENTIONS_PROJECT" if target["entity_type"] == "project" else "MENTIONS_PERSON"
                relations.add((doc_id, target["entity_id"], edge_type, doc_id))

    return list(docs.values()), list(entities.values()), sorted(relations)


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=8)
    conn.execute("PRAGMA busy_timeout=8000")
    return conn


@contextmanager
def _db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _ensure_schema(conn: sqlite3.Connection):
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS semantic_fts USING "
        "fts5(doc_id UNINDEXED, kind, title, body, "
        "tokenize='unicode61 remove_diacritics 2')"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS semantic_entities ("
        "entity_id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, "
        "name TEXT NOT NULL, source_id TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS semantic_relations ("
        "from_id TEXT NOT NULL, to_id TEXT NOT NULL, relation_type TEXT NOT NULL, "
        "source_id TEXT NOT NULL, UNIQUE(from_id,to_id,relation_type,source_id))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS semantic_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )


def refresh_semantic_index(force: bool = False) -> dict:
    paths = _source_paths()
    fingerprint = _fingerprint(paths)
    with _db() as conn:
        _ensure_schema(conn)
        row = conn.execute("SELECT value FROM semantic_meta WHERE key='fingerprint'").fetchone()
        if not force and row and row[0] == fingerprint:
            return {
                "updated": False,
                "documents": conn.execute("SELECT count(*) FROM semantic_fts").fetchone()[0],
                "entities": conn.execute("SELECT count(*) FROM semantic_entities").fetchone()[0],
                "relations": conn.execute("SELECT count(*) FROM semantic_relations").fetchone()[0],
            }
        docs, entities, relations = _collect()
        conn.execute("DELETE FROM semantic_fts")
        conn.execute("DELETE FROM semantic_entities")
        conn.execute("DELETE FROM semantic_relations")
        conn.executemany(
            "INSERT INTO semantic_fts(doc_id,kind,title,body) VALUES(?,?,?,?)",
            [(d["doc_id"], d["kind"], d["title"], d["body"]) for d in docs],
        )
        conn.executemany(
            "INSERT INTO semantic_entities(entity_id,entity_type,name,source_id) VALUES(?,?,?,?)",
            [(e["entity_id"], e["entity_type"], e["name"], e["source_id"]) for e in entities],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO semantic_relations(from_id,to_id,relation_type,source_id) VALUES(?,?,?,?)",
            relations,
        )
        conn.execute(
            "INSERT INTO semantic_meta(key,value) VALUES('fingerprint',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (fingerprint,),
        )
        return {"updated": True, "documents": len(docs), "entities": len(entities), "relations": len(relations)}


def search_semantic_memory(query: str, limit: int = 6) -> str:
    query = " ".join(str(query or "").split()).strip()
    if not query:
        return "QUERY_REQUIRED: provide a topic, project, person, task or event."
    tokens = _WORDS.findall(query)
    if not tokens:
        return "QUERY_REQUIRED: no searchable words were found."
    match = " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens[:12])
    limit = max(1, min(10, int(limit)))
    refresh_semantic_index()
    try:
        with _db() as conn:
            rows = conn.execute(
                "SELECT doc_id,kind,title,snippet(semantic_fts,3,'[',']','…',18) "
                "FROM semantic_fts WHERE semantic_fts MATCH ? "
                "ORDER BY bm25(semantic_fts,0.0,0.5,2.0,1.0) LIMIT ?",
                (match, limit),
            ).fetchall()
            if not rows:
                return f"NO_SEMANTIC_MATCHES: nothing relevant found for {query!r}."
            lines = [f"SEMANTIC_MEMORY_RESULTS: {len(rows)} result(s) for {query!r}."]
            for doc_id, kind, title, excerpt in rows:
                lines.append(f"\n[{kind}] {title}: {excerpt}")
                related = conn.execute(
                    "SELECT e.entity_type,e.name,r.relation_type "
                    "FROM semantic_relations r JOIN semantic_entities e "
                    "ON e.entity_id=CASE WHEN r.from_id=? THEN r.to_id ELSE r.from_id END "
                    "WHERE r.from_id=? OR r.to_id=? LIMIT 4",
                    (doc_id, doc_id, doc_id),
                ).fetchall()
                if related:
                    lines.append("  Related: " + "; ".join(
                        f"{name} ({relation.lower().replace('_', ' ')})"
                        for _type, name, relation in related
                    ))
            return "\n".join(lines)
    except sqlite3.OperationalError as exc:
        return f"SEMANTIC_INDEX_ERROR: {exc}"
