"""Standalone background-task host used while the JARVIS UI is hibernated."""
from __future__ import annotations

import ctypes
import json
import os
import sys
import time
from pathlib import Path

# This worker runs unattended while the desktop interface is hibernated.
# Extend the same no-terminal policy to every subprocess used by task actions.
from core.windows_process import install_no_console_policy
install_no_console_policy()

BASE = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
STOP = BASE / "memory" / "task_worker.stop"
CANCEL = BASE / "memory" / "task_worker.cancel"
PID = BASE / "memory" / "task_worker.pid"
HANDOFF = BASE / "memory" / "task_worker_handoff.json"
MUTEX = r"Global\JarvisTaskWorker"


def _wait_parent(pid: int) -> None:
    if pid <= 0 or os.name != "nt":
        return
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
    k.OpenProcess.restype = ctypes.c_void_p
    k.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = k.OpenProcess(0x00100000, False, pid)
    if not handle:
        return
    try:
        while k.WaitForSingleObject(handle, 500) == 0x102:
            pass
    finally:
        k.CloseHandle(handle)


def _mutex():
    if os.name != "nt":
        return None
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    k.CreateMutexW.restype = ctypes.c_void_p
    ctypes.set_last_error(0)
    handle = k.CreateMutexW(None, False, MUTEX)
    if not handle:
        raise OSError("could not create task worker mutex")
    if ctypes.get_last_error() == 183:
        k.CloseHandle(ctypes.c_void_p(handle))
        return None
    return k, handle


def _run_engine() -> int:
    from core.tasks.engine import TaskEngine
    from memory.config_manager import load_api_keys

    def log(message: str) -> None:
        try:
            with (BASE / "memory" / "task_worker.log").open("a", encoding="utf-8") as stream:
                stream.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
        except Exception:
            pass

    def notify(event, task, detail):
        title = (task or {}).get("title", "task")
        log(f"{event}: {title}: {str(detail)[:180]}")

    config = load_api_keys()
    max_parallel = max(1, min(4, int(config.get("tasks_max_parallel") or 2)))
    engine = TaskEngine(
        BASE / "memory" / "tasks",
        BASE / "reports",
        [BASE / "agents"],
        notify=notify,
        max_parallel=max_parallel,
        log=log,
    )
    try:
        if CANCEL.exists():
            log("complete exit requested; cancelling unfinished tasks")
            engine.shutdown(wait=5.0, cancel_active=True)
            return 0
        try:
            handoff = json.loads(HANDOFF.read_text(encoding="utf-8")) if HANDOFF.exists() else {}
        except Exception:
            handoff = {}
        resume_ids = set(handoff.get("resume_ids") or [])
        scheduled_ids = set(handoff.get("scheduled_ids") or [])
        HANDOFF.unlink(missing_ok=True)
        resumed = 0
        restored_scheduled = 0
        for task in engine.list(500):
            tid = task.get("id")
            if task.get("status") != "paused":
                continue
            if tid in resume_ids and engine.resume(tid):
                resumed += 1
            elif tid in scheduled_ids:
                # Preserve the original due time; do not turn a future task
                # into an immediate task merely because the UI hibernated.
                engine.store.update(tid, status="scheduled", paused_at=0.0)
                restored_scheduled += 1
        log(f"worker active; resumed {resumed} task(s), restored {restored_scheduled} scheduled task(s)")
        while not STOP.exists():
            time.sleep(0.5)
        if CANCEL.exists():
            log("complete exit requested; cancelling unfinished tasks")
            engine.shutdown(wait=5.0, cancel_active=True)
            return 0
        log("handoff requested; checkpointing active tasks")
        ok, pending = engine.pause_all(timeout=60.0)
        while not ok:
            log("waiting for safe checkpoint: " + ", ".join(
                t.get("title", t["id"]) for t in pending
            ))
            time.sleep(1.0)
            ok, pending = engine.pause_all(timeout=5.0)
        log("all tasks parked; worker stopping")
        engine.shutdown(wait=5.0, cancel_active=False)
        return 0
    finally:
        # The task engine must never outlive its process after a handoff.
        try:
            engine.shutdown(wait=5.0, cancel_active=False)
        except Exception:
            pass


def main() -> int:
    parent_pid = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    owned_mutex = _mutex()
    if os.name == "nt" and owned_mutex is None:
        return 0
    PID.parent.mkdir(parents=True, exist_ok=True)
    PID.write_text(str(os.getpid()), encoding="ascii")
    try:
        _wait_parent(parent_pid)
        # A wake can arrive before this process has started its scheduler.
        # In that case the daemon's stop marker prevents any task from resuming.
        if STOP.exists() and not CANCEL.exists():
            return 0
        return _run_engine()
    except Exception as exc:
        try:
            with (BASE / "memory" / "task_worker.log").open("a", encoding="utf-8") as stream:
                stream.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} worker error: {type(exc).__name__}: {exc}\n")
        except Exception:
            pass
        return 1
    finally:
        PID.unlink(missing_ok=True)
        if owned_mutex:
            owned_mutex[0].CloseHandle(ctypes.c_void_p(owned_mutex[1]))


if __name__ == "__main__":
    raise SystemExit(main())
