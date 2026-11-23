"""Read-only health diagnostics for a local JARVIS installation.

This module deliberately reports states, never credentials, command lines,
file contents, or personal task text. It performs no repairs or restarts.
"""
from __future__ import annotations

import json
import os
import platform
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parents[1]
_REQUIRED_AGENTS = {"general", "researcher", "document_analyst", "study_coach", "quality_reviewer"}
_TERMINAL = {"done", "failed", "cancelled"}


def _check(name: str, label: str, status: str, detail: str) -> dict:
    return {"name": name, "label": label, "status": status, "detail": detail}


def _json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except FileNotFoundError:
        return None, "file missing"
    except Exception as exc:
        return None, type(exc).__name__


def _check_config(base: Path) -> tuple[dict, dict]:
    path = base / "config" / "api_keys.json"
    cfg, error = _json(path)
    if not isinstance(cfg, dict):
        return {}, _check("config", "Configuração", "critical",
                          "Arquivo de configuração ausente ou inválido; valores secretos não foram lidos.")
    providers = cfg.get("providers") if isinstance(cfg.get("providers"), dict) else {}
    mode = str(providers.get("mode") or "gemini").strip().lower()
    if mode == "gemini":
        status, detail = "ok", "Gemini Live está definido como cérebro principal."
    else:
        status, detail = "warning", "O modo principal não está definido como Gemini Live."
    return cfg, _check("config", "Cérebro principal", status, detail)


def _check_memory(base: Path) -> list[dict]:
    folder = base / "memory"
    primary = folder / "long_term.json"
    backup = folder / "long_term.json.bak"
    data, err = _json(primary)
    backup_data, backup_err = _json(backup)
    checks = []
    if isinstance(data, dict):
        if isinstance(backup_data, dict):
            checks.append(_check("memory", "Memória persistente", "ok",
                                 "Arquivo principal e cópia de segurança são JSON válidos."))
        else:
            checks.append(_check("memory", "Memória persistente", "warning",
                                 "Memória principal válida; cópia .bak ausente ou inválida."))
    elif isinstance(backup_data, dict):
        checks.append(_check("memory", "Memória persistente", "warning",
                             "Arquivo principal inválido; existe uma cópia .bak válida para recuperação."))
    else:
        checks.append(_check("memory", "Memória persistente", "critical",
                             "Arquivo principal e cópia .bak estão ausentes ou inválidos."))

    db = folder / "semantic_index.sqlite3"
    if not db.exists():
        checks.append(_check("semantic_index", "Índice semântico", "warning",
                             "Banco de memória semântica não encontrado."))
    else:
        try:
            uri = db.resolve().as_uri() + "?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=2.0)
            try:
                result = conn.execute("PRAGMA quick_check").fetchone()
            finally:
                conn.close()
            if result and result[0] == "ok":
                checks.append(_check("semantic_index", "Índice semântico", "ok",
                                     "Banco SQLite passou no quick_check em modo somente leitura."))
            else:
                checks.append(_check("semantic_index", "Índice semântico", "critical",
                                     "SQLite reportou inconsistência no índice semântico."))
        except Exception as exc:
            checks.append(_check("semantic_index", "Índice semântico", "warning",
                                 f"Não foi possível verificar o SQLite ({type(exc).__name__})."))
    return checks


def _check_agents(base: Path) -> dict:
    try:
        from core.tasks.agents import load
        profiles = load([base / "agents"], log=lambda *_: None)
        names = set(profiles)
        missing = sorted(_REQUIRED_AGENTS - names)
        if missing:
            return _check("agents", "Agentes especializados", "warning",
                          "Perfis ausentes: " + ", ".join(missing) + ".")
        return _check("agents", "Agentes especializados", "ok",
                      f"{len(names)} perfis válidos carregados; agentes essenciais presentes.")
    except Exception as exc:
        return _check("agents", "Agentes especializados", "critical",
                      f"Falha ao carregar perfis ({type(exc).__name__}).")


