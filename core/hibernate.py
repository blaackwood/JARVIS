"""Non-blocking preparation for JARVIS low-footprint hibernation."""
from __future__ import annotations

import threading
from collections.abc import Callable


def start_hibernate_preparation(
    callback: Callable[[str], object],
    mode: str,
    on_finished: Callable[[bool, str], object],
) -> threading.Thread:
    """Run task checkpointing away from the Qt UI thread.

    on_finished is invoked from the worker thread. A Qt signal's emit method
    is safe to use here and will deliver the result on its owning thread.
    """
    def worker() -> None:
        try:
            result = callback(mode)
            ok, detail = result if isinstance(result, tuple) else (bool(result), "")
        except Exception as exc:
            ok, detail = False, str(exc)
        try:
            on_finished(bool(ok), str(detail or ""))
        except Exception:
            # The UI may already be closing. A failed notification must never
            # turn a successfully checkpointed task into a failed checkpoint.
            pass

    thread = threading.Thread(
        target=worker,
        name="JarvisHibernatePreparation",
        daemon=True,
    )
    thread.start()
    return thread
