import json
import os
import re
import tempfile
from datetime import datetime
from threading import RLock
from pathlib import Path
import sys


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR         = get_base_dir()
MEMORY_PATH      = BASE_DIR / "memory" / "long_term.json"
_lock            = RLock()
MAX_VALUE_LENGTH = 380

# ── Why there are two very different numbers here ────────────────────────────
#
# There used to be one: MEMORY_MAX_CHARS = 2200, applied to the whole store. It
# was a *storage* limit, and it existed only because the entire memory was
# pasted into the system prompt on every connect — so growing the memory grew
# every single request. When it filled, _trim_to_limit() deleted the oldest
# entries and printed one line to a console nobody reads. A memory described as
# "deeply remembers projects, preferences and personal context" was in practice
# two pages long, and quietly forgot your sister's name after a few weeks.
#
# Storage and prompt budget are now separate concerns:
#
#   MEMORY_MAX_CHARS  — a runaway guard, not a feature limit. Nothing normal
#                       reaches it; a bug writing in a loop does.
#   PROMPT_CORE_CHARS — what actually rides in the system prompt every session.
#                       Smaller than the old whole-memory dump, so sessions
#                       start *faster* than before, not slower.
#
# Everything above the core stays on disk and is fetched on demand by the
# recall_memory tool — see search_memory() and format_memory_for_prompt().
MEMORY_MAX_CHARS  = 200_000
PROMPT_CORE_CHARS = 1800
PROMPT_INDEX_CHARS = 600
# Most entries any one category may contribute to the core block, so a person
# with forty stored preferences still gets their sister into the prompt.
PROMPT_MAX_PER_CATEGORY = 6

def _empty_memory() -> dict:
    return {
        "identity":      {},
        "preferences":   {},
        "projects":      {},
        "relationships": {},
        "wishes":        {},
        "notes":         {},
        "sessions":      [],
    }


def _complete_memory_shape(data: dict) -> dict:
    base = _empty_memory()
    for key in base:
        if key not in data:
            data[key] = [] if key == "sessions" else {}
    return data


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Write in the destination directory and replace atomically on Windows."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            Path(temp_name).unlink(missing_ok=True)
        except OSError:
            pass


def _write_memory_file(memory: dict) -> None:
    """Persist memory atomically, retaining the previous valid JSON as .bak."""
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    backup_path = MEMORY_PATH.with_suffix(MEMORY_PATH.suffix + ".bak")
    if MEMORY_PATH.exists():
        try:
            previous = MEMORY_PATH.read_bytes()
            parsed = json.loads(previous.decode("utf-8-sig"))
            if isinstance(parsed, dict):
                try:
                    _atomic_write_bytes(backup_path, previous)
                except OSError as backup_error:
                    print(f"[Memory] ⚠️ Backup write failed: {backup_error}")
        except (OSError, UnicodeError, json.JSONDecodeError):
            # A corrupt primary must never replace the last known-good backup.
            pass
    payload = json.dumps(memory, indent=2, ensure_ascii=False).encode("utf-8")
    _atomic_write_bytes(MEMORY_PATH, payload)


def load_memory() -> dict:
    with _lock:
        if MEMORY_PATH.exists():
            try:
                data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return _complete_memory_shape(data)
                print("[Memory] ⚠️ Primary memory has an invalid JSON shape.")
            except Exception as e:
                print(f"[Memory] ⚠️ Load error: {e}")

        backup_path = MEMORY_PATH.with_suffix(MEMORY_PATH.suffix + ".bak")
        if backup_path.exists():
            try:
                recovered = json.loads(backup_path.read_text(encoding="utf-8"))
                if isinstance(recovered, dict):
                    recovered = _complete_memory_shape(recovered)
                    print("[Memory] ♻️ Restoring memory from the last known-good backup.")
                    try:
                        _write_memory_file(recovered)
                    except OSError as restore_error:
                        print(f"[Memory] ⚠️ Automatic restore failed: {restore_error}")
                    return recovered
            except Exception as backup_error:
                print(f"[Memory] ⚠️ Backup recovery failed: {backup_error}")
        return _empty_memory()

def _all_entries(memory: dict) -> list[tuple]:
    entries = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if isinstance(entry, dict) and "value" in entry:
                entries.append((cat, key, entry))
    return entries