def _check_tasks(base: Path) -> tuple[dict, dict]:
    folder = base / "memory" / "tasks"
    counts: dict[str, int] = {}
    invalid = []
    task_ids: set[str] = set()
    total = 0
    if folder.exists():
        for path in folder.glob("*.json"):
            if path.name.endswith(".turns.json"):
                continue
            total += 1
            data, _ = _json(path)
            if not isinstance(data, dict) or not data.get("id") or not data.get("status"):
                invalid.append(path.name)
                continue
            task_ids.add(str(data["id"]))
            state = str(data["status"])
            counts[state] = counts.get(state, 0) + 1

    checkpoint_files = list(folder.glob("*.turns.json")) if folder.exists() else []
    invalid_checkpoints = []
    orphan_checkpoints = []
    for path in checkpoint_files:
        turns, _ = _json(path)
        task_id = path.name.split(".", 1)[0]
        if not isinstance(turns, list):
            invalid_checkpoints.append(path.name)
        if task_id not in task_ids:
            orphan_checkpoints.append(path.name)

    staged = sum(1 for p in folder.glob("*.tmp")) if folder.exists() else 0

    audit_path = folder / "audit.jsonl"
    audit_rows = 0
    invalid_audit_rows = 0
    if audit_path.exists():
        try:
            for line in audit_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    invalid_audit_rows += 1
                    continue
                if (not isinstance(row, dict)
                        or not {"t", "task_id", "kind", "event"}.issubset(row)):
                    invalid_audit_rows += 1
                else:
                    audit_rows += 1
        except Exception:
            invalid_audit_rows += 1

    active = sum(count for state, count in counts.items()
                 if state not in _TERMINAL and state != "paused")
    problems = []
    if invalid:
        problems.append(f"{len(invalid)} arquivo(s) de tarefa inválido(s)")
    if invalid_checkpoints:
        problems.append(f"{len(invalid_checkpoints)} checkpoint(s) inválido(s)")
    if orphan_checkpoints:
        problems.append(f"{len(orphan_checkpoints)} checkpoint(s) sem tarefa correspondente")
    if staged:
        problems.append(f"{staged} arquivo(s) temporário(s) aguardando reconciliação")
    if invalid_audit_rows:
        problems.append(f"{invalid_audit_rows} linha(s) inválida(s) no diário de auditoria")
    if problems:
        status = "warning"
        detail = "; ".join(problems) + "."
    else:
        status = "ok"
        detail = (f"{total} tarefas legíveis; {active} em fila/execução e "
                  f"{counts.get('paused', 0)} pausadas; {len(checkpoint_files)} checkpoints válidos; "
                  f"{audit_rows} registros de auditoria íntegros.")
    snapshot = {
        "total": total, "by_status": counts, "active": active,
        "invalid_files": len(invalid), "staged_files": staged,
        "checkpoint_files": len(checkpoint_files),
        "invalid_checkpoints": len(invalid_checkpoints),
        "orphan_checkpoints": len(orphan_checkpoints),
        "audit_rows": audit_rows, "invalid_audit_rows": invalid_audit_rows,
    }
    return snapshot, _check("tasks", "Fila e checkpoints", status, detail)


def _check_worker(base: Path) -> dict:
    memory = base / "memory"
    pid_path = memory / "task_worker.pid"
    if not pid_path.exists():
        return _check("worker", "Worker separado", "ok",
                      "Nenhum worker separado ativo; isso é normal quando o JARVIS está acordado.")
    try:
        pid = int(pid_path.read_text(encoding="ascii").strip())
    except Exception:
        return _check("worker", "Worker separado", "warning",
                      "Marcador de PID existe, mas não contém um PID válido.")
    try:
        import psutil
        if psutil.pid_exists(pid):
            return _check("worker", "Worker separado", "ok",
                          "Worker em segundo plano está registrado e o processo existe.")
        return _check("worker", "Worker separado", "warning",
                      "Marcador de PID aponta para um processo que não está mais ativo.")
    except Exception:
        return _check("worker", "Worker separado", "info",
                      "PID registrado; verificação do processo indisponível nesta instalação.")


