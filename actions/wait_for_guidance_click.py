from __future__ import annotations

import core.screenview as screenview
from core.guidance import (
    clear_target, get_target, set_target, wait_for_user_click, wait_for_user_hover,
    windows_escape_down, windows_mouse_poll, point_inside,
)


def wait_for_guidance_click(parameters: dict, player=None, speak=None) -> str:
    """Wait for a fresh physical click in the currently highlighted control bounds."""
    params = parameters or {}
    timeout = max(1.0, min(300.0, float(params.get("timeout", 120) or 120)))
    mode = str(params.get("mode") or "click").strip().lower()
    if mode not in {"click", "hover"}:
        return "INVALID_WAIT_MODE: use click or hover."
    expect_text = str(params.get("expect_text") or "").strip()
    if mode == "hover" and expect_text:
        return "INVALID_WAIT: expect_text is available only after a click."

    target = get_target()
    if target is None:
        return "NO_GUIDED_TARGET: call highlight_screen_target first."

    try:
        from core import screenview
        current = screenview.look(allow_ocr=False)
        if current.degraded or current.source != "uia":
            return (
                "TARGET_NOT_RECHECKED: Windows UI Automation is unavailable now. "
                "The old highlight was removed; inspect the screen and highlight the control again."
            )
        if target.pid and current.pid != target.pid:
            return (
                f"TARGET_WINDOW_CHANGED: the foreground application changed from "
                f"{target.app!r}. The old click target is stale; inspect and highlight again."
            )
        if target.title and current.title != target.title:
            return (
                "TARGET_WINDOW_CHANGED: the foreground window title changed. "
                "The old click target is stale; inspect and highlight again."
            )
        from core.appidentity import fold
        hits = current.find(
            target.label, role=target.role, interactable_only=True, limit=12
        )
        exact = [el for el in hits if fold(el.label) == fold(target.label)]
        if len(exact) != 1:
            return (
                f"TARGET_NO_LONGER_UNIQUE: {target.label!r} now resolves to "
                f"{len(exact)} enabled exact controls. Inspect and highlight again."
            )
        live = exact[0]
        if not live.enabled or live.width <= 0 or live.height <= 0:
            return "TARGET_NO_LONGER_ACTIONABLE: the control is disabled or has no usable bounds."
        if live.rect != target.rect:
            # The app may have reflowed while the instruction was spoken. Move
            # the frame to the fresh, exact bounds rather than waiting on stale pixels.
            target = set_target(
                live.rect, live.label, app=current.app, title=current.title,
                pid=current.pid, step=target.step, role=live.role,
            )
            if player is None or not callable(getattr(player, "show_guidance_target", None)):
                return "GUIDANCE_UNAVAILABLE: the target moved and the overlay cannot be refreshed."
            player.show_guidance_target(target.rect, target.label, target.step)

        waiter = wait_for_user_click if mode == "click" else wait_for_user_hover
        outcome = waiter(
            target,
            timeout=timeout,
            poll=windows_mouse_poll,
            cancel=windows_escape_down,
        )
        if outcome["status"] == "cancelled":
            return "GUIDANCE_CANCELLED: Escape was pressed; no next step was advanced."
        if outcome["status"] == "timeout":
            if mode == "hover":
                return (
                    f"GUIDANCE_HOVER_TIMEOUT: the pointer did not remain over "
                    f"{target.label!r} for the required dwell within {timeout:.0f} seconds. Stay on this step."
                )
            return (
                f"GUIDANCE_TIMEOUT: no new left click was observed inside "
                f"{target.label!r} within {timeout:.0f} seconds. Stay on this step."
            )
        if mode == "hover":
            return (
                f"GUIDANCE_HOVERED: the user moved the pointer over the real bounds of "
                f"{target.label!r} and held it there for {outcome['dwell']:.2f} seconds. "
                "The hover was observed; inspect the next screen state before choosing another target."
            )

        # The click location has been observed. That alone is not proof the app
        # accepted it, so a fresh accessibility scan checks only an explicit
        # visible postcondition supplied by the caller.
        after = screenview.look(allow_ocr=False)
        if after.degraded or after.source != "uia":
            return (
                f"CLICK_SEEN_NOT_VERIFIED: the user clicked inside {target.label!r}, "
                "but the application state could not be re-read. Do not claim the task completed."
            )
        after_hits = after.find(
            target.label, role=target.role, interactable_only=False, limit=12
        )
        after_exact = [el for el in after_hits if fold(el.label) == fold(target.label)]
        if len(after_exact) == 1 and not point_inside(after_exact[0].rect, outcome["point"]):
            return (
                f"CLICK_TARGET_MOVED: the click landed inside the old frame for "
                f"{target.label!r}, but the control moved before the click was confirmed. "
                "Inspect and highlight the new position; do not advance."
            )
        if expect_text and after.contains_text(expect_text):
            return (
                f"CLICK_AND_POSTCONDITION_VERIFIED: the user clicked {target.label!r}; "
                f"fresh screen inspection found {expect_text!r}. It is safe to proceed to the next step."
            )
        if expect_text:
            return (
                f"CLICK_SEEN_NOT_VERIFIED: click inside {target.label!r} was observed, "
                f"but expected visible text {expect_text!r} was not found. Inspect the screen "
                "before advancing or retrying."
            )
        still_present = after.find(target.label, role="", interactable_only=False, limit=4)
        return (
            f"CLICK_SEEN_NOT_VERIFIED: a new left click was observed inside the real "
            f"bounds of {target.label!r} at {outcome['point']}. "
            + ("The same label is still visible; " if still_present else "The previous label is no longer visible; ")
            + "the application result has not been verified. Inspect the new screen state before the next step."
        )
    except Exception as exc:
        return f"GUIDANCE_WAIT_FAILED: {type(exc).__name__}: {str(exc)[:180]}"
    finally:
        clear_target()
        if player is not None and callable(getattr(player, "clear_guidance_target", None)):
            try:
                player.clear_guidance_target()
            except Exception:
                pass


TOOL = {
    "name": "wait_for_guidance_click",
    "description": (
        "Wait for the user's next physical interaction inside the exact highlighted control. "
        "Call only after highlight_screen_target has displayed a fresh, unique Windows UIA target "
        "and you have spoken the instruction. mode=click (default) waits for a new physical left "
        "click; mode=hover waits for a fresh pointer entry held over the target for 0.45 seconds "
        "without a mouse button pressed. Escape or timeout pauses the step. The tool never clicks "
        "automatically and never treats a mark as input. A click is not proof the app accepted it; "
        "supply expect_text only when a visible postcondition must be verified. A hover is only an "
        "observed pointer interaction; inspect the changed screen before selecting the next target."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "mode": {"type": "STRING", "enum": ["click", "hover"], "description": "Physical click by default, or pointer hover held over the target."},
            "timeout": {"type": "NUMBER", "description": "Wait time in seconds, 1 to 300; default 120."},
            "expect_text": {"type": "STRING", "description": "Optional visible text required after the click to verify the result."},
        },
        "required": [],
    },
    "handler": wait_for_guidance_click,
    "tier": "core",
    "brief": "Wait for the user to click the highlighted control and report whether the result was verified.",
}