# Set by main.py so a trim can reach the activity log. Deleting something a
# person told you and mentioning it only on stdout is how a memory loses trust.
_trim_notifier = None


def set_trim_notifier(fn) -> None:
    """Register a callable(str) that surfaces trims to the user."""
    global _trim_notifier
    _trim_notifier = fn


def _trim_to_limit(memory: dict) -> dict:
    if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
        return memory
    entries = _all_entries(memory)
    entries.sort(key=lambda t: t[2].get("updated", "0000-00-00"))
    dropped = []
    for cat, key, _ in entries:
        if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
            break
        del memory[cat][key]
        dropped.append(f"{cat}/{key}")
        print(f"[Memory] 🗑️  Trimmed {cat}/{key}")
    if dropped and _trim_notifier:
        try:
            _trim_notifier(
                f"SYS: Memory full — forgot {len(dropped)} oldest entries "
                f"({', '.join(dropped[:3])}{'…' if len(dropped) > 3 else ''})"
            )
        except Exception:
            pass
    return memory

def save_memory(memory: dict) -> None:
    if not isinstance(memory, dict):
        return
    with _lock:
        memory = _trim_to_limit(memory)
        _write_memory_file(memory)


def _truncate_value(val: str) -> str:
    if isinstance(val, str) and len(val) > MAX_VALUE_LENGTH:
        return val[:MAX_VALUE_LENGTH].rstrip() + "…"
    return val


def _recursive_update(target: dict, updates: dict) -> bool:
    changed = False
    for key, value in updates.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, dict) and "value" not in value:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
                changed = True
            if _recursive_update(target[key], value):
                changed = True
        else:
            new_val  = _truncate_value(str(value["value"] if isinstance(value, dict) else value))
            entry    = {"value": new_val, "updated": datetime.now().strftime("%Y-%m-%d")}
            existing = target.get(key, {})
            if not isinstance(existing, dict) or existing.get("value") != new_val:
                target[key] = entry
                changed = True
    return changed


_VALID_CATEGORIES = {"identity", "preferences", "projects", "relationships", "wishes", "notes"}
_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,63}$")
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:password|passwd|senha|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|secret|bearer)\b\s*[:=]"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{25,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
)


def validate_memory_item(category: str, key: str, value: str) -> tuple[str, str, str]:
    """Validate a personal-memory write before it reaches disk."""
    category = str(category or "").strip().lower()
    key = str(key or "").strip()
    value = str(value or "").strip()
    if category not in _VALID_CATEGORIES:
        raise ValueError("Invalid memory category.")
    if not _KEY_RE.fullmatch(key):
        raise ValueError("Memory key must be a short name using letters, numbers, spaces, _ or -.")
    if not value:
        raise ValueError("Memory value cannot be empty.")
    if re.search(r"(?i)(password|passwd|senha|api[_ -]?key|token|secret|credential|senha)", key):
        raise ValueError("Credential-like memory keys are not allowed.")
    if len(value) > MAX_VALUE_LENGTH:
        raise ValueError(f"Memory value is too long (maximum {MAX_VALUE_LENGTH} characters).")
    if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
        raise ValueError("This looks like a credential, secret or payment-card number. It was not saved.")
    return category, key, value


def _normalize_fact(value: str) -> str:
    value = str(value or "").casefold()
    return " ".join(re.findall(r"\w+", value, flags=re.UNICODE))


