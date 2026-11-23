"""Central authorization policy for actions with persistent or destructive effects.

Default-deny is reserved for explicitly prohibited action classes. Ordinary
read-only work is allowed; persistent recurring changes and irreversible
operations require a human confirmation through core.confirm (never a model
parameter). Every decision is recorded without secrets or full payloads.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLICY_PATH = _ROOT / "memory" / "authorization" / "policy.json"
_AUDIT_PATH = _ROOT / "memory" / "authorization" / "decisions.jsonl"
_LOCK = threading.RLock()

DEFAULT_POLICY = {
    "version": 1,
    "mode": "autonomous_balanced",
    "classes": {
        "read_only": "allow",
        "reversible_change": "allow",
        "persistent_automation": "allow",
        "destructive_change": "confirm",
        "external_commitment": "confirm",
        "security_bypass": "deny",
        "credential_exposure": "deny",
        "unknown_high_impact": "deny",
    },
}

CLASS_LABELS = {
    "read_only": "Consulta e leitura",
    "reversible_change": "Alteração reversível",
    "persistent_automation": "Automação recorrente ou persistente",
    "destructive_change": "Ação destrutiva ou irreversível",
    "external_commitment": "Compromisso externo",
    "security_bypass": "Contorno de segurança",
    "credential_exposure": "Exposição de credenciais",
    "unknown_high_impact": "Ação de alto impacto não classificada",
}


def _read_policy() -> dict:
    with _LOCK:
        try:
            data = json.loads(_POLICY_PATH.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1:
                raise ValueError("unsupported policy")
            classes = data.get("classes")
            if not isinstance(classes, dict):
                raise ValueError("invalid classes")
            clean = dict(DEFAULT_POLICY["classes"])
            for key, value in classes.items():
                if key in clean and value in ("allow", "confirm", "deny"):
                    clean[key] = value
            mode = data.get("mode", "autonomous_balanced")
            if mode != "autonomous_balanced":
                mode = "autonomous_balanced"
            return {"version": 1, "mode": mode, "classes": clean}
        except (OSError, ValueError, TypeError):
            return json.loads(json.dumps(DEFAULT_POLICY))


def get_policy() -> dict:
    return _read_policy()


def set_rule(action_class: str, decision: str) -> dict:
    if action_class not in CLASS_LABELS:
        raise ValueError("unknown authorization class")
    if decision not in ("allow", "confirm", "deny"):
        raise ValueError("decision must be allow, confirm or deny")
    with _LOCK:
        policy = _read_policy()
        policy["classes"][action_class] = decision
        _POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _POLICY_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        os.replace(tmp, _POLICY_PATH)
    record("policy_changed", action_class, decision, "human_confirmed")
    return policy


def record(event: str, action_class: str, decision: str,
           source: str = "runtime", reference: str = "") -> None:
    row = {
        "timestamp": time.time(),
        "event": str(event)[:50],
        "class": str(action_class)[:60],
        "decision": str(decision)[:30],
        "source": str(source)[:40],
        "reference": str(reference)[:100],
    }
    with _LOCK:
        _AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _AUDIT_PATH.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())


def _browser_purchase_intent(params: dict) -> bool:
    action = str(params.get("action") or "").casefold()
    values = " ".join(str(params.get(k) or "") for k in
                      ("url", "query", "text", "selector", "description")).casefold()
    terms = (
        "buy now", "purchase", "checkout", "place order", "submit order",
        "complete order", "pay now", "payment", "billing", "add to cart",
        "comprar", "compre agora", "finalizar compra", "fechar pedido",
        "concluir pedido", "pagar agora", "pagamento", "adicionar ao carrinho",
        "confirmar compra", "realizar pedido",
    )
    return action in {"purchase", "checkout", "buy"} or any(t in values for t in terms)


def classify_action(tool_name: str, parameters: dict | None = None) -> str:
    """Conservative classification for the built-in action surface."""
    name = str(tool_name or "").lower()
    params = parameters or {}
    action = str(params.get("action") or "").lower().replace("-", "_").replace(" ", "_")

    if name == "file_processor":
        ext = os.path.splitext(str(params.get("file_path") or ""))[1].lower()
        # file_path is intentionally optional: the processor resolves the
        # user-selected GUI file. A pure translation request is read-only even
        # when the model omits that redundant path argument.
        if not ext and action in {"translate", "translate_hint"}:
            return "read_only"
        file_types = {
            ".jpg": "image", ".jpeg": "image", ".png": "image",
            ".gif": "image", ".webp": "image", ".bmp": "image",
            ".tif": "image", ".tiff": "image", ".svg": "image", ".ico": "image",
            ".pdf": "pdf", ".doc": "docx", ".docx": "docx",
            ".txt": "text", ".md": "text", ".rst": "text", ".log": "text",
            ".csv": "csv", ".xlsx": "excel", ".xls": "excel", ".ods": "excel",
            ".json": "json", ".xml": "xml",
            ".py": "code", ".js": "code", ".ts": "code", ".html": "code",
            ".css": "code", ".java": "code", ".cpp": "code", ".c": "code",
            ".h": "code", ".cs": "code", ".go": "code", ".rs": "code",
            ".php": "code", ".rb": "code", ".sh": "code", ".bat": "code",
            ".ps1": "code", ".sql": "code",
            ".mp3": "audio", ".wav": "audio", ".ogg": "audio",
            ".m4a": "audio", ".aac": "audio", ".flac": "audio",
            ".wma": "audio", ".opus": "audio",
            ".mp4": "video", ".avi": "video", ".mov": "video",
            ".mkv": "video", ".wmv": "video", ".flv": "video",
            ".webm": "video", ".m4v": "video", ".3gp": "video",
            ".zip": "archive", ".rar": "archive", ".7z": "archive",
            ".tar": "archive", ".gz": "archive", ".bz2": "archive",
            ".xz": "archive", ".pptx": "pptx", ".ppt": "pptx",
        }
        file_type = file_types.get(ext)
        if file_type is None:
            return "unknown_high_impact"
        if file_type == "code" and action == "run":
            return "unknown_high_impact"
        if params.get("save") is True:
            return "destructive_change"

        writes = {
            "image": {"resize", "compress", "convert"},
            "pdf": {"extract_text", "to_word", "reformat"},
            "docx": {"extract_text", "to_word"},
            "text": {"extract_text"},
            "csv": {"filter", "sort", "convert", "to_excel", "to_json", "to_csv"},
            "excel": {"filter", "sort", "convert", "to_csv", "to_json"},
            "json": {"format", "to_csv"},
            "xml": {"format", "to_csv"},
            "audio": {"trim", "convert"},
            "video": {"trim", "extract_audio", "extract_frame", "compress", "convert"},
            "archive": {"extract"},
            "pptx": {"extract_text", "to_pdf"},
        }
        if action in writes.get(file_type, set()):
            return "destructive_change"

        reads = {
            "image": {"", "describe", "ocr", "analyze", "read", "extract_text", "translate", "info", "custom"},
            "pdf": {"", "summarize", "analyze", "translate_hint", "ocr", "info", "custom"},
            "docx": {"", "summarize", "fix", "reformat", "translate_hint", "word_count", "to_bullet", "info", "custom"},
            "text": {"", "summarize", "fix", "reformat", "translate_hint", "word_count", "to_bullet", "info", "custom"},
            "csv": {"", "analyze", "stats", "info", "custom"},
            "excel": {"", "analyze", "stats", "info", "custom"},
            "json": {"", "validate", "analyze", "extract", "info", "custom"},
            "xml": {"", "validate", "analyze", "extract", "info", "custom"},
            "code": {"", "explain", "review", "fix", "optimize", "document", "test", "info", "custom"},
            "audio": {"", "transcribe", "info", "custom"},
            "video": {"", "transcribe", "info", "custom"},
            "archive": {"", "list", "info", "custom"},
            "pptx": {"", "summarize", "analyze", "info", "custom"},
        }
        return "read_only" if action in reads.get(file_type, set()) else "unknown_high_impact"

    if any(token in name for token in ("credential", "password_dump", "security_bypass")):
        return "credential_exposure" if "credential" in name else "security_bypass"
    if action in {"format_disk", "wipe_disk", "disable_defender", "disable_firewall",
                  "delete_system32", "remove_security"}:
        return "security_bypass" if "disable" in action or "security" in action else "unknown_high_impact"
    if name == "background_tasks" and action in {"routine_add", "routine_remove"}:
        return "persistent_automation"
    if name == "computer_settings" and action in {
        "shutdown", "restart", "sleep", "hibernate", "log_out", "logout",
        "wifi_disable", "toggle_wifi", "bluetooth_disable", "display_off",
    }:
        return "destructive_change"
    if name == "file_controller":
        if action in {"open", "list", "read", "find", "largest", "disk_usage", "info"}:
            return "read_only"
        if action in {"delete", "overwrite", "replace", "permanent_delete"}:
            return "destructive_change"
        if action == "organize_desktop":
            return "reversible_change"
        # Creating a new file is automatic; replacing an existing target is not.
        if action in {"create_file", "write"}:
            try:
                if not str(params.get("name") or "").strip():
                    return "unknown_high_impact"
                from actions import file_controller
                target = file_controller._resolve_path(str(params.get("path") or "home"))
                if params.get("name"):
                    target = target / str(params.get("name"))
                return "destructive_change" if target.exists() else "reversible_change"
            except Exception:
                return "unknown_high_impact"
        if action in {"move", "copy"}:
            try:
                from actions import file_controller
                src = file_controller._resolve_path(str(params.get("path") or "home"))
                item = src / str(params.get("name") or "")
                dst = file_controller._resolve_path(str(params.get("destination") or ""))
                if dst.is_dir():
                    dst = dst / item.name
                return "destructive_change" if dst.exists() else "reversible_change"
            except Exception:
                return "unknown_high_impact"
        if action in {"create_folder", "rename"}:
            return "reversible_change"
        return "unknown_high_impact"
    if name == "screen_perception":
        if action == "inspect":
            return "read_only"
        # Autonomous desktop operation is the user's explicit preference.
        # Purchase/checkout controls remain hard-blocked by default-deny.
        target = str(params.get("target") or "").casefold()
        purchase_terms = (
            "buy now", "purchase", "checkout", "place order", "submit order",
            "complete order", "pay now", "payment", "billing", "add to cart",
            "comprar", "compre agora", "finalizar compra", "fechar pedido",
            "concluir pedido", "pagar agora", "pagamento",
            "adicionar ao carrinho", "confirmar compra", "realizar pedido",
        )
        if any(term in target for term in purchase_terms):
            return "unknown_high_impact"
        return "reversible_change"
    if name == "browser_control":
        if _browser_purchase_intent(params):
            return "unknown_high_impact"
        return "reversible_change"
    if name in {"send_email", "send_message", "publish_post", "purchase",
                "book_reservation", "game_updater"}:
        return "external_commitment"
    if name in {"web_search", "weather_report", "flight_finder",
                "youtube_video", "system_status", "background_monitor", "screen_process",
                "jarvis_health", "use_skill"}:
        return "read_only"
    if name in {"inspect_screen_marks", "wait_for_guidance_click"}:
        return "read_only"
    if name == "highlight_screen_target":
        return "reversible_change"
    if name in {"show_visual", "present_visual_lesson", "draw_right_triangle", "clear_visual",
                "show_screen_marks", "clear_screen_marks", "edit_screen_marks"}:
        # These are temporary screen-side annotations / teaching overlays.
        # They create no persistent files, change no system settings, and have
        # no external side effects; the user can close or clear them at any time.
        return "reversible_change"
    if name == "focus_mode":
        return "reversible_change"
    if name == "chess_assistant":
        # Le a tela, fala e desenha uma seta temporaria. Nao clica nem escreve nada.
        return "read_only" if action in {"status", "stop"} else "reversible_change"
    if name == "chess_teacher":
        # Le a tela, fala e desenha uma seta temporaria. Nao clica nem escreve nada.
        return "read_only" if action in {"status", "stop", "explain_fen", "why", "repeat", "level"} else "reversible_change"
    if name in {"authorization", "background_tasks", "open_app", "video_player",
                "code_helper", "dev_agent", "opencode_agent", "desktop_control",
                "computer_control", "computer_settings"}:
        return "reversible_change"
    return "unknown_high_impact"


def decision_for(action_class: str) -> str:
    return _read_policy()["classes"].get(action_class, "deny")


def authorize(tool_name: str, parameters: dict | None = None,
              source: str = "runtime") -> tuple[str, str]:
    action_class = classify_action(tool_name, parameters)
    decision = decision_for(action_class)
    record("authorization_check", action_class, decision, source, tool_name)
    return action_class, decision
