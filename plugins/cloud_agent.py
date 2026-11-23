"""Paired JARVIS cloud body over the existing pinned-TLS link.

The plugin is deliberately dormant until the user pastes a pairing code in
Plugin Settings and tests it. Reminder IDs are stable across this desktop and
the cloud routine store; no Telegram token is stored on this computer.
"""
from __future__ import annotations

from datetime import datetime
import re
import threading
import time


def _pair_code(values=None) -> str:
    if isinstance(values, dict) and values.get("pair_code"):
        return str(values["pair_code"]).strip()
    from memory.config_manager import get_plugin_config
    return str(get_plugin_config("cloud_agent").get("pair_code") or "").strip()


def _client(values=None):
    code = _pair_code(values)
    if not code:
        raise ValueError("Paste the cloud pairing code first.")
    from core.cloud import Client
    return Client.from_code(code)


def _worker_config(values=None):
    supplied = values if isinstance(values, dict) else {}
    try:
        from memory.config_manager import get_plugin_config
        saved = get_plugin_config("cloud_agent")
    except Exception:
        saved = {}
    base = str(supplied.get("worker_url") if "worker_url" in supplied else saved.get("worker_url") or "").strip()
    token = str(supplied.get("worker_token") if "worker_token" in supplied else saved.get("worker_token") or "").strip()
    if not base and not token:
        return None
    if not base or len(token) < 32:
        raise ValueError("Cloudflare Worker URL and a 32-character API token are both required.")
    from urllib.parse import urlsplit
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Cloudflare Worker URL must be a clean HTTPS address.")
    if parsed.path not in ("", "/"):
        raise ValueError("Cloudflare Worker URL must contain only the origin, without a path.")
    return base.rstrip("/"), token


def _worker_request(method, path, body=None, values=None):
    config = _worker_config(values)
    if not config:
        raise ValueError("Cloudflare Worker is not configured.")
    import requests
    base, token = config
    response = requests.request(
        str(method).upper(), base + "/" + str(path).lstrip("/"),
        json=body if body is not None else None,
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
        timeout=(5, 15),
    )
    try:
        payload = response.json()
    except Exception:
        payload = {}
    if response.status_code >= 400:
        raise RuntimeError(str(payload.get("error") or f"Cloudflare answered HTTP {response.status_code}")[:180])
    if not isinstance(payload, dict):
        raise RuntimeError("Cloudflare returned an invalid response.")
    return payload


def _cloud_configured() -> bool:
    try:
        return bool(_worker_config()) or bool(_pair_code())
    except Exception:
        return False