def save_memory_item(category: str, key: str, value: str, *,
                     confirm_overwrite: bool = False,
                     confirm_duplicate: bool = False) -> dict:
    """Save one fact without silently overwriting conflicts or duplicating facts.

    Confirmation flags must only be set after the user explicitly approves the
    specific replacement or duplicate. Returns saved/already_stored/conflict/
    duplicate/possible_duplicate/rejected with a safe match reference.
    """
    category, key, value = validate_memory_item(category, key, value)
    wanted = _normalize_fact(value)
    with _lock:
        memory = load_memory()
        existing_category = memory.get(category, {})
        current = existing_category.get(key) if isinstance(existing_category, dict) else None
        current_value = _entry_value(current) if current is not None else ""

        if current_value:
            if _normalize_fact(current_value) == wanted:
                return {"status": "already_stored", "match": f"{category}/{key}"}
            if not confirm_overwrite:
                return {
                    "status": "conflict",
                    "match": f"{category}/{key}",
                    "existing_value": current_value,
                }

        for other_category, items in memory.items():
            if not isinstance(items, dict):
                continue
            for other_key, entry in items.items():
                if other_category == category and other_key == key:
                    continue
                other_value = _entry_value(entry)
                if not other_value:
                    continue
                normalized = _normalize_fact(other_value)
                if normalized == wanted:
                    if not confirm_duplicate:
                        return {
                            "status": "duplicate",
                            "match": f"{other_category}/{other_key}",
                        }
                elif len(wanted) >= 28 and len(normalized) >= 28:
                    from difflib import SequenceMatcher
                    if SequenceMatcher(None, wanted, normalized).ratio() >= 0.96:
                        if not confirm_duplicate:
                            return {
                                "status": "possible_duplicate",
                                "match": f"{other_category}/{other_key}",
                            }

        update = {category: {key: {"value": value}}}
        if _recursive_update(memory, update):
            save_memory(memory)
            return {"status": "saved", "match": f"{category}/{key}"}
        return {"status": "already_stored", "match": f"{category}/{key}"}


def update_memory(memory_update: dict) -> dict:
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()
    unknown = set(memory_update) - _VALID_CATEGORIES
    if unknown:
        raise ValueError("Invalid memory category: " + ", ".join(sorted(unknown)))
    # Validate the entire batch before changing anything; partial writes are unsafe.
    for category, items in memory_update.items():
        if not isinstance(items, dict):
            raise ValueError("Memory category must contain key/value pairs.")
        for key, entry in items.items():
            value = entry.get("value") if isinstance(entry, dict) else entry
            validate_memory_item(category, key, value)
    with _lock:
        memory = load_memory()
        if _recursive_update(memory, memory_update):
            save_memory(memory)
            print(f"[Memory] 💾 Saved categories: {list(memory_update.keys())}")
        return memory

def _entry_value(entry) -> str:
    """Accept both the {'value': ..., 'updated': ...} shape and a bare string,
    because early versions of the store wrote plain strings."""
    if isinstance(entry, dict):
        return str(entry.get("value", "") or "").strip()
    return str(entry or "").strip()


def _pretty(key: str) -> str:
    return key.replace("_", " ").strip()


# Identity is always in the prompt; these categories compete for the remaining
# budget by recency.
_CATEGORY_LABELS = {
    "preferences":   "Preferences",
    "projects":      "Active projects / goals",
    "relationships": "People in their life",
    "wishes":        "Wishes / plans",
    "notes":         "Notes",
}

_IDENTITY_FIELDS = ["name", "age", "birthday", "city", "job",
                    "language", "school", "nationality"]


