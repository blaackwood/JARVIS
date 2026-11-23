"""Human-manageable authorization policy for Jarvis actions."""
from __future__ import annotations

from core import outcome


def authorization(parameters: dict, player=None) -> str:
    from core import authorization as policy
    from core import confirm

    args = dict(parameters or {})
    action = str(args.get("action") or "status").strip().lower()
    if action == "status":
        current = policy.get_policy()["classes"]
        return "\n".join(
            f"{name}: {decision} — {policy.CLASS_LABELS.get(name, name)}"
            for name, decision in current.items()
        )
    if action != "set":
        return outcome.failed("authorization", "action must be status or set")

    action_class = str(args.get("class") or "").strip()
    decision = str(args.get("decision") or "").strip().lower()
    if action_class not in policy.CLASS_LABELS:
        return outcome.failed("authorization", "unknown authorization class")
    if decision not in ("allow", "confirm", "deny"):
        return outcome.failed("authorization", "decision must be allow, confirm or deny")
    if confirm.pending_title():
        return outcome.ask("authorization", "another confirmation is already pending")

    return confirm.request(
        key="authorization_policy",
        title="Change Jarvis authorization policy",
        detail=(f"Class: {policy.CLASS_LABELS[action_class]} | New rule: {decision}. "
                "This rule will be saved and applied to future actions."),
        run=lambda: (policy.set_rule(action_class, decision) and
                     f"Authorization rule updated: {action_class} = {decision}."),
    )


TOOL = {
    "name": "authorization",
    "description": (
        "Manage Jarvis action authorization. action=status shows all policy classes. "
        "action=set changes one class; class must be one of read_only, reversible_change, "
        "persistent_automation, destructive_change, external_commitment, security_bypass, "
        "credential_exposure, unknown_high_impact. decision must be allow, confirm or deny. "
        "Every policy change requires the human to confirm on the Jarvis HUD; never claim "
        "the change was saved before confirmation."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["status", "set"]},
            "class": {"type": "STRING"},
            "decision": {"type": "STRING", "enum": ["allow", "confirm", "deny"]},
        },
    },
    "handler": authorization,
    "tier": "core",
    "brief": "View or change action authorization rules; policy changes require human HUD confirmation.",
}
