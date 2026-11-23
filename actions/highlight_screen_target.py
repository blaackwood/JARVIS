from __future__ import annotations

import core.screenview as screenview

import time


def highlight_screen_target(parameters: dict, player=None, speak=None) -> str:
    """Resolve one exact live UI Automation control, then highlight its real bounds."""
    params = parameters or {}
    target_text = str(params.get("target") or "").strip()
    role = str(params.get("role") or "").strip().lower()
    step = max(1, min(99, int(params.get("step", 1) or 1)))
    if not target_text:
        return "TARGET_REQUIRED: give the exact visible label from screen inspection."
    if player is None or not callable(getattr(player, "show_guidance_target", None)):
        return "GUIDANCE_UNAVAILABLE: the desktop overlay is not connected."

    try:
        from core import screenview
        from core.appidentity import fold

        view = screenview.look(allow_ocr=False)
        if view.degraded or view.source != "uia":
            reason = view.reason or "Windows UI Automation did not return a reliable control tree"
            return (
                f"SCREEN_UNAVAILABLE: {reason}. No target was highlighted. "
                "Use a screenshot or the application's own accessible controls instead."
            )
        hits = view.find(
            target_text, role=role, interactable_only=True, limit=12
        )
        exact = [element for element in hits if fold(element.label) == fold(target_text)]
        if len(exact) != 1:
            candidates = [element.label[:70] for element in hits[:6]]
            if not exact:
                return (
                    f"TARGET_NOT_FOUND: no enabled visible control exactly matches "
                    f"{target_text!r}. Candidates: {candidates}. Nothing was highlighted."
                )
            return (
                f"AMBIGUOUS_TARGET: {target_text!r} matches {len(exact)} enabled controls. "
                "Specify a more precise label or role. Nothing was highlighted."
            )
        element = exact[0]
        if not element.enabled or element.width <= 0 or element.height <= 0:
            return "TARGET_NOT_ACTIONABLE: the exact control is disabled or has no usable bounds."

        from core.guidance import set_target
        current = set_target(
            element.rect, element.label, app=view.app, title=view.title,
            pid=view.pid, step=step, role=element.role,
        )
        player.show_guidance_target(current.rect, current.label, current.step)
        return (
            f"TARGET_HIGHLIGHTED: step {step}, exact {element.role} "
            f"{element.label!r} in {view.app!r}. A glowing frame marks its current "
            "Windows UI Automation bounds. The frame does not click the application. "
            "Speak the instruction, then call wait_for_guidance_click before advancing."
        )
    except Exception as exc:
        try:
            from core.guidance import clear_target
            clear_target()
            player.clear_guidance_target()
        except Exception:
            pass
        return f"GUIDANCE_FAILED: {type(exc).__name__}: {str(exc)[:180]}"


TOOL = {
    "name": "highlight_screen_target",
    "description": (
        "Highlight one exact control on the REAL Windows desktop with an animated, "
        "click-through teal frame and numbered caption. First inspect the screen or "
        "use an exact label already returned by screen_perception. The label must resolve "
        "to exactly one enabled UI Automation control in a fresh foreground-window scan; "
        "fuzzy matches, OCR text, guessed coordinates, and duplicate labels are refused. "
        "After speaking the current instruction, call wait_for_guidance_click to wait "
        "for the user's real left click inside that exact rectangle. Re-resolve the next "
        "target from a fresh screen view after every click. The frame never clicks for the user."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "target": {"type": "STRING", "description": "Exact visible accessible label of the control."},
            "role": {"type": "STRING", "description": "Optional exact UIA role filter, e.g. button, link, edit."},
            "step": {"type": "INTEGER", "description": "Number shown beside the target, 1 to 99."},
        },
        "required": ["target"],
    },
    "handler": highlight_screen_target,
    "tier": "core",
    "brief": "Highlight one exact live desktop control for a guided step.",
}