def format_memory_for_prompt(memory: dict | None) -> str:
    """Build the memory block that goes into the system prompt.

    This used to dump everything. It now sends three things:

      1. IDENTITY  - always, in full. It is small, and it is wrong for the
         assistant to have to look up your name.
      2. RECENT    - the most recently updated entries from every other
         category, up to PROMPT_CORE_CHARS. Recency is the cheapest useful
         relevance signal available without embeddings.
      3. AN INDEX  - the *keys* of everything else, values omitted.

    Point 3 is what makes recall work at all. A model cannot decide to look
    something up if it does not know the thing exists: with only points 1 and 2,
    "who is Ayse?" would get "I don't know" while ayse_sister sat on disk
    unread. The index costs a few hundred characters and turns recall from a
    gamble into a lookup.

    Net effect on latency: this block is SMALLER than the old full dump, so
    every session connects with fewer tokens. Occasionally the model spends one
    extra round trip on recall_memory - covered by the acknowledgment it
    already speaks before any slow step."""
    if not memory:
        return ""

    core_lines: list[str] = []

    # Recent session summaries provide continuity across separate Gemini Live sessions.
    # They are historical context, not proof that a task remains current.
    sessions = memory.get("sessions", [])
    if isinstance(sessions, list) and sessions:
        recent = [item for item in sessions[-_SESSION_PROMPT_MAX:] if isinstance(item, dict) and item.get("summary")]
        if recent:
            core_lines.append("[RECENT SESSION CONTEXT — historical; verify current status before assuming anything is still ongoing]")
            for item in recent:
                date = str(item.get("date", "")).strip()
                summary = str(item.get("summary", "")).strip()
                if summary:
                    core_lines.append(f"  - {date}: {summary[:280]}")

    # 1. Identity - always, in full
    identity = memory.get("identity", {}) or {}
    for field in _IDENTITY_FIELDS:
        val = _entry_value(identity.get(field))
        if not val:
            continue
        if field == "language":
            # Labelled as an observation, not a setting. A bare "Language:
            # English" line written months ago reads like a standing order and
            # was one of the reasons a Turkish question came back in English.
            core_lines.append(
                f"Has spoken to you in: {val} (an observation about the past — "
                f"always answer in the language of their CURRENT message)")
        else:
            core_lines.append(f"{field.title()}: {val}")
    for key, entry in identity.items():
        if key in _IDENTITY_FIELDS:
            continue
        val = _entry_value(entry)
        if val:
            core_lines.append(f"{_pretty(key).title()}: {val}")

    # 2. Everything else, most recently updated first
    rest: list[tuple[str, str, str, str]] = []   # (updated, cat, key, value)
    for cat in _CATEGORY_LABELS:
        for key, entry in (memory.get(cat, {}) or {}).items():
            val = _entry_value(entry)
            if not val:
                continue
            updated = (entry.get("updated", "") if isinstance(entry, dict) else "") or "0000-00-00"
            rest.append((updated, cat, key, val))
    rest.sort(key=lambda t: t[0], reverse=True)

    used    = sum(len(l) + 1 for l in core_lines)
    shown: dict[str, list[str]] = {}
    overflow: dict[str, list[str]] = {}

    # Recency decides order, but no single category may take the whole budget.
    # Without the cap, someone with forty stored preferences gets a prompt that
    # is forty preferences and not one person's name — the categories that
    # matter most in conversation are also the ones that change least often, so
    # pure recency systematically buries them.
    per_cat_used: dict[str, int] = {}
    for _updated, cat, key, val in rest:
        line = f"  - {_pretty(key).title()}: {val}"
        if (per_cat_used.get(cat, 0) < PROMPT_MAX_PER_CATEGORY
                and used + len(line) + 1 <= PROMPT_CORE_CHARS):
            shown.setdefault(cat, []).append(line)
            per_cat_used[cat] = per_cat_used.get(cat, 0) + 1
            used += len(line) + 1
        else:
            overflow.setdefault(cat, []).append(_pretty(key))

    # The index is a table of contents, so it is interleaved across categories
    # rather than continuing in recency order. Sorted by recency it would list
    # twenty-four preferences before the first relationship, and the one entry
    # the index exists for — the old fact the model has no other way to know
    # about — would fall off the end.
    indexed: list[str] = []
    if overflow:
        cats  = [c for c in _CATEGORY_LABELS if overflow.get(c)]
        cursor = {c: 0 for c in cats}
        while cats:
            for cat in list(cats):
                i = cursor[cat]
                if i >= len(overflow[cat]):
                    cats.remove(cat)
                    continue
                indexed.append(overflow[cat][i])
                cursor[cat] = i + 1

    for cat, label in _CATEGORY_LABELS.items():
        if shown.get(cat):
            core_lines.append("")
            core_lines.append(f"{label}:")
            core_lines.extend(shown[cat])

    if not core_lines and not indexed:
        return ""

    out = [
        "[WHAT YOU KNOW ABOUT THIS PERSON — use naturally, never recite like a list]",
        *core_lines,
    ]

    # 3. The index of what is on disk but not in this prompt
    if indexed:
        budget, names = PROMPT_INDEX_CHARS, []
        for n in indexed:
            if budget - len(n) - 2 < 0:
                break
            names.append(n)
            budget -= len(n) + 2
        if names:
            out.append("")
            out.append(
                "[ALSO REMEMBERED — values not shown here. Call recall_memory "
                "with a keyword to read any of these before saying you do not know]"
            )
            out.append(", ".join(names)
                       + (f" (+{len(indexed) - len(names)} more)"
                          if len(indexed) > len(names) else ""))

    return "\n".join(out) + "\n"


