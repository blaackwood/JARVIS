"""Bridge between JARVIS task events/approvals and the official Codex App Server."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

from codex_runtime import CodexAppServer, CodexProtocolError


PROVIDER_ID = "openai_codex"
PROVIDER_LABEL = "OpenAI Codex"
WORKSPACE_MODE = "Acesso ao workspace"
READ_ONLY_MODE = "Somente plano"


def _codex_execution_settings(mode):
    """Return the approval policy and legacy sandbox mode for a bounded Codex thread."""
    if mode == READ_ONLY_MODE:
        return "never", "read-only"
    # Ask mode keeps interactive approvals. Workspace mode uses on-request at the
    # protocol layer, then the JARVIS approval broker auto-accepts only safe in-root
    # requests. This keeps workspace-write enabled without surfacing a prompt per file.
    return "on-request", "workspace-write"


def _codex_sandbox_policy(mode, workspace):
    """Build the explicit per-turn sandbox policy; never enable network or full access."""
    if mode == READ_ONLY_MODE:
        return {"type": "readOnly", "networkAccess": False}
    return {
        "type": "workspaceWrite",
        "writableRoots": [str(Path(workspace).resolve())],
        "networkAccess": False,
    }


_WEB_TASK_RE = re.compile(
    r"\b(site|website|web|webapp|web\s+app|frontend|front-end|"
    r"html|css|javascript|react|next\.js|vue|svelte|landing\s+page|"
    r"dashboard|p[aá]gina\s+web|interface\s+web|layout\s+web)\b",
    re.IGNORECASE,
)


def _is_web_frontend_task(text, attachments=()):
    """Detect web UI work so Codex can use the dedicated design/QA workflow."""
    if _WEB_TASK_RE.search(str(text or "")):
        return True
    for item in attachments or ():
        name = item[0] if isinstance(item, (tuple, list)) and item else item
        if re.search(r"\.(html?|css|scss|sass|less|jsx|tsx|vue|svelte)$",
                     str(name or ""), re.IGNORECASE):
            return True
    return False


def _select_reasoning_effort(model_info, web_task=False):
    """Choose a strong, practical effort for web work; preserve the model default otherwise."""
    entries = model_info.get("supportedReasoningEfforts") or []
    supported = []
    for entry in entries:
        value = entry.get("reasoningEffort") if isinstance(entry, dict) else entry
        if value and str(value) not in supported:
            supported.append(str(value))
    if not supported:
        return str(model_info.get("defaultReasoningEffort") or "medium")
    if web_task:
        # "max"/"ultra" can spend a long time in deliberation before producing
        # code. High is the default web balance; raise only when high is absent.
        for candidate in ("high", "xhigh", "max", "ultra", "medium", "low"):
            if candidate in supported:
                return candidate
    default = str(model_info.get("defaultReasoningEffort") or "medium")
    if default in supported:
        return default
    for candidate in ("medium", "high", "low", "xhigh", "max", "ultra"):
        if candidate in supported:
            return candidate
    return supported[0]


def _web_skill_inputs():
    """Return locally bundled, licensed design and browser-QA skills for web tasks."""
    project_root = Path(__file__).resolve().parents[1]
    candidates = (
        ("hallmark", project_root / ".agents" / "skills" / "hallmark" / "SKILL.md"),
        ("frontend-design", project_root / ".agents" / "skills" / "frontend-design" / "SKILL.md"),
        ("webapp-testing", project_root / ".agents" / "skills" / "webapp-testing" / "SKILL.md"),
    )
    return [
        {"type": "skill", "name": name, "path": str(skill_path)}
        for name, skill_path in candidates
        if skill_path.is_file()
    ]


def _web_workflow_directive():
    project_root = Path(__file__).resolve().parents[1]
    qa_script = project_root / "tools" / "jarvis_browser_qa.py"
    python_exe = str(Path(sys.executable).resolve())
    qa_check_command = '"%s" "%s" --check' % (python_exe, str(qa_script))
    qa_run_command = '"%s" "%s" --project-dir "<workspace>"' % (python_exe, str(qa_script))
    return (
        "\n\n[PROTOCOLO OBRIGATÓRIO DE CRIAÇÃO WEB — JARVIS WEB EXCELLENCE + HALLMARK / FIRST-PASS QUALITY]\n"
        "Esta solicitação envolve frontend. Invoque e siga $hallmark; "
        "use $frontend-design para direção visual e $webapp-testing para QA real no navegador.\n"
        "QA PLAYWRIGHT INTEGRADO: antes de depender de automação visual, execute " + qa_check_command +
        " para verificar Playwright e Chromium. Para auditar o projeto e gerar capturas desktop/mobile, "
        "execute " + qa_run_command + ". O comando usa core/browser_qa.py, vincula servidores locais "
        "somente a 127.0.0.1 e salva relatórios/capturas em uma pasta local de evidências. Não instala "
        "pacotes ou navegadores automaticamente; se o ambiente não estiver pronto, reporte o bloqueio "
        "e continue com os testes locais que forem seguros.\n"
        "REFERÊNCIA E PREFERÊNCIAS: procure referências fornecidas, decisões anteriores e versões que o usuário já escolheu ou elogiou nesta mesma linha de trabalho. Quando houver uma versão preferida, inspecione capturas e código/design tokens; preserve as preferências já definidas e não peça ao usuário para repeti-las.\n"
        "PAPEL DO HALLMARK: use-o como sistema de direção de arte, escolha de tema, composição, "
        "disciplina do hero e auditoria anti-design-genérico. Leia sua SKILL.md e as referências "
        "necessárias. Para novas páginas/sites, faça o pre-flight, infira audiência/uso/tom do briefing "
        "e do contexto e selecione uma direção visual coerente. Não faça as quatro perguntas padrão "
        "do Hallmark: JARVIS deve avançar com inferências razoáveis e perguntar somente se faltar "
        "um dado realmente impeditivo. Se o usuário pedir design customizado ou fornecer uma direção "
        "clara, respeite-a em vez de impor um tema sorteado.\n"
        "TEMA E FERRAMENTAS LOCAIS: quando for um novo site/página e não houver design.md ou tema "
        "explicitamente fixado, use theme.mjs deal/draw para explorar uma direção e theme.mjs scaffold "
        "quando compatível com a arquitetura. Use os scripts que acompanham .agents/skills/hallmark. "
        "Não presuma que Puppeteer está instalado. Verifique se Playwright e um navegador estão "
        "disponíveis antes do QA; use a dependência Playwright já declarada pelo projeto quando possível. "
        "Não instale dependências automaticamente. Rode sloplint.mjs --render quando o renderizador estiver "
        "disponível; se Puppeteer faltar, faça sloplint estático e use Playwright/webapp-testing para "
        "capturas desktop/tablet/mobile e inspeção visual.\n"
        "RESTRIÇÃO DE REDE: não execute theme.mjs photos, imagegen.mjs, downloads, Wikimedia, Together "
        "API, serviços externos ou quaisquer chamadas de rede para obter fotos/comps sem autorização "
        "específica do usuário. Não use o passo de comps que exige TOGETHER_API_KEY. Prefira assets "
        "fornecidos pelo usuário e recursos locais. SVG/CSS autoral é permitido quando o briefing pede "
        "mapas, diagramas, gráficos, ilustrações de produto ou quando isso é claramente melhor; não "
        "o use como preenchimento decorativo genérico. Nunca fabrique depoimentos, logos ou métricas.\n"
        "HIERARQUIA DE REGRAS: o pedido explícito do usuário, os fatos do produto, o design system "
        "existente, acessibilidade e funcionamento prevalecem sobre regras estéticas genéricas do "
        "Hallmark. Preserve exigências do briefing mesmo quando uma gate estilística discordar. "
        "Não force o limite de palavras do hero, proibição de eyebrow, formato de navegação, tema ou "
        "macroestrutura quando isso prejudicar a intenção do usuário. Registre exceções justificáveis; "
        "não falsifique um resultado limpo do sloplint.\n"
        "ESCOPO: para novo site/página de marketing, use o fluxo completo do Hallmark. Para dashboard, "
        "admin, ferramenta ou app em que o usuário trabalha, use --scope app e preserve o shell, a "
        "arquitetura e a familiaridade da categoria. Para correções pequenas em design existente, "
        "mantenha o sistema visual atual; não faça redesign completo sem pedido. Para redesign pedido "
        "explicitamente, use a branch redesign do Hallmark.\n"
        "PADRÃO DA PRIMEIRA ENTREGA: não mostre ao usuário um rascunho só porque o código compila. "
        "A primeira versão apresentada precisa parecer um produto coeso, completo e visualmente "
        "polido. Antes de programar, escreva critérios de aceite visuais/funcionais e planeje a "
        "composição em desktop, tablet e mobile (grid, hierarquia, espaçamento, tipografia, cor, "
        "proporção e comportamento responsivo).\n"
        "HERO-FIRST: construa a navegação e o hero primeiro. Se Puppeteer estiver instalado, rode "
        "sloplint --render --stage hero; em qualquer caso, capture o hero com Playwright local "
        "e inspecione a imagem antes de completar o restante. Depois implemente a página inteira, rode "
        "sloplint estático e --render se disponível, e gere capturas finais desktop/tablet/mobile. Um "
        "sloplint com FAIL/REFLEX é uma lista de achados para corrigir, não motivo para encerrar a tarefa. "
        "Se a invocação falhar por sintaxe/caminho, leia --help e corrija o comando; não confunda erro "
        "do comando com defeito do site. Corrija falhas concretas de acessibilidade, contraste, "
        "responsividade, tokens, overflow e consistência. Gates puramente opinativas podem ser "
        "justificadas quando o briefing ou o produto pedir algo diferente; não persiga zero artificialmente.\n"
        "REVISÃO AUTÔNOMA OBRIGATÓRIA: inspecione visualmente screenshots renderizados, não apenas "
        "código/DOM. Identifique os três problemas mais importantes (defeitos visuais ou de usabilidade) e corrija-os antes de entregar. "
        "Repita capturas e testes após correções. Use também Playwright/webapp-testing para fluxos "
        "funcionais, interações, console, exceções, rede e overflow nos viewports 1440x900, 768x1024 "
        "e 390x844. sloplint complementa, não substitui, Playwright nem o julgamento visual.\n"
        "HONESTIDADE E SEGURANÇA: se autorização, sandbox ou ferramenta impedir servidor, screenshot "
        "ou lint, não pare no silêncio e não afirme que passou; identifique o bloqueio e use uma "
        "alternativa local dentro do workspace quando segura. Nunca altere políticas globais de "
        "aprovação para evitar prompts. Não publique/deploy sem pedido. Preserve dados e escopo. "
        "Relate separadamente resultados funcionais, sloplint, inspeção visual, viewports e limitações.\n"
    )


def _plain_content(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(str(x.get("text") or "") for x in value if isinstance(x, dict))
    return str(value or "")


def _messages_fingerprint(messages):
    """Stable digest used to detect when another account changed this JARVIS conversation."""
    payload = json.dumps(messages or [], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _approval_result(t, request, stop, ctx, workspace_auto=False):
    """Present Codex permissions, or enforce the explicitly trusted workspace boundary."""
    method = str(request.get("method") or "")
    params = request.get("params") or {}
    network = params.get("networkApprovalContext") or {}
    is_file = method == "item/fileChange/requestApproval"
    is_permissions = method == "item/permissions/requestApproval"
    requested_permissions = params.get("permissions") or {}
    is_network = bool(network)
    command = str(params.get("command") or "").strip()
    cwd = str(params.get("cwd") or ctx["ws"]()).strip()
    grant_root = str(params.get("grantRoot") or "").strip()
    danger = bool(ctx["DANGER"].search(command))

    permission_paths = []
    network_request = requested_permissions.get("network") or {}
    if is_permissions:
        file_system = requested_permissions.get("fileSystem") or {}
        for key in ("read", "write"):
            for value in file_system.get(key) or []:
                permission_paths.append(str(value.get("path") if isinstance(value, dict) else value))
        for entry in file_system.get("entries") or []:
            value = entry.get("path") or {}
            permission_paths.append(str(value.get("path") or value.get("pattern") or value.get("value") or value))
        details = []
        if permission_paths:
            details.append("Caminhos: " + ", ".join(permission_paths[:8]))
        if network_request.get("enabled"):
            details.append("Acesso de rede adicional")
        title = "O Codex solicita permiss?es adicionais. Autorizar?"
        display_cmd = "\n".join(details) or str(params.get("reason") or "Permiss?es adicionais do Codex")[:1200]
        kind = "edit" if permission_paths else "cmd"
    elif is_network:
        host = str(network.get("host") or "destino externo")
        protocol = str(network.get("protocol") or "rede")
        title = "Permitir acesso de rede para %s (%s)?" % (host, protocol)
        display_cmd = "Acesso de rede: %s (%s)" % (host, protocol)
        kind = "cmd"
    elif is_file:
        title = "Permitir alteração de arquivos fora do acesso atual?"
        display_cmd = "Pasta solicitada: " + (grant_root or "não informada")
        kind = "edit"
    else:
        title = "O Codex precisa de autorização para executar um comando."
        display_cmd = command[:1200] or str(params.get("reason") or "Comando solicitado")[:1200]
        kind = "cmd"

    available = params.get("availableDecisions") or []
    available_text = json.dumps(available, ensure_ascii=False).lower()
    in_workspace = False
    try:
        if cwd:
            in_workspace = ctx["inside"](Path(cwd).resolve(), ctx["ws"]().resolve())
        if grant_root and is_file:
            in_workspace = in_workspace and ctx["inside"](Path(grant_root).resolve(), ctx["ws"]().resolve())
    except Exception:
        in_workspace = False
    can_session = (not is_permissions and "acceptforsession" in available_text and in_workspace and not danger)

    if workspace_auto:
        # This mode is intentionally non-interactive. Keep the sandbox boundary:
        # reject network, extra permission grants, dangerous commands and paths outside
        # the active workspace; accept ordinary work that stays inside it.
        outside_requested_path = False
        for raw in permission_paths:
            try:
                if not ctx["inside"](Path(raw).resolve(), ctx["ws"]().resolve()):
                    outside_requested_path = True
                    break
            except Exception:
                outside_requested_path = True
                break
        blocked_reason = None
        if is_network or network_request.get("enabled"):
            blocked_reason = "acesso de rede fora do modo workspace"
        elif outside_requested_path or not in_workspace:
            blocked_reason = "caminho fora do workspace autorizado"
        elif danger:
            blocked_reason = "comando classificado como destrutivo ou de alto risco"
        elif is_permissions and not permission_paths and not network_request:
            blocked_reason = "permissão adicional não reconhecida"
        if blocked_reason:
            ctx["emit"](t, {"t": "tool", "id": uuid.uuid4().hex[:8],
                            "name": "codex_workspace_guard", "label": "Ação bloqueada pelo limite do workspace",
                            "ok": False, "detail": blocked_reason})
            if is_permissions:
                return {"permissions": {}, "scope": "turn"}
            return {"decision": "decline"}
        if is_permissions:
            ctx["emit"](t, {"t": "tool", "id": uuid.uuid4().hex[:8],
                            "name": "codex_workspace_guard", "label": "Permissão limitada ao workspace",
                            "ok": True, "detail": "Somente caminhos dentro da pasta atual"})
            return {"permissions": requested_permissions, "scope": "turn"}
        ctx["emit"](t, {"t": "tool", "id": uuid.uuid4().hex[:8],
                        "name": "codex_workspace_guard", "label": "Ação autorizada no workspace",
                        "ok": True, "detail": "Sandbox ativo; sem acesso adicional fora da pasta"})
        return {"decision": "accept"}

    aid = uuid.uuid4().hex[:8]
    created = time.time()
    state = {"id": aid, "task_id": t["id"], "created_at": created,
             "expires_at": created + ctx["approval_ttl"], "status": "pending",
             "choice": 3, "note": "", "source": "codex"}
    if not ctx["save_approval_state"](aid, state):
        return {"decision": "decline"}
    local = {"ev": __import__("threading").Event(), "choice": 3, "note": "", "source": "codex"}
    ctx["asks"][aid] = local
    t["awaiting"] = True
    ctx["emit"](t, {"t": "ask", "id": aid, "title": title, "kind": kind,
                    "cmd": display_cmd, "danger": danger,
                    "always": "nesta sessão Codex" if can_session else None,
                    "scope": "session" if can_session else None})
    ctx["notify"]("Codex precisa de autorização", re.sub(r"\s+", " ", title)[:140])

    choice, note = 3, "pedido expirado"
    while True:
        current = ctx["asks"].get(aid)
        if current and current["ev"].wait(0.25):
            choice = int(current.get("choice") or 3)
            note = str(current.get("note") or "")
            break
        shared = ctx["load_approval_state"](aid)
        if shared and shared.get("status") in ("approved", "rejected", "cancelled", "expired"):
            choice = int(shared.get("choice") or 3)
            note = str(shared.get("note") or "")
            break
        if stop.is_set():
            choice, note = 3, "execução interrompida"
            break
        if time.time() >= state["expires_at"]:
            break

    ctx["asks"].pop(aid, None)
    t["awaiting"] = False
    choice = choice if choice in (1, 2) else 3
    if choice == 2 and can_session:
        decision = "acceptForSession"
    elif choice in (1, 2):
        decision = "accept"
        choice = 1
    else:
        decision = "cancel" if stop.is_set() else "decline"
    final_state = ctx["load_approval_state"](aid) or state
    final_state.update(status="completed" if choice in (1, 2) else "rejected",
                       choice=choice, note=note, resolved_at=time.time())
    ctx["save_approval_state"](aid, final_state)
    ctx["emit"](t, {"t": "asked", "id": aid, "choice": choice,
                    "scope": "session" if decision == "acceptForSession" else None})
    if is_permissions:
        # This RPC has a distinct response schema from command/file approvals.
        # Grant only the exact profile the user explicitly approved, for this turn.
        return {"permissions": requested_permissions if choice in (1, 2) else {}, "scope": "turn"}
    return {"decision": decision}


def _track_codex_path(t, raw_path, ctx, touched):
    if not raw_path:
        return
    try:
        full = Path(str(raw_path))
        if not full.is_absolute():
            full = ctx["ws"]() / full
        full = full.resolve()
        if full == ctx["ws"]().resolve() or not ctx["inside"](full, ctx["ws"]().resolve()):
            return
        if ctx["secret_names"].search(str(full)) or ".git" in full.parts:
            return
        ctx["track"](t, full)
        touched.add(str(full))
    except Exception:
        return


def _finalize_snapshots(t, touched, ctx):
    changed = False
    for raw in list(touched):
        try:
            full = Path(raw).resolve()
            key = str(full)
            if key not in t.get("changes", {}):
                continue
            record = t["changes"][key]
            if full.is_file():
                record["last_hash"] = ctx["disk_hash"](full)
            elif record.get("orig") is None:
                t["changes"].pop(key, None)
            else:
                # Keep a visible conflict for deleted files rather than offering an unsafe rollback.
                record["last_hash"] = "__deleted_by_codex__"
            changed = True
        except Exception:
            continue
    if changed:
        ctx["save"](t)
        ctx["emit"](t, {"t": "changes"})


def run_codex_agent(t, text, mode, atts, stop, ctx):
    """Run one turn in a persistent Codex thread and translate its events to JARVIS."""
    t0 = time.time()
    workspace = ctx["ws"]().resolve()
    task_files = (ctx["data"] / "task_files" / t["id"]).resolve()
    touched, text_parts, command_buffers = set(), [], {}
    turn_state = {"completed": False, "status": None, "error": None}
    account_id = str(ctx.get("codex_account_id") or "primary")
    account_home = Path(ctx.get("codex_home") or Path.home() / ".codex").resolve()
    thread_map = t.setdefault("codex_threads", {})
    thread_context_map = t.setdefault("codex_thread_context", {})
    previous_messages = list(t.get("messages") or [])
    context_fingerprint = _messages_fingerprint(previous_messages)
    thread_id = str(thread_map.get(account_id) or (t.get("codex_thread_id") if account_id == "primary" else "") or "")
    # A thread belongs to one Codex account. When another account (or provider)
    # adds turns to the shared JARVIS conversation, rebuild this account's Codex
    # thread from the latest saved transcript instead of resuming stale context.
    if thread_id and str(thread_context_map.get(account_id) or "") != context_fingerprint:
        thread_map.pop(account_id, None)
        thread_context_map.pop(account_id, None)
        if account_id == "primary":
            t.pop("codex_thread_id", None)
        thread_id = ""
    turn_id = ""
    codex = None

    def on_message(message):
        method = str(message.get("method") or "")
        params = message.get("params") or {}
        if method in ("item/commandExecution/requestApproval", "item/fileChange/requestApproval",
                      "item/permissions/requestApproval"):
            return _approval_result(t, message, stop, ctx, workspace_auto=(mode == WORKSPACE_MODE))
        if method == "item/started":
            item = params.get("item") or {}
            item_type, item_id = item.get("type"), str(item.get("id") or "")
            if item_type == "fileChange":
                for change in item.get("changes") or []:
                    _track_codex_path(t, change.get("path"), ctx, touched)
                if touched:
                    ctx["save"](t)
                names = ", ".join(str(c.get("path") or "arquivo") for c in item.get("changes") or [])[:500]
                ctx["emit"](t, {"t": "tool", "id": item_id, "name": "codex_file_change",
                                "label": "Alterando arquivos", "chip": names or "Alterações propostas",
                                "detail": "Codex aplicando alterações no workspace"})
            elif item_type == "commandExecution":
                command_buffers[item_id] = {"command": str(item.get("command") or "Comando do Codex"), "out": ""}
                ctx["emit"](t, {"t": "tool", "id": item_id, "name": "codex_command",
                                "label": "Executando comando", "chip": str(item.get("command") or "Comando")[:500],
                                "detail": str(item.get("cwd") or workspace)})
            elif item_type == "webSearch":
                ctx["emit"](t, {"t": "think", "d": "Pesquisando na web: %s " % str(item.get("query") or "")[:240]})
            elif item_type:
                ctx["emit"](t, {"t": "tool", "id": item_id or uuid.uuid4().hex[:8],
                                "name": "codex_" + re.sub(r"[^a-z0-9_]+", "_", str(item_type).lower()),
                                "label": str(item.get("title") or item.get("tool") or item_type)[:120],
                                "detail": "Atividade do Codex"})
        elif method == "item/commandExecution/outputDelta":
            item_id = str(params.get("itemId") or "")
            delta = str(params.get("delta") or "")
            if item_id in command_buffers and delta:
                command_buffers[item_id]["out"] = (command_buffers[item_id]["out"] + delta)[-12000:]
        elif method == "item/agentMessage/delta":
            delta = str(params.get("delta") or "")
            if delta:
                text_parts.append(delta)
                ctx["emit"](t, {"t": "text", "d": delta})
        elif method == "item/plan/delta":
            delta = str(params.get("delta") or "")
            if delta:
                ctx["emit"](t, {"t": "think", "d": delta})
        elif method == "item/reasoning/summaryTextDelta":
            delta = str(params.get("delta") or "")
            if delta:
                ctx["emit"](t, {"t": "think", "d": delta})
        elif method == "item/completed":
            item = params.get("item") or {}
            item_type, item_id = item.get("type"), str(item.get("id") or "")
            status = str(item.get("status") or "completed")
            if item_type == "fileChange":
                for change in item.get("changes") or []:
                    _track_codex_path(t, change.get("path"), ctx, touched)
                _finalize_snapshots(t, touched, ctx)
                ctx["emit"](t, {"t": "tool", "id": item_id, "name": "codex_file_change",
                                "label": "Alterações de arquivos", "ok": status == "completed",
                                "detail": "%s · %d arquivo(s)" % (status, len(item.get("changes") or []))})
            elif item_type == "commandExecution":
                buffer = command_buffers.pop(item_id, {})
                output = str(item.get("aggregatedOutput") or buffer.get("out") or "")[-3000:]
                ok = status == "completed" and item.get("exitCode", 0) == 0
                ctx["emit"](t, {"t": "tool", "id": item_id, "name": "codex_command",
                                "label": "Comando concluído" if ok else "Comando com falha",
                                "ok": ok, "detail": "exit %s · %s" % (item.get("exitCode", "?"), status),
                                "out": output})
            elif item_type == "agentMessage":
                if not text_parts:
                    value = _plain_content(item.get("content") or item.get("text"))
                    if value:
                        text_parts.append(value)
                        ctx["emit"](t, {"t": "text", "d": value})
            elif item_type and status in ("failed", "declined"):
                detail = str(item.get("reason") or item.get("error") or item.get("status") or status)[:500]
                ctx["emit"](t, {"t": "tool", "id": item_id or uuid.uuid4().hex[:8],
                                "name": "codex_item", "label": "Atividade do Codex n?o conclu?da",
                                "ok": False, "detail": detail})
        elif method == "error":
            err = params.get("error") or {}
            ctx["emit"](t, {"t": "think", "d": "Codex: %s " % str(err.get("message") or err)[:500]})
        elif method == "turn/completed":
            turn = params.get("turn") or {}
            if not turn_id or turn.get("id") == turn_id:
                turn_state.update(completed=True, status=turn.get("status"), error=turn.get("error"))

    try:
        # Record the user input in JARVIS before contacting the model.
        if not thread_id and previous_messages:
            handoff = []
            for item in previous_messages[-16:]:
                role = str(item.get("role") or "")
                body = _plain_content(item.get("content"))
                if role in ("user", "assistant") and body.strip():
                    handoff.append(("Usuário" if role == "user" else "Assistente") + ": " + body[:2500])
            if handoff:
                text = ("CONTEXTO DA CONVERSA ANTERIOR NO JARVIS (não repita o trabalho concluído):\n" +
                        "\n\n".join(handoff) + "\n\nNOVA SOLICITAÇÃO:\n" + text)
        t.setdefault("messages", []).append({"role": "user", "content": text})
        if not ctx["save"](t):
            raise RuntimeError("Não foi possível salvar a solicitação antes de iniciar o Codex.")

        attachment_text, image_inputs = [], []
        for name, content in atts:
            if isinstance(content, dict) and content.get("image_data"):
                image_path = str(content.get("path") or "")
                if image_path:
                    image_inputs.append({"type": "localImage", "path": image_path})
                attachment_text.append("[imagem anexada: %s; arquivo local: %s]" % (name, image_path))
            else:
                attachment_text.append("[anexo: %s]\n%s" % (name, str(content)[:20000]))
        request_text = text + ("\n\n" + "\n\n".join(attachment_text) if attachment_text else "")
        request_text += "\n\n[Contexto JARVIS] Workspace autorizado: %s. " % workspace
        request_text += ("MODO SOMENTE PLANO: não crie, edite, exclua ou execute nada que altere arquivos/sistema. "
                         "Leia e apresente apenas a análise e o plano. " if mode == READ_ONLY_MODE else
                         "MODO EXECUÇÃO: trabalhe diretamente no workspace indicado; faça alterações, execute testes e confira o resultado. "
                         "Não leia nem imprima credenciais, tokens, arquivos .env, api_keys.json, chaves privadas ou dados de autenticação. "
                         "Não opere fora do workspace sem autorização explícita. Não publique/deploy sem pedido explícito. ")
        if mode == WORKSPACE_MODE:
            request_text += ("MODO ACESSO AO WORKSPACE: você está em execução não interativa, mas o sandbox continua limitado à pasta atual "
                             "(:workspace) e aos runtimeWorkspaceRoots informados. Não tente acessar caminhos fora dela, rede, downloads, "
                             "instalações, credenciais ou operações destrutivas. Esses pedidos serão recusados sem abrir uma aprovação. "
                             "Se uma tarefa realmente exigir algo fora da pasta ou acesso de rede, pare e explique o bloqueio; o usuário poderá "
                             "trocar manualmente para Pedir aprovação. ")
        request_text += "Use português brasileiro na comunicação e seja rigoroso ao verificar o que realmente foi concluído."
        web_task = _is_web_frontend_task(text, atts)
        if web_task:
            request_text += _web_workflow_directive()
        inputs = [{"type": "text", "text": request_text}] + image_inputs
        if web_task:
            inputs.extend(_web_skill_inputs())

        codex = CodexAppServer(workspace, codex_home=account_home)
        codex.request("initialize", {"clientInfo": {"name": "jarvis_agent", "title": "JARVIS Agent", "version": "2.0.0"}, "capabilities": {"experimentalApi": True}}, timeout=30)
        codex.notify("initialized", {})
        account_result = codex.request("account/read", {"refreshToken": False}, timeout=20)
        account = account_result.get("account") or {}
        if account.get("type") != "chatgpt":
            raise RuntimeError("O Codex não está autenticado com uma conta ChatGPT neste Windows. Faça login no Codex e tente novamente.")
        t["codex_plan_type"] = account.get("planType") or "ChatGPT"
        models_result = codex.request("model/list", {"limit": 50, "includeHidden": False}, timeout=30)
        models = [m for m in models_result.get("data", []) if not m.get("hidden") and m.get("id")]
        selected_model = next((m for m in models if m.get("id") == t.get("codex_model")), None)
        if not selected_model:
            selected_model = next((m for m in models if m.get("isDefault")), None) or (models[0] if models else None)
        if not selected_model:
            raise RuntimeError("A conta ChatGPT não retornou nenhum modelo Codex disponível.")
        model = str(selected_model.get("id"))
        effort = _select_reasoning_effort(selected_model, web_task=web_task)
        t["codex_model"] = model
        t["codex_effort"] = effort
        t["codex_plan_type"] = str(account.get("planType") or "ChatGPT")
        ctx["emit"](t, {"t": "think", "d": "Codex: %s · raciocínio %s%s" % (
            str(selected_model.get("displayName") or model), effort,
            " · modo frontend" if web_task else "")})
        try:
            limits = codex.request("account/rateLimits/read", {}, timeout=20)
            primary = ((limits.get("rateLimits") or {}).get("primary") or {})
            used = primary.get("usedPercent")
            if used is not None:
                t["codex_usage_percent"] = int(used)
                if int(used) >= 95:
                    ctx["emit"](t, {"t": "think", "d": "A conta ChatGPT está perto do limite de uso do Codex (%s%%). O serviço informa o limite se ele for atingido. " % int(used)})
        except Exception:
            pass

        # Use the legacy thread sandbox for compatibility and an explicit per-turn
        # workspaceWrite/readOnly sandbox policy. Never grant danger-full-access.
        approval_policy, sandbox_mode = _codex_execution_settings(mode)
        sandbox_policy = _codex_sandbox_policy(mode, workspace)

        if thread_id:
            try:
                codex.request("thread/resume", {"threadId": thread_id, "excludeTurns": True}, timeout=40)
            except Exception:
                thread_id = ""
                thread_map.pop(account_id, None)
                thread_context_map.pop(account_id, None)
                if account_id == "primary":
                    t.pop("codex_thread_id", None)

        if not thread_id:
            started = codex.request("thread/start", {"cwd": str(workspace), "model": model,
                                    "approvalPolicy": approval_policy, "sandbox": sandbox_mode,
                                    "runtimeWorkspaceRoots": [str(workspace)],
                                    "serviceName": "jarvis_agent"}, timeout=45)
            thread_id = str((started.get("thread") or {}).get("id") or "")
            if not thread_id:
                raise RuntimeError("O Codex não retornou o identificador da conversa.")
            thread_map[account_id] = thread_id
            thread_context_map[account_id] = context_fingerprint
            if account_id == "primary":
                t["codex_thread_id"] = thread_id
            if not ctx["save"](t):
                raise RuntimeError("A conversa foi criada, mas não foi possível salvar seu identificador no JARVIS.")

        turn_params = {"threadId": thread_id, "input": inputs, "cwd": str(workspace),
                       "model": model, "effort": effort, "approvalPolicy": approval_policy,
                       "sandboxPolicy": sandbox_policy,
                       "runtimeWorkspaceRoots": [str(workspace)]}
        started_turn = codex.request("turn/start", turn_params, on_message=on_message, timeout=90)
        turn_id = str(((started_turn.get("turn") or {}).get("id")) or "")
        if not turn_id and not turn_state["completed"]:
            raise RuntimeError("O Codex não retornou o identificador da execução.")

        interrupted = False
        while not turn_state["completed"]:
            if stop.is_set() and not interrupted and turn_id:
                try:
                    codex.send({"method": "turn/interrupt", "id": 999999,
                                "params": {"threadId": thread_id, "turnId": turn_id}})
                    interrupted = True
                except Exception:
                    break
            message = codex.next_message(timeout=0.35)
            if message:
                result = on_message(message)
                if "id" in message and message.get("method"):
                    codex.send({"id": message["id"], "result": result or {"decision": "decline"}})
            if stop.is_set() and interrupted and time.time() - t0 > 600:
                break

        _finalize_snapshots(t, touched, ctx)
        status = turn_state.get("status")
        answer = "".join(text_parts).strip()
        if status == "failed":
            err = turn_state.get("error") or {}
            message = str(err.get("message") or "O Codex encerrou a execução com falha.")
            if answer:
                t["messages"].append({"role": "assistant", "content": answer})
            raise RuntimeError(message[:1200])
        if status == "interrupted" or stop.is_set():
            answer = (answer + "\n\n" if answer else "") + "Execução interrompida. Confira os arquivos alterados antes de continuar."
        if not answer:
            answer = "O Codex concluiu a execução. Confira os eventos e os arquivos alterados no workspace."
            ctx["emit"](t, {"t": "text", "d": answer})
        t["messages"].append({"role": "assistant", "content": answer})
        t["last"] = answer
        # Record the exact JARVIS transcript represented by this account's thread.
        # A later account switch changes the digest and forces a safe context handoff.
        thread_context_map[account_id] = _messages_fingerprint(t["messages"])
        ctx["save"](t)
    except Exception as exc:
        raise RuntimeError(str(exc)[:1500]) from exc
    finally:
        _finalize_snapshots(t, touched, ctx)
        if codex is not None:
            codex.close()