def _check_startup(base: Path, platform_name: str | None = None,
                   environ: dict | None = None) -> list[dict]:
    os_name = platform_name or platform.system()
    if os_name != "Windows":
        return [_check("startup", "Inicialização do Windows", "info",
                       "Verificação disponível somente no Windows.")]
    env = environ if environ is not None else os.environ
    checks = []
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            command, _ = winreg.QueryValueEx(key, "JARVIS_AI")
        command_text = str(command or "").lower()
        native = base / "wake_native" / "build" / "JarvisWakeNative.exe"
        hidden_launcher = base / "wake_native" / "launch_hidden.vbs"
        packaged_wake = base / "JARVIS-Wake.exe"
        if ("launch_hidden.vbs" in command_text and "wscript.exe" in command_text
                and hidden_launcher.is_file() and native.is_file()):
            checks.append(_check("wake_startup", "Detector Hey JARVIS", "ok",
                                 "Entrada usa o lançador invisível; o executável nativo não abre terminal."))
        elif ("jarvis-wake.exe" in command_text and packaged_wake.is_file()):
            checks.append(_check("wake_startup", "Detector Hey JARVIS", "ok",
                                 "Daemon empacotado com inicialização sem janela de console."))
        elif "jarviswakenative.exe" in command_text and native.is_file():
            checks.append(_check("wake_startup", "Detector Hey JARVIS", "warning",
                                 "Entrada ainda inicia diretamente o executável Console; pode abrir terminal."))
        else:
            checks.append(_check("wake_startup", "Detector Hey JARVIS", "warning",
                                 "Entrada de inicialização ou executável de wake não confere."))
    except Exception:
        checks.append(_check("wake_startup", "Detector Hey JARVIS", "warning",
                             "Não foi possível confirmar a entrada JARVIS_AI no Registro."))
    appdata = str(env.get("APPDATA") or "").strip()
    script = (Path(appdata) / "Microsoft" / "Windows" / "Start Menu" /
              "Programs" / "Startup" / "OmniRoute.vbs") if appdata else None
    cfg, _ = _json(base / "config" / "api_keys.json")
    providers = cfg.get("providers") if isinstance(cfg, dict) and isinstance(cfg.get("providers"), dict) else {}
    coding = str(providers.get("coding") or "").lower()
    if "omniroute" in coding:
        ok = bool(script and script.is_file())
        checks.append(_check("omniroute_startup", "OmniRoute no login",
                             "ok" if ok else "warning",
                             "Atalho de inicialização encontrado." if ok else
                             "OmniRoute está selecionado para programação, mas o atalho de inicialização não foi encontrado."))
    else:
        checks.append(_check("omniroute_startup", "OmniRoute no login", "info",
                             "OmniRoute não está selecionado como provedor de programação."))
    return checks


def _probe_json(url: str, timeout: float = 1.2):
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        body = response.read(256_000)
        return response.status, json.loads(body.decode("utf-8", errors="replace"))


def _check_local_services(cfg: dict, base: Path, enabled: bool) -> list[dict]:
    if not enabled:
        return []
    checks = []
    providers = cfg.get("providers") if isinstance(cfg.get("providers"), dict) else {}
    coding = str(providers.get("coding") or "").lower()
    if "omniroute" in coding:
        try:
            status, body = _probe_json("http://127.0.0.1:20128/api/monitoring/health")
            healthy = status == 200 and (not isinstance(body, dict) or
                                         body.get("status") in (None, "healthy", "ok"))
            checks.append(_check("omniroute", "OmniRoute local",
                                 "ok" if healthy else "warning",
                                 "Endpoint local respondeu." if healthy else
                                 "Endpoint respondeu, mas não confirmou estado saudável."))
        except Exception as exc:
            checks.append(_check("omniroute", "OmniRoute local", "warning",
                                 f"Endpoint local indisponível ({type(exc).__name__})."))
    else:
        checks.append(_check("omniroute", "OmniRoute local", "info",
                             "Não configurado como provedor de programação."))

    # Exam Lab uses Gemini and configured remote vision providers only.
    exam_plugin = base / "plugins" / "exam_lab.py"
    if exam_plugin.exists():
        checks.append(_check(
            "exam_cloud", "Exam Lab · IA na nuvem", "info",
            "Extração e segunda revisão usam provedores remotos; nenhum serviço Ollama local é necessário.",
        ))
    return checks