# ── Recall ────────────────────────────────────────────────────────────────────

def _score(query_words: list[str], cat: str, key: str, value: str) -> int:
    """Cheap lexical relevance. No embeddings, no network, no model call - this
    runs in well under a millisecond, which is the entire point: recall must
    cost one model round trip, never two."""
    hay_key = _pretty(key).lower()
    hay_val = value.lower()
    score   = 0
    for w in query_words:
        if not w:
            continue
        if w == hay_key:
            score += 10
        elif w in hay_key:
            score += 6
        if w in hay_val:
            score += 3
        if w in cat:
            score += 1
    return score


def search_memory(query: str, limit: int = 8) -> str:
    """Find stored facts matching `query`. Backs the recall_memory tool.

    An empty query is treated as "show me everything you know", capped - the
    model asks that when the user says "what do you remember about me?"."""
    memory = load_memory()
    words  = [w for w in re.split(r"[^\w]+", (query or "").lower()) if len(w) > 1]

    rows: list[tuple[int, str, str, str]] = []
    for cat, items in memory.items():
        if cat == "sessions" and isinstance(items, list):
            for index, entry in enumerate(items):
                if not isinstance(entry, dict):
                    continue
                val = str(entry.get("summary", "") or "").strip()
                if not val:
                    continue
                key = str(entry.get("id") or entry.get("date") or f"session_{index + 1}")
                s = _score(words, cat, key, val) if words else 1
                if s > 0:
                    rows.append((s, cat, key, val))
            continue
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            val = _entry_value(entry)
            if not val:
                continue
            s = _score(words, cat, key, val) if words else 1
            if s > 0:
                rows.append((s, cat, key, val))

    if not rows:
        return (f"Nothing stored about '{query}'." if query
                else "I have not stored anything about this person yet.")

    rows.sort(key=lambda r: (-r[0], r[2]))
    lines = [f"{cat}/{_pretty(key)}: {val}" for _s, cat, key, val in rows[:max(1, limit)]]
    head  = (f"Stored facts matching '{query}':" if query
             else "Everything currently stored:")
    more  = (f"\n(+{len(rows) - len(lines)} more — search with a narrower keyword)"
             if len(rows) > len(lines) else "")
    return head + "\n" + "\n".join(lines) + more


def all_entries_for_ui() -> list[dict]:
    """Flat list for the memory panel, including retained session summaries."""
    memory = load_memory()
    rows = []
    for cat, items in memory.items():
        if cat == "sessions" and isinstance(items, list):
            for index, entry in enumerate(items):
                if isinstance(entry, dict) and entry.get("summary"):
                    rows.append({
                        "category": "sessions",
                        "key": str(entry.get("id") or entry.get("date") or f"session_{index + 1}"),
                        "label": str(entry.get("date") or f"Session {index + 1}"),
                        "value": str(entry["summary"]),
                        "updated": str(entry.get("date") or ""),
                    })
            continue
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            val = _entry_value(entry)
            if not val:
                continue
            rows.append({
                "category": cat,
                "key": key,
                "value": val,
                "updated": (entry.get("updated", "") if isinstance(entry, dict) else ""),
            })
    rows.sort(key=lambda r: (r["updated"] or "0000-00-00"), reverse=True)
    return rows

def remember(key: str, value: str, category: str = "notes") -> str:
    valid = {"identity", "preferences", "projects", "relationships", "wishes", "notes"}
    if category not in valid:
        category = "notes"
    update_memory({category: {key: {"value": value}}})
    return f"Remembered: {category}/{key} = {value}"