def _local_offset_minutes() -> int:
    offset = datetime.now().astimezone().utcoffset()
    return int(offset.total_seconds() // 60) if offset else 0


def _checked_result(response: dict) -> tuple[bool, str]:
    result = str((response or {}).get("result") or "")
    if result.startswith("status=done "):
        return True, result
    if result.startswith("status=failed "):
        return False, result
    return False, result or "The cloud server returned no schedule result."


_sync_stop = threading.Event()
_sync_lock = threading.Lock()
_sync_thread = None


def _test_connection(values=None) -> tuple[bool, str]:
    try:
        worker = _worker_config(values)
        if worker:
            health = _worker_request("GET", "api/health", values=values)
            if health.get("server") != "jarvis-cloudflare" or not health.get("ok"):
                return False, "The endpoint did not identify itself as the JARVIS Cloudflare service."
            setup = _worker_request("GET", "api/setup", values=values)
            detail = "Connected to JARVIS Cloudflare storage."
            detail += (
                "\n\niPhone - Apple Reminders list JARVIS"
                f"\nInstall profile: {setup.get('setup_profile_url', '')}"
                f"\nPrivate setup page: {setup.get('credentials_url', '')}"
                "\nUse username 'jarvis' and the CalDAV password configured for this Worker."
            )
            start_reminder_sync()
            return True, detail

        client = _client(values)
        response = client.request("POST", "hello", {}, timeout=12)
        if response.get("server") != "jarvis-cloud":
            return False, "The paired endpoint did not identify itself as a JARVIS cloud body."
        phones = int(response.get("telegram_phones") or 0)
        configured = bool(response.get("telegram_configured"))
        name = str(response.get("name") or "JARVIS")
        detail = f"Connected to {name}'s cloud body."
        detail += " Telegram is configured." if configured and phones else " Cloud link works, but Telegram has no approved phone yet."
        try:
            setup = client.request("POST", "caldav_info", {}, timeout=12)
        except Exception:
            setup = {}
        if setup.get("ok"):
            detail += (
                "\n\niPhone - Apple Reminders list JARVIS"
                f"\nInstall profile: {setup.get('setup_profile_url', '')}"
                f"\nPrivate account details: {setup.get('credentials_url', '')}"
                "\nInstall the profile, enable full trust for the JARVIS root certificate, "
                "then open the private details link to enter the account password when iOS asks."
            )
        else:
            detail += " The cloud endpoint is connected, but its CalDAV setup route is not available yet; update the cloud server."
        start_reminder_sync()
        return True, detail
    except Exception as exc:
        return False, f"Cloud connection failed: {type(exc).__name__}: {str(exc)[:180]}"



def sync_reminder_states() -> tuple[bool, str]:
    """Pull phone-side completion/snooze changes into the desktop's canonical records."""
    if not _cloud_configured():
        return False, "cloud link is not configured"
    if not _sync_lock.acquire(blocking=False):
        return False, "sync already running"
    try:
        from core.routines import desktop
        engine = desktop.engine()
        if engine is None:
            return False, "desktop routines are not attached yet"
        if _worker_config():
            response = _worker_request("GET", "api/reminders")
        else:
            response = _client().request("POST", "schedule", {
                "action": "sync", "tz_offset_min": _local_offset_minutes(),
            }, timeout=20)
        remote = response.get("reminders")
        if not isinstance(remote, list):
            return False, "the cloud server does not support structured reminder sync; update the cloud service"
        by_id = {str(item.get("id") or ""): item for item in remote if isinstance(item, dict)}
        changed = 0
        from actions.reminder import (_cancel_os_schedule, _reschedule_os_schedule,
                                      _get_os, _write_notify_script, _schedule_windows,
                                      _schedule_mac, _schedule_linux)
        local_by_id = {
            str(((r.get("options") or {}).get("jarvis_reminder") or {}).get("id") or ""): r
            for r in engine.list() if r.get("source") == "reminder"
        }
        # A reminder created from Telegram exists first on the cloud body. Bring
        # it into the same local routine store so the desktop HUD shows it too.
        for rid, cloud in by_id.items():
            if not rid:
                continue
            existing_local = local_by_id.get(rid)
            if existing_local is not None:
                # The cloud create may have succeeded while its HTTPS response
                # was lost. The matching external ID is our idempotency proof:
                # recover the sync link in place instead of making another row.
                options = dict(existing_local.get("options") or {})
                meta = dict(options.get("jarvis_reminder") or {})
                if not meta.get("cloud_synced"):
                    meta.update({"cloud_synced": True,
                                 "cloud_id": str(cloud.get("cloud_id") or ""),
                                 "sync_recovered_at": time.time()})
                    options["jarvis_reminder"] = meta
                    try:
                        existing_local = engine.update(existing_local["id"], options=options)
                        local_by_id[rid] = existing_local
                        changed += 1
                    except Exception:
                        continue
                continue
            due_ts = float(cloud.get("due_ts") or 0)
            message = str(cloud.get("message") or "").strip()[:200]
            status = str(cloud.get("status") or "open").lower()
            if due_ts <= 0 or not message or status not in {"open", "done", "cancelled", "missed"}:
                continue
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", rid):
                continue
            task_name = f"JARVISReminder_{rid}"
            os_name = _get_os()
            meta = {"id": rid, "cloud_id": str(cloud.get("cloud_id") or ""),
                    "status": status, "due_ts": due_ts, "message": message,
                    "os_name": os_name, "task_name": task_name, "script_path": "",
                    "scheduler_id": "", "cloud_synced": True,
                    "created_at": time.time(), "imported_from_cloud": True}
            enabled = status == "open" and due_ts > time.time()
            if enabled:
                script_path = _write_notify_script(task_name, message, os_name)
                due_dt = datetime.fromtimestamp(due_ts)
                try:
                    if os_name == "windows":
                        scheduler_id = _schedule_windows(due_dt, task_name, script_path, message)
                    elif os_name == "mac":
                        scheduler_id = _schedule_mac(due_dt, task_name, script_path)
                    else:
                        scheduler_id = _schedule_linux(due_dt, task_name, script_path)
                except Exception:
                    script_path.unlink(missing_ok=True)
                    scheduler_id = ""
                if scheduler_id:
                    meta.update({"script_path": str(script_path), "scheduler_id": scheduler_id})
                else:
                    script_path.unlink(missing_ok=True)
                    meta["local_notification_unavailable"] = True
            elif status == "open":
                meta["overdue"] = True
            try:
                imported = engine.add(
                    name=message[:60] or "Reminder", kind="say", text=message,
                    trigger={"type": "time", "rule": {"type": "once", "at_ts": due_ts}},
                    source="reminder", options={"jarvis_reminder": meta},
                    next_ts=due_ts, enabled=enabled,
                )
            except Exception:
                if meta.get("scheduler_id"):
                    _cancel_os_schedule(meta)
                continue
            local_by_id[rid] = imported
            changed += 1

        for routine in engine.list():
            if routine.get("source") != "reminder":
                continue
            options = dict(routine.get("options") or {})
            meta = dict(options.get("jarvis_reminder") or {})
            if not meta.get("cloud_synced"):
                continue
            rid = str(meta.get("id") or "")
            cloud = by_id.get(rid)
            if not cloud:
                continue
            remote_state = str(cloud.get("status") or "open").lower()
            if remote_state not in {"open", "done", "cancelled", "missed"}:
                continue
            due_ts = float(cloud.get("due_ts") or meta.get("due_ts") or 0)
            local_state = str(meta.get("status") or "open")
            due_changed = due_ts > 0 and abs(due_ts - float(meta.get("due_ts") or 0)) > 30
            new_meta = dict(meta)
            if due_ts > 0:
                new_meta["due_ts"] = due_ts
            if cloud.get("message"):
                new_meta["message"] = str(cloud["message"])[:200]

            if remote_state == "open":
                if due_ts > time.time():
                    if local_state != "open" or due_changed or not meta.get("scheduler_id"):
                        ok, detail, restored = _reschedule_os_schedule(dict(new_meta, status="open"))
                        if not ok:
                            continue
                        new_meta.update(restored)
                    new_meta.update({"status": "open", "overdue": False})
                    trigger = {"type": "time", "rule": {"type": "once", "at_ts": due_ts}}
                    engine.update(routine["id"], trigger=trigger, enabled=True, text=new_meta.get("message") or routine.get("text"),
                                  options={"jarvis_reminder": new_meta})
                else:
                    if local_state == "open" and meta.get("scheduler_id"):
                        ok, _ = _cancel_os_schedule(meta)
                        if not ok:
                            continue
                    new_meta.update({"status": "open", "overdue": True})
                    engine.update(routine["id"], enabled=False, text=new_meta.get("message") or routine.get("text"),
                                  options={"jarvis_reminder": new_meta})
                changed += int(remote_state != local_state or due_changed)
                continue

            # Terminal states from Telegram/cloud must cancel the desktop job
            # before the UI is allowed to show the item as closed.
            if local_state not in {"done", "cancelled", "missed"} and meta.get("scheduler_id"):
                ok, _ = _cancel_os_schedule(meta)
                if not ok:
                    continue
            new_meta["status"] = remote_state
            for key in ("completed_at", "cancelled_at", "missed_at"):
                if cloud.get(key):
                    new_meta[key] = cloud[key]
            engine.update(routine["id"], enabled=False,
                          text=new_meta.get("message") or routine.get("text"),
                          options={"jarvis_reminder": new_meta})
            changed += int(remote_state != local_state)
        return True, f"synchronized {changed} reminder state change(s)"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {str(exc)[:160]}"
    finally:
        _sync_lock.release()


def _sync_loop() -> None:
    while not _sync_stop.is_set():
        try:
            from memory.config_manager import get_plugin_enabled
            if get_plugin_enabled("cloud_agent") and _cloud_configured():
                sync_reminder_states()
        except Exception:
            pass
        _sync_stop.wait(45.0)


def start_reminder_sync() -> bool:
    """Start one quiet background sync worker; it does nothing without pairing."""
    global _sync_thread
    if not _cloud_configured():
        return False
    try:
        from memory.config_manager import get_plugin_enabled
        if not get_plugin_enabled("cloud_agent"):
            return False
    except Exception:
        return False
    if _sync_thread is not None and _sync_thread.is_alive():
        return True
    _sync_stop.clear()
    _sync_thread = threading.Thread(target=_sync_loop, name="jarvis-cloud-reminder-sync", daemon=True)
    _sync_thread.start()
    return True


def stop_reminder_sync() -> None:
    _sync_stop.set()


def mirror_reminder(message: str, target_dt: datetime, reminder_id: str = "") -> tuple[bool, str]:
    """Create the phone-side copy with the desktop's stable reminder identity."""
    try:
        worker = _worker_config()
        if worker:
            if isinstance(target_dt, datetime):
                due_ts = target_dt.timestamp()
            else:
                parsed = datetime.fromisoformat(str(target_dt))
                if parsed.tzinfo is None:
                    parsed = parsed.astimezone()
                due_ts = parsed.timestamp()
            response = _worker_request("POST", "api/reminders", {
                "action": "upsert", "id": str(reminder_id or "")[:180],
                "message": str(message or "Reminder")[:200],
                "due_ts": due_ts, "status": "open",
            })
            return bool(response.get("ok")), "Cloudflare reminder saved." if response.get("ok") else "Cloudflare did not save the reminder."

        body = {
            "action": "add", "reminder": str(message or "Reminder")[:200],
            "at": target_dt.strftime("%Y-%m-%d %H:%M"),
            "external_id": str(reminder_id or "")[:64],
            "tz_offset_min": _local_offset_minutes(),
        }
        response = _client().request("POST", "schedule", body, timeout=18)
        ok, detail = _checked_result(response)
        return ok, detail if ok else f"Cloud reminder was not created: {detail}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {str(exc)[:160]}"


def set_reminder_state(reminder_id: str, state: str) -> tuple[bool, str]:
    state = str(state or "").lower()
    if state not in {"open", "done", "cancelled"}:
        return False, "state must be open, done or cancelled"
    try:
        if _worker_config():
            response = _worker_request("POST", "api/reminders", {
                "action": "state", "id": str(reminder_id or "")[:180], "status": state,
            })
            return bool(response.get("ok")), "Cloudflare reminder updated." if response.get("ok") else "Cloudflare did not update the reminder."

        action = {"open": "reopen", "done": "complete", "cancelled": "cancel"}[state]
        response = _client().request("POST", "schedule", {
            "action": action, "id": str(reminder_id or "")[:64],
            "tz_offset_min": _local_offset_minutes(),
        }, timeout=18)
        ok, detail = _checked_result(response)
        return ok, detail if ok else f"Cloud reminder was not changed: {detail}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {str(exc)[:160]}"


def run(parameters: dict, player=None, session_memory=None) -> str:
    action = str((parameters or {}).get("action") or "status").lower()
    if action == "status":
        ok, detail = _test_connection()
        return ("CLOUD_CONNECTED: " if ok else "CLOUD_NOT_CONNECTED: ") + detail
    return "Unknown action. Use status."


PLUGIN = {
    "name": "cloud_agent",
    "description": (
        "Status of the optional paired JARVIS cloud body. The pairing code is private "
        "and is configured only in Plugin Settings; do not ask the user to speak it aloud. "
        "Timed reminders are mirrored automatically when the link is configured."
    ),
    "tier": "extra",
    "brief": "Check the optional JARVIS cloud link status.",
    "parameters": {
        "type": "OBJECT",
        "properties": {"action": {"type": "STRING", "enum": ["status"]}},
        "required": ["action"],
    },
}

PLUGIN_SETTINGS = {
    "namespace": "cloud_agent",
    "title": "JARVIS cloud link",
    "fields": [
        {
            "key": "pair_code", "label": "Legacy pairing code (optional)",
            "type": "password", "placeholder": "jarvis://host:port/secret#certificate-fingerprint",
        },
        {
            "key": "worker_url", "label": "Cloudflare Worker HTTPS URL",
            "type": "text", "placeholder": "https://jarvis-reminders.<account>.workers.dev",
        },
        {
            "key": "worker_token", "label": "Cloudflare JARVIS API token",
            "type": "password", "placeholder": "Private token configured as a Worker secret",
        },
    ],
    "action": {"label": "TEST & SYNC CLOUD LINK", "run": _test_connection},
}