def _check_runtime(base: Path, enabled: bool) -> list[dict]:
    if not enabled:
        return []
    try:
        import psutil
        current = Path(str(base)).resolve()
        found = False
        for proc in psutil.process_iter(["name", "exe"]):
            try:
                name = (proc.info.get("name") or "").lower()
                exe = str(proc.info.get("exe") or "").lower()
                if name == "jarvis.exe" or (name == "pythonw.exe" and str(current).lower() in exe):
                    found = True
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        checks = [_check("jarvis_process", "Aplicativo JARVIS", "ok" if found else "warning",
                         "Processo do JARVIS encontrado." if found else
                         "Não encontrei o processo principal do JARVIS nesta máquina.")]
        mem = psutil.virtual_memory()
        checks.append(_check("system_memory", "Memória RAM", "warning" if mem.percent >= 90 else "ok",
                             f"{mem.percent:.0f}% em uso ({mem.available / 1024**3:.1f} GB disponíveis)."))
        return checks
    except Exception as exc:
        return [_check("runtime", "Estado do computador", "info",
                       f"Monitoramento indisponível ({type(exc).__name__}).")]


def collect_health(base_dir: str | Path | None = None, *,
                   platform_name: str | None = None,
                   environ: dict | None = None,
                   probe_services: bool = True,
                   include_runtime: bool = True) -> dict:
    """Return a local-only health snapshot. No files are changed."""
    base = Path(base_dir or BASE_DIR).resolve()
    cfg, config_check = _check_config(base)
    task_data, task_check = _check_tasks(base)
    checks = [config_check, *_check_memory(base), _check_agents(base),
              task_check, _check_worker(base)]
    checks.extend(_check_startup(base, platform_name=platform_name, environ=environ))
    checks.extend(_check_local_services(cfg, base, probe_services))
    checks.extend(_check_runtime(base, include_runtime))
    statuses = {item["status"] for item in checks}
    overall = "critical" if "critical" in statuses else (
        "attention" if "warning" in statuses else "healthy")
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "overall": overall,
        "task_data": task_data,
        "checks": checks,
    }


def format_health(snapshot: dict, *, compact: bool = False) -> str:
    """Human-readable report; deliberately omits raw paths and sensitive config."""
    labels = {"healthy": "SAUDÁVEL", "attention": "PRECISA DE ATENÇÃO",
              "critical": "CRÍTICO"}
    lines = [f"Diagnóstico JARVIS: {labels.get(snapshot.get('overall'), 'INDEFINIDO')}"]
    task_data = snapshot.get("task_data") or {}
    if task_data:
        statuses = task_data.get("by_status") or {}
        bits = [f"{count} {state}" for state, count in sorted(statuses.items())]
        lines.append("Fila: " + (", ".join(bits) if bits else "vazia"))
    for item in snapshot.get("checks") or []:
        if compact and item.get("status") == "ok":
            continue
        marker = {"ok": "OK", "warning": "ATENÇÃO", "critical": "CRÍTICO",
                  "info": "INFO"}.get(item.get("status"), "INFO")
        lines.append(f"{marker} — {item.get('label')}: {item.get('detail')}")
    lines.append("Verificação somente de leitura; nenhuma chave ou token foi exibido.")
    return "\n".join(lines)