def forget(key: str, category: str = "notes") -> str:
    """Delete one explicitly identified personal fact or session summary."""
    category = str(category or "notes").strip().lower()
    key = str(key or "").strip()
    with _lock:
        memory = load_memory()
        if category == "sessions":
            sessions = memory.get("sessions", [])
            if not isinstance(sessions, list):
                return f"Not found: sessions/{key}"
            matches = []
            for index, entry in enumerate(sessions):
                if not isinstance(entry, dict):
                    continue
                entry_id = str(entry.get("id") or "")
                entry_date = str(entry.get("date") or f"session_{index + 1}")
                if (entry_id and entry_id == key) or (not entry_id and entry_date == key):
                    matches.append(index)
            if len(matches) > 1:
                return "Multiple summaries share this date. Use the unique session ID from recall_memory."
            if matches:
                del sessions[matches[0]]
                memory["sessions"] = sessions
                save_memory(memory)
                return f"Forgotten: sessions/{key}"
            return f"Not found: sessions/{key}"
        if category not in _VALID_CATEGORIES:
            return "Invalid memory category."
        cat = memory.get(category, {})
        if isinstance(cat, dict) and key in cat:
            del cat[key]
            memory[category] = cat
            save_memory(memory)
            return f"Forgotten: {category}/{key}"
    return f"Not found: {category}/{key}"


def import_memory_text(title: str, content: str) -> dict:
    """Import a user-pasted note as atomic, searchable memory entries.

    Long text is split on word boundaries into validated note chunks. The
    complete batch is validated before a single write; existing memory is never
    overwritten by an import.
    """
    title = str(title or "").strip()
    content = str(content or "").strip()
    if not title:
        raise ValueError("Give this memory a title.")
    if len(title) > 60:
        raise ValueError("The memory title must be 60 characters or fewer.")
    if not content:
        raise ValueError("Paste the text you want JARVIS to remember.")
    if len(content) > 12000:
        raise ValueError("This import is too large (maximum 12,000 characters). Split it into smaller memories.")
    slug = re.sub(r"[^a-z0-9]+", "_", title.casefold()).strip("_")[:32] or "imported"
    words = content.split()
    chunks, current = [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if len(candidate) > 300 and current:
            chunks.append(current)
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    if not chunks:
        raise ValueError("The pasted text is empty.")

    with _lock:
        memory = load_memory()
        notes = memory.setdefault("notes", {})
        prefix = f"imported_{slug}"
        suffix = 1
        while any(f"{prefix}_{suffix + i:02d}" in notes for i in range(len(chunks))):
            suffix += 1
        updates = {}
        for index, chunk in enumerate(chunks, start=suffix):
            key = f"{prefix}_{index:02d}"
            value = f"[{title}] {chunk}"
            validate_memory_item("notes", key, value)
            updates[key] = {"value": value}
        _recursive_update(memory, {"notes": updates})
        save_memory(memory)
    return {"status": "saved", "title": title, "entries": len(chunks)}


forget_memory = forget


# ── Session memory ─────────────────────────────────────────────────────────────

_SESSION_MAX = 100   # retain up to 100 session summaries for searchable history
_SESSION_PROMPT_MAX = 3   # inject only the newest three into each session prompt


def save_session_summary(summary: str, language: str = "") -> None:
    """Append a 1-2 sentence session summary to long_term.json['sessions']."""
    summary = (summary or "").strip()
    if not summary:
        return
    with _lock:
        memory = load_memory()
        sessions = memory.get("sessions", [])
        if not isinstance(sessions, list):
            sessions = []
        now = datetime.now()
        entry: dict = {
            "id":      now.isoformat(timespec="microseconds"),
            "date":    now.strftime("%Y-%m-%d"),
            "summary": summary[:280],
        }
        if language:
            entry["language"] = language
        sessions.append(entry)
        memory["sessions"] = sessions[-_SESSION_MAX:]
        _write_memory_file(memory)
    print(f"[Memory] 📝 Session saved ({entry['date']})")


def get_last_session_for_briefing() -> dict | None:
    """
    Return the newest session summary not yet mentioned in a startup briefing.
    Mark it as briefed without deleting it: summaries remain available for long-term
    continuity and recall_memory.
    """
    with _lock:
        try:
            memory = load_memory()
            sessions = memory.get("sessions", [])
            if not isinstance(sessions, list):
                return None
            for entry in reversed(sessions):
                if not isinstance(entry, dict) or not entry.get("summary"):
                    continue
                if entry.get("briefed_at"):
                    continue
                entry["briefed_at"] = datetime.now().isoformat(timespec="seconds")
                _write_memory_file(memory)
                return dict(entry)
            return None
        except Exception as e:
            print(f"[Memory] ⚠️ get_last_session_for_briefing error: {e}")
            return None