"""Semantic screen perception and guarded interaction for Jarvis.

The model names a visible control; the accessibility layer resolves it from a
fresh screen snapshot. Coordinates are never accepted from the model.
"""
from __future__ import annotations

from core import screenact, screenview


def _fresh_view():
    view = screenview.look()
    if view.degraded or view.source not in {"uia", "ax", "atspi"}:
        reason = view.reason or "the accessibility tree is unavailable"
        return None, (
            f"SCREEN_UNAVAILABLE: {reason}. No interaction was attempted. "
            "Bring the target application to the foreground and try again."
        )
    return view, ""


def _resolve(view, target: str, role: str = "", *, interactable: bool = False):
    target = str(target or "").strip()
    if not target:
        return None, "TARGET_REQUIRED: provide the visible control's exact label."
    hits = view.find(target, role=role, interactable_only=interactable, limit=8)
    if not hits:
        return None, f"NOT_FOUND: no visible control matched {target!r}."
    # Only an exact, unique label is safe to act on. Fuzzy matches are useful
    # for discovery, never sufficient authority to click or type.
    from core.appidentity import fold
    exact = [el for el in hits if fold(el.label) == fold(target)]
    if len(exact) != 1:
        labels = [el.label[:80] for el in hits[:5]]
        return None, (
            f"AMBIGUOUS_TARGET: {target!r} did not resolve to one exact "
            f"control. Candidates: {labels}. Inspect the screen and specify "
            "a more precise label. Nothing was executed."
        )
    el = exact[0]
    if interactable and not el.interactable:
        return None, "NOT_INTERACTABLE: the matched control is not enabled."
    return el, ""


def screen_perception(parameters: dict, player=None, speak=None) -> str:
    """Inspect the foreground screen or interact with one exact UI element."""
    params = parameters or {}
    action = str(params.get("action", "inspect")).strip().lower()
    if action not in {"inspect", "click", "double_click", "right_click",
                      "type", "press", "scroll", "hover"}:
        return "INVALID_ACTION: use inspect, click, double_click, right_click, type, press, scroll or hover."

    if action == "inspect":
        view, error = _fresh_view()
        if error:
            return error
        payload = view.to_model_json()
        return (
            f"SCREEN_READ source={view.source} app={view.app!r} "
            f"title={view.title!r} elements={len(view.elements)} "
            f"scan_ms={view.scan_ms:.0f}\n{payload}"
        )

    view, error = _fresh_view()
    if error:
        return error

    target = str(params.get("target", "")).strip()
    role = str(params.get("role", "")).strip().lower()
    if action in {"click", "double_click", "right_click", "type", "hover"}:
        allowed_role = "edit" if action == "type" else role
        el, error = _resolve(
            view, target, allowed_role,
            interactable=action in {"click", "double_click", "right_click", "type", "hover"},
        )
        if error:
            return error
        if action == "type":
            if el.role != screenview.ROLE_EDIT:
                return "WRONG_CONTROL_TYPE: text may only be entered into a visible edit field."
            if el.protected:
                return "PROTECTED_FIELD: Jarvis will not type into password or protected fields."
            text = str(params.get("text", ""))
            if len(text) > 4000:
                return "TEXT_TOO_LONG: maximum 4000 characters per operation."
            result = screenact.type_text(
                text, target=el, clear_first=bool(params.get("clear_first", False))
            )
        elif action == "hover":
            result = screenact.hover(el)
        else:
            clicks = 2 if action == "double_click" else 1
            button = "right" if action == "right_click" else "left"
            result = screenact.click(el, button=button, clicks=clicks)
    elif action == "press":
        key = str(params.get("key", "")).strip()
        if not key:
            return "KEY_REQUIRED: specify a key or key combination."
        result = screenact.press(key)
    else:  # scroll
        direction = str(params.get("direction", "down")).lower()
        if direction not in {"up", "down", "left", "right"}:
            return "INVALID_DIRECTION: use up, down, left or right."
        amount = max(1, min(10, int(params.get("amount", 3))))
        el = None
        if target:
            el, error = _resolve(view, target, role, interactable=False)
            if error:
                return error
        result = screenact.scroll(direction, amount=amount, target=el)

    if not result.ok:
        return f"ACTION_FAILED: {result}"
    # A successful input API call proves delivery, not that the application
    # accepted the operation. A caller may supply expect_text for a fresh,
    # explicit postcondition check.
    expect_text = str(params.get("expect_text", "")).strip()
    if expect_text:
        after = screenview.wait_stable(timeout_s=3.0)
        if after.contains_text(expect_text):
            return f"ACTION_DELIVERED_AND_VERIFIED: {result}. Visible postcondition found: {expect_text!r}."
        return f"ACTION_DELIVERED_BUT_UNVERIFIED: {result}. Expected visible text {expect_text!r} was not found."
    return (
        f"ACTION_DELIVERED_NOT_VERIFIED: {result}. The input was sent, "
        "but the application-level result has not been confirmed."
    )


TOOL = {
    "name": "screen_perception",
    "description": (
        "Read the current foreground application through Windows accessibility "
        "and interact with visible controls by exact label. Use action=inspect "
        "first to see visible controls. If inspection returns SCREEN_UNAVAILABLE, do not give up: "
        "use screen_process with angle='screen' to inspect the actual screenshot, then use "
        "computer_control action='screen_find' or 'screen_click' to locate a described visual target. "
        "If JARVIS is covering the desktop, minimize only JARVIS first. Then click/double_click/right_click, "
        "type into a named edit field, press a key, scroll, or hover. Every "
        "interaction takes a fresh screen snapshot and requires one unique exact "
        "control label; never invent coordinates. Password fields are blocked. "
        "For actions that matter, provide expect_text to verify a visible "
        "postcondition. Without it, report input delivered but NOT verified."
    ),
    "brief": "Reads the current screen and interacts with visible controls by exact label, never guessed coordinates.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "inspect | click | double_click | right_click | type | press | scroll | hover"},
            "target": {"type": "STRING", "description": "Exact visible label of the control, as returned by inspect"},
            "role": {"type": "STRING", "description": "Optional role filter, e.g. button, link, edit"},
            "text": {"type": "STRING", "description": "Text to enter when action=type"},
            "clear_first": {"type": "BOOLEAN", "description": "Clear the named edit field before typing; default false"},
            "key": {"type": "STRING", "description": "Key or chord, e.g. enter or ctrl+l"},
            "direction": {"type": "STRING", "description": "Scroll direction: up, down, left, right"},
            "amount": {"type": "INTEGER", "description": "Scroll amount from 1 to 10"},
            "expect_text": {"type": "STRING", "description": "Optional visible text that must appear after the action to count as verified"}
        },
        "required": ["action"]
    },
    "handler": screen_perception,
}
