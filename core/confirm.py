"""
core/confirm.py — a confirmation the model cannot forge.

THE PROBLEM WITH THE OLD GATE
    computer_settings guarded shutdown and restart like this:

        confirmed = str(params.get("confirmed", "")).lower()
        if confirmed not in ("yes", "true", "1", "confirm"):
            return "Please confirm by calling again with confirmed=yes."

    `confirmed` is a tool parameter, which means the *model* writes it. Nothing
    stops it from sending confirmed=yes on the first call, and nothing checks
    that a human was ever involved. It is a convention, not a gate — and its
    coverage was two actions, so deleting files and switching off the WiFi the
    assistant is talking over went through with no gate at all.

THE DESIGN HERE
    The confirmation token is issued by the *interface*, never by the model:

      1. An action calls `request(...)` with a callable that does the real work.
      2. This module hands the UI a banner with CONFIRM / CANCEL.
      3. The caller may either return a pending notice immediately, or wait
         off the Qt thread for the human decision and final action result.
      4. If — and only if — the user presses CONFIRM, the UI calls `resolve()`,
         which runs the stored callable off the Qt thread.

    Central tool dispatch waits for the final result so the model receives one
    authoritative FunctionResponse after the human decision. The UI event loop
    remains free while the tool's executor thread waits.

WHAT BELONGS HERE AND WHAT DOES NOT
    Only genuinely irreversible things. Anything that can be reversed should be
    done at once and pushed onto core/undo.py instead — undo is faster than a
    question, and an assistant that asks before every action is one nobody uses.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

# A pending confirmation is abandoned after this long. Chosen to outlast a
# normal "hang on, let me look at the screen" pause without leaving a live
# shutdown button sitting on the HUD for the rest of the day.
TIMEOUT_SECONDS = 90.0


@dataclass
class _Pending:
    key:     str
    title:   str
    detail:  str
    run:     Callable[[], str]
    at:      float
    wait_for_result: bool = False
    decision_event: threading.Event = field(default_factory=threading.Event)
    done_event: threading.Event = field(default_factory=threading.Event)
    result: str = ""


_pending: Optional[_Pending] = None
_lock = threading.Lock()
_workers_lock = threading.Lock()
_workers: set[threading.Thread] = set()


def wait_for_workers(timeout: float = 2.0) -> bool:
    """Wait for accepted confirmation callbacks to finish.

    Primarily useful to deterministic tests and orderly shutdown; normal UI
    operation remains fully asynchronous.
    """
    deadline = time.monotonic() + max(0.0, float(timeout))
    while True:
        with _workers_lock:
            workers = tuple(_workers)
        if not workers:
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        for worker in workers:
            worker.join(timeout=min(0.05, remaining))


# Set once at startup by main.py. Signature: (title, detail) -> None for show,
# and () -> None for hide. Both are marshalled onto the Qt thread by the UI.
_show_cb: Optional[Callable[[str, str], None]] = None
_hide_cb: Optional[Callable[[], None]] = None
_log_cb:  Optional[Callable[[str], None]] = None


def bind(show, hide, log=None) -> None:
    """Wire this module to the HUD. Called once from main.py at startup."""
    global _show_cb, _hide_cb, _log_cb
    _show_cb, _hide_cb, _log_cb = show, hide, log


def _log(msg: str) -> None:
    if _log_cb:
        try:
            _log_cb(msg)
        except Exception:
            pass


def request(key: str, title: str, detail: str, run: Callable[[], str],
            *, wait_for_result: bool = False) -> str:
    """Park an action behind the on-screen gate.

    When wait_for_result is true, the caller (which must be off the Qt thread)
    waits for the human's decision and the action result. This lets a Live tool
    call return ONE final FunctionResponse after approval instead of leaving the
    model with a stale CONFIRMATION_PENDING response.
    """
    global _pending

    if _show_cb is None:
        return (f"I cannot confirm '{title}' right now because the interface is "
                f"not available, so I have not done it.")

    p = _Pending(key=key, title=title, detail=detail, run=run,
                 at=time.monotonic(), wait_for_result=bool(wait_for_result))
    with _lock:
        if _pending is not None and time.monotonic() - _pending.at <= TIMEOUT_SECONDS:
            return ("Another confirmation is already pending. Answer that "
                    "request first; this action was not queued.")
        _pending = p

    try:
        _show_cb(title, detail)
    except Exception as e:
        with _lock:
            if _pending is p:
                _pending = None
        p.result = f"Could not ask for confirmation: {e}. Nothing was done."
        p.decision_event.set()
        p.done_event.set()
        return p.result

    _log(f"SYS: Awaiting confirmation — {title}")
    if not p.wait_for_result:
        return (
            f"[CONFIRMATION_PENDING] I have put a confirmation on screen for: {title}. "
            "Tell the user to confirm or cancel it on the HUD. Do not claim it is done."
        )

    # This runs in an action executor thread, never in the Qt thread. The HUD
    # remains interactive while the Live tool call waits for its final result.
    if not p.decision_event.wait(TIMEOUT_SECONDS):
        expired = False
        with _lock:
            if _pending is p:
                _pending = None
                expired = True
        if expired:
            p.result = "CONFIRMATION_EXPIRED: no decision was received. Nothing was executed."
            p.done_event.set()
            if _hide_cb:
                try:
                    _hide_cb()
                except Exception:
                    pass
            _log(f"SYS: Confirmation expired — {p.title}")
            return p.result

    p.done_event.wait()
    return p.result or "The confirmation ended without an action result."


def resolve(accepted: bool) -> None:
    """Called by the UI when the user presses CONFIRM or CANCEL.

    Accepted work always runs off the Qt thread. Waiting callers are released
    only after the action has produced its final result.
    """
    global _pending

    with _lock:
        p, _pending = _pending, None

    if _hide_cb:
        try:
            _hide_cb()
        except Exception:
            pass

    if p is None:
        return

    p.decision_event.set()
    if time.monotonic() - p.at > TIMEOUT_SECONDS:
        p.result = "CONFIRMATION_EXPIRED: the decision arrived too late. Nothing was executed."
        p.done_event.set()
        _log(f"SYS: Confirmation expired — {p.title}")
        return

    if not accepted:
        p.result = "ACTION_CANCELLED_BY_USER: nothing was executed."
        p.done_event.set()
        _log(f"SYS: Cancelled — {p.title}")
        return

    def _worker():
        try:
            result = p.run() or "Done."
            p.result = str(result)
            _log(f"SYS: Confirmed — {p.title}. {p.result}")
        except Exception as e:
            p.result = f"Action failed: {e}"
            _log(f"ERR: {p.title} failed — {e}")
        finally:
            p.done_event.set()
            with _workers_lock:
                _workers.discard(threading.current_thread())

    worker = threading.Thread(target=_worker, daemon=True,
                              name=f"confirm-{p.key}")
    with _workers_lock:
        _workers.add(worker)
    worker.start()


def pending_title() -> str:
    """'' when nothing is waiting. Lets an action avoid stacking two banners."""
    with _lock:
        if _pending is None:
            return ""
        if time.monotonic() - _pending.at > TIMEOUT_SECONDS:
            return ""
        return _pending.title
