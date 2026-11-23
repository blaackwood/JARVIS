"""Application language selection and lightweight UI translation.

The persistent language lives in the user's local app configuration.  It is
independent of Windows display language and of the language of a one-off task.
"""
from __future__ import annotations

from memory.config_manager import get_app_language, normalize_app_language

LANGUAGE_CHOICES = (
    ("English (US)", "en-US"),
    ("Português (Brasil)", "pt-BR"),
)


PT_TO_EN = {
    "1-4 estados  N noticias  S pesquisa  H inicio  T tarefas  R rotinas  C controles  G config  F4 mutar  ESC interromper  F11 tela cheia  ESC sair": "1-4 states  N news  S search  H home  T tasks  R routines  C controls  G settings  F4 mute  ESC interrupt  F11 full screen  ESC exit",

    "INÍCIO": "HOME", "INICIO": "HOME", "TAREFAS": "TASKS",
    "ROTINAS": "ROUTINES", "CONTROLES": "CONTROLS", "CONFIG": "SETTINGS",
    "Microfone": "Microphone", "Desligado, o Jarvis para de escutar": "Off — JARVIS stops listening",
    "Interromper": "Interrupt", "Para a fala do assistente agora": "Stop the assistant's speech now",
    "Tela cheia": "Full screen", "Alterna o modo tela cheia (F11)": "Toggle full screen (F11)",
    "Dormir agora": "Sleep now", "Acordar agora": "Wake up now",
    "Espera até ouvir a palavra de ativação": "Wait until the wake word is heard",
    "Espera ate ouvir a palavra de ativacao": "Wait until the wake word is heard",
    "Precisa da palavra de ativação ligada": "Wake word must be enabled",
    "Resumo da manhã": "Morning briefing", "Fala notícias e agenda ao acordar": "Reads news and schedule when you wake up",
    "Palavra de ativação": "Wake word", "Responde quando ouvir o nome dele": "Responds when it hears its name",
    "Baixa o modelo na primeira vez": "Downloads the model on first use",
    "Apertar para falar": "Push to talk", "Só escuta com a tecla pressionada": "Listens only while the key is held",
    "Visual da esfera": "Orb appearance", "Alterna holograma e núcleo neural": "Switch between hologram and neural core",
    "Agent UI": "Agent UI", "Abre o aplicativo Jarvis Agent": "Opens the JARVIS Agent app",
    "Acesso remoto": "Remote access", "Pareamento seguro com outro dispositivo": "Secure pairing with another device",
    "Atalho na área de trabalho": "Desktop shortcut", "Cria um ícone para abrir o JARVIS": "Creates an icon to open JARVIS",
    "Iniciar com o Windows": "Start with Windows", "Abre junto com o computador": "Starts when the computer starts",
    "Identidade do JARVIS": "JARVIS identity", "Nome, voz, aparência e motor": "Name, voice, appearance and engine",
    "Voz e áudio": "Voice and audio", "Microfone, saída e níveis": "Microphone, output and levels",
    "Memória": "Memory", "Inspecione o que o JARVIS guardou": "Review what JARVIS has remembered",
    "Extensões": "Extensions", "Extensoes": "Extensions",
    "Gerencie as capacidades instaladas": "Manage installed capabilities",
    "Configuração de extensões": "Extension settings", "Configuraçao de extensoes": "Extension settings",
    "Ajuste os módulos conectados": "Configure connected modules",
    "Motor e provedores": "Engine and providers", "Rotas de escuta, raciocínio e fala": "Listening, reasoning and speech routes",
    "CONFIGURAÇÕES DO JARVIS  ·  CONTROLE E PERSONALIZAÇÃO": "JARVIS SETTINGS  ·  CONTROL AND PERSONALIZATION",
    "Configurações do Jarvis": "JARVIS settings",
    "Fale com o Jarvis ou digite um comando...": "Talk to JARVIS or type a command...",
    "Pesquise na web: ": "Search the web: ",
    "Falhou: ": "Failed: ", "Ligue a palavra de ativação para usar o modo de espera.": "Enable the wake word to use sleep mode.",
    "Microfone padrão": "Default microphone", "Saída de som": "Sound output",
    "Alto-falantes": "Speakers", "Fones de ouvido": "Headphones",
    "Controle remoto": "Remote control", "Início automático": "Automatic startup",
    "Memória de longo prazo": "Long-term memory", "Plugins": "Plugins",
    "Pesquisa na web": "Web search", "Notícias": "News", "Agenda": "Calendar",
    "Controle do PC": "PC control", "Aparência": "Appearance",
    "Nome": "Name", "Voz": "Voice", "Idioma": "Language",
    "Português (BR)": "Português (Brasil)", "Desligado": "Off", "Ligado": "On",
    "Criar atalho": "Create shortcut", "Atalho criado ✓": "Shortcut created ✓",
    "Resumo da manhã": "Morning briefing", "Lenta": "Slow", "Normal": "Normal", "Rápida": "Fast",
    "Sem prazo": "No due date", "Hoje": "Today", "Amanhã": "Tomorrow",
    "Nenhuma tarefa em segundo plano ainda.": "No background tasks yet.",
    "Nenhuma rotina ainda. Peça uma por voz.": "No routines yet. Ask for one by voice.",
    "JARVIS  /  CONFIGURAÇÕES DO SISTEMA": "JARVIS  /  SYSTEM SETTINGS",
    "Central de controle neural": "Neural control center",
    "Configuração ao vivo e módulos do sistema — conectados diretamente a esta instalação do JARVIS.": "Live configuration and system modules — connected directly to this JARVIS installation.",
    "Perfil": "Profile", "Nome do assistente": "Assistant name", "Seu nome": "Your name",
    "Deixe em branco se preferir que o assistente escolha como se dirigir a você automaticamente.": "Leave blank if you prefer the assistant to choose how to address you.",
    "Voz e motor": "Voice and engine", "Escolha a voz Live e o motor de conversa.": "Choose the Live voice and conversation engine.",
    "Voz do assistente": "Assistant voice", "Motor de conversa": "Conversation engine",
    "Idioma do JARVIS": "JARVIS language",
    "Escolha o idioma da interface, das respostas e da fala do assistente.": "Choose the language used for the interface, assistant replies and speech.",
    "A alteração será aplicada à próxima sessão de voz.": "The change will be applied to the next voice session.",
    "Identidade visual": "Visual identity", "Defina a cor de destaque usada no HUD e nos controles do JARVIS.": "Set the accent color used by the JARVIS HUD and controls.",
    "Cor de destaque (hex)": "Accent color (hex)", "Digite uma cor de seis dígitos, como #8262ff. Um valor válido é pré-visualizado imediatamente.": "Enter a six-digit color such as #8262ff. A valid value previews immediately.",
    "Credenciais Gemini": "Gemini credentials",
    "Deixe em branco para manter a chave salva atualmente. Valores secretos nunca são exibidos.": "Leave blank to keep the currently saved key. Secret values are never displayed.",
    "Chave de API Gemini": "Gemini API key", "Salvar identidade": "Save identity",
    "Use uma cor hexadecimal válida, por exemplo #8262ff.": "Use a valid hexadecimal color, for example #8262ff.",
    "Identidade salva. A interface do JARVIS foi atualizada.": "Identity saved. The JARVIS interface has been updated.",
    "Você pode voltar para o Gemini Live aqui a qualquer momento.": "You can switch back to Gemini Live here at any time.",
    "Configurar módulos conectados.": "Configure connected modules.",
    "Voltar às configurações": "Back to settings", "Voltar as configuracoes": "Back to settings",
    "Voltar ao sistema": "Back to system", "Back to system": "Voltar ao sistema",
    "MÓDULO": "MODULE", "Ao vivo": "Live", "Sistema online": "System online",
    "Configuração inicial": "Initial setup", "Conecte seu JARVIS": "Connect your JARVIS",
    "Português (Brasil)": "Português (Brasil)", "English (US)": "English (US)",
    "MODULOS": "MODULES", "Voz": "Voice", "Visão": "Vision", "Navegador": "Browser", "Memória": "Memory", "Agentes": "Agents", "Agenda": "Calendar",
    "EM ESPERA": "IDLE",
    "ESCUTANDO": "LISTENING",
    "PENSANDO": "THINKING",
    "FALANDO": "SPEAKING",
    "Aguardando chamada": "Waiting for wake word",
    "Ouvindo seu comando": "Listening to your command",
    "Interpretando o pedido": "Processing your request",
    "Respondendo por voz": "Speaking",
    "1-4 estados  N noticias  S pesquisa  H inicio  T tarefas  R rotinas  C controles  G config  M mutar  I interromper  O esfera  Espaco demo  F11 tela cheia  Esc sair": "1-4 states  N news  S search  H home  T tasks  R routines  C controls  G settings  M mute  I interrupt  O orb  Space demo  F11 full screen  Esc exit",
    "MUDO": "MUTED",
    "ENTRAR": "ENTER",
    "SAIR": "EXIT",
    "Para a fala e volta ao repouso": "Stops speech and returns to idle",
    "Microfone ligado": "Microphone on",
    "Microfone mudo": "Microphone muted",
}

EN_TO_PT = {value: key for key, value in PT_TO_EN.items()}


def app_language(language: str | None = None) -> str:
    return normalize_app_language(language or get_app_language())


def tr(text, language: str | None = None) -> str:
    """Translate static interface copy while keeping dynamic/user content intact."""
    value = str(text or "")
    lang = app_language(language)
    table = EN_TO_PT if lang == "pt-BR" else PT_TO_EN

    def lookup(item):
        found = table.get(item)
        if found is None and item.isupper():
            found = table.get(item.lower().capitalize())
            if found is not None:
                found = found.upper()
        return found

    translated = lookup(value)
    if translated is not None:
        return translated

    # Keep identity names and status icons while translating their fixed suffix.
    for prefix in ("\u25cf  ", "\u25cf ", "\u2713  "):
        if value.startswith(prefix):
            suffix = lookup(value[len(prefix):])
            if suffix is not None:
                return prefix + suffix
    # Translate fixed log prefixes while preserving task titles and user content.
    for prefix in (
        "Tarefa: ", "Task: ", "Esfera: ", "Orb: ", "Falhou: ", "Failed: ",
        "Detalhe indispon\u00edvel: ", "Detail unavailable: ",
        "Rotina n\u00e3o alterada: ", "Routine unchanged: ",
    ):
        if value.startswith(prefix):
            translated_prefix = table.get(prefix)
            if translated_prefix is not None:
                suffix = lookup(value[len(prefix):])
                return translated_prefix + (suffix if suffix is not None else value[len(prefix):])
    if " \u00b7 " in value:
        head, tail = value.split(" \u00b7 ", 1)
        suffix = lookup(tail)
        if suffix is not None:
            return head + " \u00b7 " + suffix
    return value

def language_name(language: str | None = None) -> str:
    return "Brazilian Portuguese (pt-BR)" if app_language(language) == "pt-BR" else "English (United States, en-US)"


def speech_language_code(language: str | None = None) -> str:
    return app_language(language)


def language_instruction(language: str | None = None) -> str:
    """Highest-priority language policy injected at the end of the Live prompt."""
    lang = app_language(language)
    if lang == "pt-BR":
        return (
            "[JARVIS LANGUAGE — APP PREFERENCE]\n"
            "The user's selected JARVIS language is Brazilian Portuguese (pt-BR). "
            "Respond and speak naturally in Brazilian Portuguese, with a native Brazilian accent, "
            "pronunciation, vocabulary and grammar. Use a respectful, composed register. "
            "This is the persistent app language setting, not a one-turn request. "
            "Use another language only when the user explicitly requests translation or a specific "
            "task in another language; then return to Brazilian Portuguese afterwards. "
            "Text shown in the UI, spoken replies, greetings, narration, visual-lesson captions, and every title, subtitle, label, annotation, quiz, status, and explanation generated for 2D/3D visual tools "
            "must follow this setting. Never use European Portuguese. Never mix languages within a visual explanation."
        )
    return (
        "[JARVIS LANGUAGE — APP PREFERENCE]\n"
        "The user's selected JARVIS language is English (United States, en-US). "
        "Respond and speak naturally in fluent American English, with natural US pronunciation, "
        "vocabulary and grammar. Use a clear, respectful, composed register. "
        "This is the persistent app language setting, not a one-turn request. "
        "Use another language only when the user explicitly requests translation or a specific "
        "task in another language; then return to American English afterwards. "
        "Text shown in the UI, spoken replies, greetings, narration, visual-lesson captions, and every title, subtitle, label, annotation, quiz, status, and explanation generated for 2D/3D visual tools "
        "must follow this setting."
    )


def visual_content_instruction(language: str | None = None) -> str:
    """Strict locale policy for every textual field produced by visual/3D tools."""
    lang = app_language(language)
    if lang == "en-US":
        return (
            "VISUAL CONTENT LANGUAGE — HARD REQUIREMENT: Write absolutely every human-readable "
            "string in this visual output in American English: title, subtitle, lesson title, "
            "3D object/part labels, model labels, link/arrow labels, captions, spoken 'say' text, "
            "text annotations, formula explanations, quiz questions and choices, hints, status text, "
            "and any explanatory text. Do not leave Portuguese words or mixed-language fragments. "
            "Keep scientific names, standard symbols, equations, proper names, and user-provided "
            "quoted text unchanged only when they are not meant to be translated. Translate the "
            "meaning of fixed Portuguese examples; never copy their Portuguese wording. "
            "Before returning tool arguments, check every text field for language consistency."
        )
    return (
        "VISUAL CONTENT LANGUAGE — HARD REQUIREMENT: Write absolutely every human-readable "
        "string in this visual output in Brazilian Portuguese: title, subtitle, lesson title, "
        "3D object/part labels, model labels, link/arrow labels, captions, spoken 'say' text, "
        "text annotations, formula explanations, quiz questions and choices, hints, status text, "
        "and any explanatory text. Do not leave English words or mixed-language fragments. "
        "Keep scientific names, standard symbols, equations, proper names, and user-provided "
        "quoted text unchanged only when they are not meant to be translated. "
        "Before returning tool arguments, check every text field for language consistency."
    )


def startup_greeting_prompt(hour: int, language: str | None = None) -> str:
    lang = app_language(language)
    if lang == "pt-BR":
        greeting = "Bom dia" if 5 <= int(hour) < 12 else "Boa tarde" if 12 <= int(hour) < 18 else "Boa noite"
        return (
            "Say exactly this one sentence in very formal, natural Brazilian Portuguese: "
            f'"{greeting}, senhor. Estou à sua inteira disposição." '
            "Address the user respectfully. Do not add another sentence, mention the time/date/news, or call tools."
        )
    greeting = "Good morning" if 5 <= int(hour) < 12 else "Good afternoon" if 12 <= int(hour) < 18 else "Good evening"
    return (
        "Say exactly this one sentence in natural, polished American English: "
        f'"{greeting} sir. I am at your service." '
        "Keep a respectful, composed tone. Do not add another sentence, mention the time/date/news, or call tools."
    )


# Live HUD and launcher vocabulary. User-created task names, routine names,
# file names, news and document content are deliberately not translated.
PT_TO_EN.update({
    "AGUARDANDO": "IDLE", "OUVINDO": "LISTENING", "PENSANDO": "THINKING",
    "FALANDO": "SPEAKING", "MUDO": "MUTED",
    "SEG": "MON", "TER": "TUE", "QUA": "WED", "QUI": "THU",
    "SEX": "FRI", "SAB": "SAT", "SÁB": "SAT", "DOM": "SUN",
    "FEV": "FEB", "ABR": "APR", "MAI": "MAY", "AGO": "AUG",
    "SET": "SEP", "OUT": "OCT", "DEZ": "DEC",
    "Microfone": "Microphone",
    "Desligado, o Jarvis para de escutar": "Off — JARVIS stops listening",
    "Interromper": "Interrupt", "Para a fala e volta ao repouso": "Stop speech and return to idle",
    "Para a fala do assistente agora": "Stop the assistant's speech now",
    "Tela cheia": "Full screen", "Alterna o modo tela cheia (F11)": "Toggle full screen (F11)",
    "Dormir agora": "Sleep now", "Acordar agora": "Wake up now",
    "Espera até ouvir a palavra de ativação": "Wait for the wake word",
    "Precisa da palavra de ativação ligada": "Wake word must be enabled",
    "Coloca o assistente em espera": "Put the assistant to sleep",
    "Resumo da manhã": "Morning briefing", "Fala notícias e agenda ao acordar": "Reads news and calendar when you wake up",
    "Palavra de ativação": "Wake word", "Responde quando ouvir o nome dele": "Responds when its name is heard",
    "Baixa o modelo na primeira vez": "Downloads the model on first use",
    "Apertar para falar": "Push to talk", "Só escuta com a tecla pressionada": "Listens only while the key is held",
    "Visual da esfera": "Orb appearance", "Alterna holograma e núcleo neural": "Switch between hologram and neural core",
    "Controles rápidos do assistente (clique para alternar)": "Quick assistant controls (click to toggle)",
    "LIGADO": "ON", "DESLIGADO": "OFF", "PARAR": "STOP",
    "SAIR": "EXIT", "ENTRAR": "ENTER", "DORMIR": "SLEEP", "ACORDAR": "WAKE",
    "INDISPONÍVEL": "UNAVAILABLE", "BAIXAR": "DOWNLOAD", "ABRIR": "OPEN", "CRIAR": "CREATE",
    "Acesso remoto": "Remote access", "Pareamento seguro com outro dispositivo": "Secure pairing with another device",
    "Atalho na área de trabalho": "Desktop shortcut", "Cria um ícone para abrir o JARVIS": "Creates an icon to open JARVIS",
    "Iniciar com o Windows": "Start with Windows", "Abre junto com o computador": "Starts when the computer starts",
    "Identidade do JARVIS": "JARVIS identity", "Nome, voz, aparência e motor": "Name, voice, appearance and engine",
    "Voz e áudio": "Voice and audio", "Microfone, saída e níveis": "Microphone, output and levels",
    "Memória": "Memory", "Inspecione o que o JARVIS guardou": "Review what JARVIS has remembered",
    "Extensões": "Extensions", "Extensoes": "Extensions",
    "Gerencie as capacidades instaladas": "Manage installed capabilities",
    "Configuração de extensões": "Extension settings", "Configuração de extensoes": "Extension settings",
    "Ajuste os módulos conectados": "Configure connected modules",
    "Motor e provedores": "Engine and providers", "Rotas de escuta, raciocínio e fala": "Listening, reasoning and speech routes",
    "CONFIGURAÇÕES DO JARVIS  ·  CONTROLE E PERSONALIZAÇÃO": "JARVIS SETTINGS  ·  CONTROL AND PERSONALIZATION",
    "Configurações do Jarvis": "JARVIS settings",
    "Fale com o Jarvis ou digite um comando...": "Talk to JARVIS or type a command...",
    "Pesquise na web: ": "Search the web: ", "Crie uma tarefa em segundo plano: ": "Create a background task: ",
    "Busque e apresente as principais notícias atuais do Brasil e do mundo.": "Find and present the top current news from the US and around the world.",
    "Falhou: ": "Failed: ", "Ligue a palavra de ativação para usar o modo de espera.": "Enable the wake word to use sleep mode.",
    "Microfone padrão": "Default microphone", "Saída de som": "Sound output",
    "Alto-falantes": "Speakers", "Fones de ouvido": "Headphones",
    "Controle remoto": "Remote control", "Início automático": "Automatic startup",
    "Memória de longo prazo": "Long-term memory", "Plugins": "Plugins",
    "Pesquisa na web": "Web search", "Notícias": "News", "Agenda": "Calendar",
    "Controle do PC": "PC control", "Aparência": "Appearance",
    "Nome": "Name", "Voz": "Voice", "Idioma": "Language",
    "Português (BR)": "Português (Brasil)", "Desligado": "Off", "Ligado": "On",
    "Criar atalho": "Create shortcut", "Atalho criado ✓": "Shortcut created ✓",
    "Lenta": "Slow", "Normal": "Normal", "Rápida": "Fast",
    "Sem prazo": "No due date", "Hoje": "Today", "Amanhã": "Tomorrow",
    "A FAZER": "TO DO", "EM ANDAMENTO": "IN PROGRESS", "CONCLUÍDO": "COMPLETED",
    "NOVA TAREFA": "NEW TASK", "Evento": "Event", "Mensal": "Monthly",
    "Uma vez": "Once", "Ao abrir": "At startup", "Ocioso": "Idle",
    "nunca rodou": "never run", "pausada": "paused", "última: ": "last: ",
    "próxima  ": "next  ", "HOJE · 24 HORAS": "TODAY · 24 HOURS",
    "Rotina": "Routine", "Tarefa": "Task", "Falhou": "Failed",
    "JARVIS  /  CONFIGURAÇÕES DO SISTEMA": "JARVIS  /  SYSTEM SETTINGS",
    "MÓDULO": "MODULE", "Ao vivo": "Live", "Sistema online": "System online",
    "Abrir JARVIS": "Open JARVIS", "Hibernar (Hey Jarvis)": "Sleep (Hey JARVIS)",
    "Sair completamente": "Exit completely",
})

# Add the reverse translations used when a user switches the same build to pt-BR.
EN_TO_PT.update({
    "HOME": "INÍCIO", "TASKS": "TAREFAS", "ROUTINES": "ROTINAS",
    "CONTROLS": "CONTROLES", "SETTINGS": "CONFIG",
    "IDLE": "AGUARDANDO", "LISTENING": "OUVINDO", "THINKING": "PENSANDO",
    "SPEAKING": "FALANDO", "MUTED": "MUDO",
    "MON": "SEG", "TUE": "TER", "WED": "QUA", "THU": "QUI",
    "FRI": "SEX", "SAT": "SÁB", "SUN": "DOM",
    "FEB": "FEV", "APR": "ABR", "MAY": "MAI", "AUG": "AGO", "SEP": "SET", "OCT": "OUT", "DEC": "DEZ",
    "Microphone": "Microfone", "Interrupt": "Interromper", "Full screen": "Tela cheia",
    "Sleep now": "Dormir agora", "Wake up now": "Acordar agora",
    "Morning briefing": "Resumo da manhã", "Wake word": "Palavra de ativação",
    "Push to talk": "Apertar para falar", "Orb appearance": "Visual da esfera",
    "Remote access": "Acesso remoto", "Desktop shortcut": "Atalho na área de trabalho",
    "Start with Windows": "Iniciar com o Windows", "JARVIS identity": "Identidade do JARVIS",
    "Voice and audio": "Voz e áudio", "Extensions": "Extensões", "Memory": "Memória",
    "Engine and providers": "Motor e provedores", "TO DO": "A FAZER",
    "IN PROGRESS": "EM ANDAMENTO", "COMPLETED": "CONCLUÍDO", "NEW TASK": "NOVA TAREFA",
    "TODAY · 24 HOURS": "HOJE · 24 HORAS", "Exit completely": "Sair completamente",
})


EN_TO_PT.update({
    "OVERVIEW": "VISÃO GERAL", "SETUP": "CONFIGURAÇÃO", "ENGINE": "MOTOR",
    "AUDIO": "ÁUDIO", "MEMORY": "MEMÓRIA", "EXTENSIONS": "EXTENSÕES",
    "IDENTITY": "IDENTIDADE", "PLUGIN CFG": "CONFIG. PLUGINS", "REMOTE": "REMOTO",
    "JARVIS  /  SYSTEMS": "JARVIS  /  SISTEMA",
    "NEURAL INTERFACE  ·  CONTROL PLANE": "INTERFACE NEURAL  ·  PAINEL DE CONTROLE",
    "SYSTEM ONLINE": "SISTEMA ONLINE",
    "JARVIS  /  SYSTEM SETTINGS": "JARVIS  /  CONFIGURAÇÕES DO SISTEMA",
    "Neural control center": "Central de controle neural",
    "Live configuration and system modules - connected directly to this JARVIS installation.": "Configuração ao vivo e módulos do sistema, conectados diretamente a esta instalação do JARVIS.",
    "ENGINE CORE": "NÚCLEO DO MOTOR", "VOICE & AUDIO": "VOZ E ÁUDIO",
    "MEMORY": "MEMÓRIA", "EXTENSIONS": "EXTENSÕES", "IDENTITY": "IDENTIDADE",
    "REMOTE ACCESS": "ACESSO REMOTO",
    "MANAGE MODELS": "GERENCIAR MODELOS", "CONFIGURE AUDIO": "CONFIGURAR ÁUDIO",
    "OPEN MEMORY": "ABRIR MEMÓRIA", "MANAGE EXTENSIONS": "GERENCIAR EXTENSÕES",
    "CUSTOMIZE JARVIS": "PERSONALIZAR JARVIS", "OPEN REMOTE": "ABRIR ACESSO REMOTO",
    "LIVE CONFIGURATION  ·  LOCAL SECRETS STAY MASKED  ·  CHANGES APPLY THROUGH THE ORIGINAL ENGINE": "CONFIGURAÇÃO AO VIVO  ·  SEGREDOS LOCAIS PROTEGIDOS  ·  ALTERAÇÕES APLICADAS AO MOTOR ORIGINAL",
    "Back to settings": "Voltar às configurações", "Back to system": "Voltar ao sistema",
    "Engine core": "Núcleo do motor",
    "Routing for hearing, reasoning, speaking, background requests and coding.": "Rotas de escuta, raciocínio, fala, tarefas em segundo plano e programação.",
    "Voice & audio": "Voz e áudio", "Select the real input/output devices and test the signal path.": "Selecione os dispositivos reais de entrada e saída e teste o áudio.",
    "Review and maintain the assistant's persistent memory.": "Consulte e gerencie a memória persistente do assistente.",
    "Enable or disable installed capabilities.": "Ative ou desative os recursos instalados.",
    "Configure credentials and settings for connected modules.": "Configure credenciais e opções dos módulos conectados.",
    "Assistant identity, voice, appearance and conversation engine.": "Identidade, voz, aparência e motor de conversa do assistente.",
    "Generate a secure pairing session for another device.": "Gere uma sessão segura de pareamento para outro dispositivo.",
    "Initial setup": "Configuração inicial", "Connect JARVIS to its conversation service and finish the local setup.": "Conecte o JARVIS ao serviço de conversação e conclua a configuração local.",
    "Assistant identity": "Identidade do assistente",
    "Personalize the JARVIS interface and conversation. Changes are applied to the running session.": "Personalize a interface e a conversa do JARVIS. As alterações são aplicadas à sessão atual.",
    "Profile": "Perfil", "The assistant name appears throughout the desktop interface.": "O nome do assistente aparece em toda a interface.",
    "Optional": "Opcional",
    "Leave blank when you prefer the assistant to choose how to address you automatically.": "Deixe em branco se preferir que o assistente escolha automaticamente como se dirigir a você.",
    "Voice and engine": "Voz e motor", "Choose the Live voice and the conversation engine.": "Escolha a voz Live e o motor de conversa.",
    "Assistant voice": "Voz do assistente", "Conversation engine": "Motor de conversa",
    "JARVIS language": "Idioma do JARVIS",
    "Choose the language used for the interface, assistant replies and speech.": "Escolha o idioma da interface, das respostas e da fala do assistente.",
    "Visual identity": "Identidade visual",
    "Set the accent color used by the JARVIS HUD and controls.": "Defina a cor de destaque usada no HUD e nos controles do JARVIS.",
    "Accent color (hex)": "Cor de destaque (hex)",
    "Enter a six-digit color such as #8262ff. A valid value previews immediately.": "Digite uma cor de seis dígitos, como #8262ff. Um valor válido é pré-visualizado imediatamente.",
    "Gemini credentials": "Credenciais do Gemini",
    "Leave blank to keep the currently saved key. Secret values are never displayed.": "Deixe em branco para manter a chave salva. Valores secretos nunca são exibidos.",
    "Gemini API key": "Chave de API do Gemini", "Paste a new Gemini API key to replace it": "Cole uma nova chave de API do Gemini para substituí-la",
    "Save identity": "Salvar identidade", "Identity saved. The JARVIS interface has been updated.": "Identidade salva. A interface do JARVIS foi atualizada.",
    "Use a valid hexadecimal color, for example #8262ff.": "Use uma cor hexadecimal válida, por exemplo #8262ff.",
    "Connect your JARVIS": "Conecte seu JARVIS",
    "Each installation uses its owner's Gemini API key. No developer key is bundled or shared.": "Cada instalação usa a própria chave de API Gemini. Nenhuma chave do desenvolvedor é incluída ou compartilhada.",
})


PT_TO_EN.update({
    "MÓDULOS": "MODULES", "SISTEMA": "SYSTEM", "MEMORIA": "MEMORY",
    "DISCO": "DISK", "Visão": "Vision", "Navegador": "Browser",
    "Agentes": "Agents", "Agenda": "Calendar", "Voz": "Voice",
    "MÓDULOS": "MODULES", "Atividade": "Activity",
    "(clique num cartão para ver os detalhes)": "(click a card to view details)",
    "(clique num cartao para ver os detalhes)": "(click a card to view details)",
    "Narração indisponível": "Narration unavailable",
    "Etapas concluídas": "All steps completed",
    "Etapa": "Step", "pausada": "paused",
    "clique": "click", "passagem do cursor": "hover",
})

EN_TO_PT.update({
    "MODULES": "MÓDULOS", "SYSTEM": "SISTEMA", "DISK": "DISCO",
    "Vision": "Visão", "Browser": "Navegador", "Agents": "Agentes",
    "Calendar": "Agenda", "Voice": "Voz", "Activity": "ATIVIDADE",
    "Narration unavailable": "Narração indisponível",
    "All steps completed": "Etapas concluídas",
    "Step": "Etapa", "paused": "pausada", "click": "clique", "hover": "passagem do cursor",
})


PT_TO_EN.update({
    "ATIVIDADE": "ACTIVITY", "MÓDULOS": "MODULES",
    "MODULOS": "MODULES", "MEMÓRIA": "MEMORY", "MUDO": "MUTED",
    "NOVA TAREFA": "NEW TASK", "CONCLUÍDO": "COMPLETED",
    "a fazer": "to do", "em andamento": "in progress", "concluídas": "completed",
})
EN_TO_PT.update({"ACTIVITY": "ATIVIDADE"})


# Complete the reverse map for every core UI term while preserving curated
# translations already supplied above.
for _pt_label, _en_label in PT_TO_EN.items():
    EN_TO_PT.setdefault(_en_label, _pt_label)

PT_TO_EN.update({"Ativo em segundo plano": "Running in the background"})
EN_TO_PT.update({"Running in the background": "Ativo em segundo plano"})


EN_TO_PT.update({
    "OVERVIEW": "VISÃO GERAL", "SETUP": "CONFIGURAÇÃO", "ENGINE": "MOTOR",
    "AUDIO": "ÁUDIO", "MEMORY": "MEMÓRIA", "EXTENSIONS": "EXTENSÕES",
    "IDENTITY": "IDENTIDADE", "PLUGIN CFG": "CONFIG. PLUGINS", "REMOTE": "REMOTO",
    "SYSTEM ONLINE": "SISTEMA ONLINE",
    "Identity": "Identidade", "Neural control center": "Central de controle neural",
    "Assistant identity, voice, appearance and conversation engine.": "Identidade, voz, aparência e motor de conversa do assistente.",
    "ASSISTANT IDENTITY": "IDENTIDADE DO ASSISTENTE",
    "Personalize the JARVIS interface and conversation. Changes are applied to the running session.": "Personalize a interface e a conversa do JARVIS. As alterações são aplicadas à sessão atual.",
    "PROFILE": "PERFIL",
    "The assistant name appears throughout the desktop interface.": "O nome do assistente aparece em toda a interface.",
    "ASSISTANT NAME": "NOME DO ASSISTENTE",
    "YOUR NAME": "SEU NOME",
    "VOICE AND ENGINE": "VOZ E MOTOR",
    "Choose the Live voice and the conversation engine.": "Escolha a voz Live e o motor de conversa.",
    "ASSISTANT VOICE": "VOZ DO ASSISTENTE",
    "CONVERSATION ENGINE": "MOTOR DE CONVERSA",
    "JARVIS LANGUAGE": "IDIOMA DO JARVIS",
    "Choose the language used for the interface, assistant replies and speech.": "Escolha o idioma da interface, das respostas e da fala do assistente.",
    "VISUAL IDENTITY": "IDENTIDADE VISUAL",
    "Set the accent color used by the JARVIS HUD and controls.": "Defina a cor de destaque usada no HUD e nos controles do JARVIS.",
    "ACCENT COLOR (HEX)": "COR DE DESTAQUE (HEX)",
    "Enter a six-digit color such as #8262ff. A valid value previews immediately.": "Digite uma cor de seis dígitos, como #8262ff. Um valor válido é pré-visualizado imediatamente.",
    "GEMINI CREDENTIALS": "CREDENCIAIS DO GEMINI",
    "Leave blank to keep the currently saved key. Secret values are never displayed.": "Deixe em branco para manter a chave salva. Valores secretos nunca são exibidos.",
    "GEMINI API KEY": "CHAVE DE API DO GEMINI",
    "Paste a new Gemini API key to replace it": "Cole uma nova chave de API do Gemini para substituí-la",
    "SAVE IDENTITY": "SALVAR IDENTIDADE",
    "←  BACK TO SYSTEM": "←  VOLTAR AO SISTEMA",
    "←  VOLTAR AS CONFIGURAÇÕES": "←  VOLTAR ÀS CONFIGURAÇÕES",
    "MANAGE MODELS  →": "GERENCIAR MODELOS  →",
    "CONFIGURE AUDIO  →": "CONFIGURAR ÁUDIO  →",
    "OPEN MEMORY  →": "ABRIR MEMÓRIA  →",
    "MANAGE EXTENSIONS  →": "GERENCIAR EXTENSÕES  →",
    "CUSTOMIZE JARVIS  →": "PERSONALIZAR JARVIS  →",
    "OPEN REMOTE  →": "ABRIR ACESSO REMOTO  →",
    "MODULE": "MÓDULO",
    "Each installation uses its owner's Gemini API key. No developer key is bundled or shared.": "Cada instalação usa a própria chave de API Gemini. Nenhuma chave do desenvolvedor é incluída ou compartilhada.",
    "Primary AI engine": "Motor principal de IA",
    "This key powers the main JARVIS conversation and its tool orchestration.": "Esta chave alimenta a conversa principal do JARVIS e a execução de ferramentas.",
    "Your Gemini API key": "Sua chave de API Gemini",
    "Create or manage a key in Google AI Studio →": "Crie ou gerencie uma chave no Google AI Studio →",
    "A key is already present in this local profile. Enter the key you want this installation to use; the saved value is never shown.": "Já existe uma chave neste perfil local. Digite a chave que deseja usar nesta instalação; o valor salvo nunca é exibido.",
    "Installation": "Instalação",
    "The operating system is stored locally with your preferences.": "O sistema operacional é armazenado localmente junto das suas preferências.",
    "Operating system": "Sistema operacional",
    "The key is checked with Google before it is saved. It stays on this computer in config/api_keys.json and must never be committed to Git.": "A chave é validada com o Google antes de ser salva. Ela permanece neste computador em config/api_keys.json e nunca deve ser enviada ao Git.",
    "VALIDATE AND CONNECT": "VALIDAR E CONECTAR",
    "Use a valid hexadecimal color, for example #8262ff.": "Use uma cor hexadecimal válida, por exemplo #8262ff.",
    "Identity saved. The JARVIS interface has been updated.": "Identidade salva. A interface do JARVIS foi atualizada.",
    "Ativo em segundo plano": "Em execução em segundo plano",
    "Running in the background": "Em execução em segundo plano",
})

for _pt_label, _en_label in PT_TO_EN.items():
    EN_TO_PT.setdefault(_en_label, _pt_label)


EN_TO_PT.update({
    # Overview cards and workspace navigation
    "Microphone, speakers, voice route and input/output levels.": "Microfone, alto-falantes, rota de voz e níveis de entrada e saída.",
    "Inspect, search, update and remove stored memories.": "Consulte, pesquise, atualize e remova memórias salvas.",
    "Installed plugins, capabilities and their configuration.": "Plugins instalados, recursos e suas configurações.",
    "Secure access session and device pairing.": "Sessão de acesso seguro e pareamento de dispositivos.",
    "This module is not available in the current installation.": "Este módulo não está disponível nesta instalação.",
    "ENGINE STATUS UNAVAILABLE": "STATUS DO MOTOR INDISPONÍVEL",
    "not set": "não configurado",
    # Setup and API-key page
    "CONNECT YOUR JARVIS": "CONECTE SEU JARVIS",
    "Each installation uses its owner's Gemini API key. No developer key is bundled or shared.": "Cada instalação usa a própria chave de API Gemini. Nenhuma chave do desenvolvedor é incluída ou compartilhada.",
    "PRIMARY AI ENGINE": "MOTOR PRINCIPAL DE IA",
    "This key powers the main JARVIS conversation and its tool orchestration.": "Esta chave alimenta a conversa principal do JARVIS e a execução de ferramentas.",
    "PASTE YOUR PERSONAL GEMINI API KEY": "COLE SUA CHAVE DE API GEMINI",
    "Your Gemini API key": "Sua chave de API Gemini",
    "Create or manage a key in Google AI Studio ↗": "Crie ou gerencie uma chave no Google AI Studio ↗",
    "A key is already present in this local profile. Enter the key you want this installation to use; the saved value is never shown.": "Já existe uma chave neste perfil local. Digite a chave que deseja usar nesta instalação; o valor salvo nunca é exibido.",
    "INSTALLATION": "INSTALAÇÃO",
    "The operating system is stored locally with your preferences.": "O sistema operacional é armazenado localmente junto das suas preferências.",
    "OPERATING SYSTEM": "SISTEMA OPERACIONAL",
    "The key is checked with Google before it is saved. It stays on this computer in config/api_keys.json and must never be committed to Git.": "A chave é validada com o Google antes de ser salva. Ela permanece neste computador em config/api_keys.json e nunca deve ser enviada ao Git.",
    "VALIDATE AND CONNECT": "VALIDAR E CONECTAR",
    # Voice and audio
    "VOICE AND AUDIO": "VOZ E ÁUDIO",
    "Select the actual microphone and speakers used by JARVIS. Device tests run in a worker and do not freeze the interface.": "Selecione o microfone e os alto-falantes usados pelo JARVIS. Os testes de dispositivos são executados em segundo plano e não travam a interface.",
    "MICROPHONE": "MICROFONE", "This is the input device JARVIS listens to.": "Este é o dispositivo de entrada que o JARVIS usa para escutar.",
    "INPUT DEVICE": "DISPOSITIVO DE ENTRADA",
    "TEST MICROPHONE": "TESTAR MICROFONE",
    "SPEAKERS": "ALTO-FALANTES", "This is the output device used for spoken replies.": "Este é o dispositivo de saída usado nas respostas faladas.",
    "OUTPUT DEVICE": "DISPOSITIVO DE SAÍDA",
    "PLAY TEST TONE": "REPRODUZIR TOM DE TESTE",
    "OUTPUT LEVEL": "NÍVEL DE SAÍDA",
    "The slider applies to the selected output device.": "O controle se aplica ao dispositivo de saída selecionado.",
    "Applying device changes reconnects the conversation. Your transcript and memory remain saved.": "Aplicar alterações nos dispositivos reconecta a conversa. A transcrição e a memória continuam salvas.",
    "APPLY DEVICES": "APLICAR DISPOSITIVOS",
    "DEFAULT": "PADRÃO",
    # Persistent memory
    "PERSISTENT MEMORY": "MEMÓRIA PERSISTENTE",
    "Review exactly what JARVIS remembers. Edit, search, import, or remove entries stored locally.": "Consulte exatamente o que o JARVIS lembra. Edite, pesquise, importe ou remova registros armazenados localmente.",
    "SEARCH AND FILTER": "PESQUISAR E FILTRAR",
    "Search by category, key, value or date…": "Pesquise por categoria, chave, valor ou data…",
    "All categories": "Todas as categorias",
    "Identity": "Identidade", "Preferences": "Preferências", "Projects": "Projetos",
    "Relationships": "Relacionamentos", "Wishes": "Desejos", "Notes": "Anotações", "Sessions": "Sessões",
    "STORED ENTRIES": "REGISTROS SALVOS",
    "IMPORT NOTE": "IMPORTAR ANOTAÇÃO",
    "No memories match this filter.": "Nenhuma memória corresponde a este filtro.",
    "EDIT": "EDITAR", "FORGET": "ESQUECER", "FORGET ENTRY": "ESQUECER REGISTRO",
    "All entries": "Todos os registros",
    # Extensions and plugin settings
    "Enable or disable installed JARVIS capabilities. Changes are stored in the local configuration.": "Ative ou desative recursos instalados do JARVIS. As alterações são salvas na configuração local.",
    "INSTALLED EXTENSIONS": "EXTENSÕES INSTALADAS",
    "modules discovered": "módulos encontrados",
    "No extensions were discovered in the plugins folder.": "Nenhuma extensão foi encontrada na pasta de plugins.",
    "Installed module": "Módulo instalado",
    "ON": "ATIVADO", "OFF": "DESATIVADO", "ERROR": "ERRO",
    "Configure each extension through its declared settings schema. Password values stay masked.": "Configure cada extensão por meio do esquema de opções declarado. Senhas permanecem ocultas.",
    "No installed extensions currently declare configurable settings.": "Nenhuma extensão instalada declarou opções configuráveis.",
    "SAVE SETTINGS": "SALVAR CONFIGURAÇÕES",
    "TEST CONNECTION": "TESTAR CONEXÃO",
    "Enabled": "Ativado",
    # Remote access
    "Generate a secure pairing session for another device.": "Gere uma sessão segura de pareamento para outro dispositivo.",
    "REMOTE ACCESS": "ACESSO REMOTO",
    "Create a temporary pairing session to connect another device to this JARVIS installation.": "Crie uma sessão temporária de pareamento para conectar outro dispositivo a esta instalação do JARVIS.",
    "DASHBOARD UNAVAILABLE": "PAINEL INDISPONÍVEL",
    "The remote dashboard is not running or has not started yet. Start JARVIS again or enable its dashboard integration.": "O painel remoto não está em execução ou ainda não foi iniciado. Reinicie o JARVIS ou ative a integração do painel.",
    "PAIRING SESSION": "SESSÃO DE PAREAMENTO",
    "Use the temporary link or copy the access key to the other device.": "Use o link temporário ou copie a chave de acesso para o outro dispositivo.",
    "CONNECTION LINK": "LINK DE CONEXÃO",
    "TEMPORARY ACCESS KEY": "CHAVE DE ACESSO TEMPORÁRIA",
    "COPY LINK": "COPIAR LINK", "COPY KEY": "COPIAR CHAVE",
    "Pairing keys expire automatically. Keep them private and only share with a device you control.": "As chaves de pareamento expiram automaticamente. Mantenha-as privadas e compartilhe apenas com um dispositivo que você controla.",
    # Status and placeholders
    "(not connected)": "(não conectado)",
    "Entries shown": "Registros exibidos",
    "Save settings": "Salvar configurações",
})

for _pt_label, _en_label in PT_TO_EN.items():
    EN_TO_PT.setdefault(_en_label, _pt_label)


EN_TO_PT.update({
    "VOICE AND AUDIO": "VOZ E ÁUDIO",
    "PERSISTENT MEMORY": "MEMÓRIA PERSISTENTE",
    "SEARCH AND FILTER": "PESQUISAR E FILTRAR",
    "STORED ENTRIES": "REGISTROS SALVOS",
    "INSTALLED EXTENSIONS": "EXTENSÕES INSTALADAS",
    "EXTENSIONS": "EXTENSÕES",
    "DASHBOARD UNAVAILABLE": "PAINEL INDISPONÍVEL",
    "PAIRING SESSION": "SESSÃO DE PAREAMENTO",
    "CONNECTION LINK": "LINK DE CONEXÃO",
    "TEMPORARY ACCESS KEY": "CHAVE DE ACESSO TEMPORÁRIA",
    "INPUT DEVICE": "DISPOSITIVO DE ENTRADA",
    "OUTPUT DEVICE": "DISPOSITIVO DE SAÍDA",
    "OUTPUT LEVEL": "NÍVEL DE SAÍDA",
    "MICROPHONE": "MICROFONE",
    "SPEAKERS": "ALTO-FALANTES",
    "APPLY DEVICES": "APLICAR DISPOSITIVOS",
    "SAVE SETTINGS": "SALVAR CONFIGURAÇÕES",
    "COPY LINK": "COPIAR LINK",
    "COPY KEY": "COPIAR CHAVE",
})

for _pt_label, _en_label in PT_TO_EN.items():
    EN_TO_PT.setdefault(_en_label, _pt_label)

PT_TO_EN.update({
    'INÍCIO': 'HOME',
    'CONCLUÍDA': 'COMPLETED',
    'FINALIZADAS': 'COMPLETED',
    'A FAZER': 'TO DO',
    'EM ANDAMENTO': 'IN PROGRESS',
    'NA FILA': 'QUEUED', 'AGUARDANDO': 'WAITING',
    'PAUSANDO': 'PAUSING', 'PAUSADA': 'PAUSED',
    'FALHOU': 'FAILED', 'CANCELADA': 'CANCELLED',
})
EN_TO_PT.update({
    'HOME': 'INÍCIO',
    'COMPLETED': 'CONCLUÍDA',
    'TO DO': 'A FAZER', 'IN PROGRESS': 'EM ANDAMENTO',
    'QUEUED': 'NA FILA', 'WAITING': 'AGUARDANDO',
    'PAUSING': 'PAUSANDO', 'PAUSED': 'PAUSADA',
    'FAILED': 'FALHOU', 'CANCELLED': 'CANCELADA',
})


# Complete static HUD/workspace vocabulary. Dynamic user-authored content
# (task names, routine names, memories, file names and third-party material)
# remains untouched unless it exactly matches a known interface label.
PT_TO_EN.update({
    "Controles r?pidos do assistente (clique para alternar)": "Quick assistant controls (click to toggle)",
    "Configura??es do Jarvis": "JARVIS settings",
    "Controle remoto": "Remote control",
    "Controle o Jarvis pelo celular ou por outro computador.": "Control JARVIS from your phone or another computer.",
    "C?digo de pareamento": "Pairing code",
    "Atalho na ?rea de trabalho": "Desktop shortcut",
    "Cria um ?cone para abrir o Jarvis com um clique.": "Creates a shortcut to open JARVIS with one click.",
    "Atalho": "Shortcut",
    "Iniciar com o Windows": "Start with Windows",
    "Abre o Jarvis sozinho quando o computador liga.": "Starts JARVIS automatically when the computer turns on.",
    "In?cio autom?tico": "Automatic startup",
    "Personalizar assistente": "Customize assistant",
    "Nome, voz e jeito de falar do assistente.": "Assistant name, voice and speaking style.",
    "Masculina": "Male",
    "Feminina": "Female",
    "Velocidade da fala": "Speech speed",
    "Dispositivos de ?udio": "Audio devices",
    "Escolha o microfone e a sa?da de som.": "Choose the microphone and audio output.",
    "Headset USB": "USB headset",
    "Volume da voz": "Voice volume",
    "O que o Jarvis guarda entre as conversas.": "What JARVIS keeps between conversations.",
    "Lembrar conversas por": "Keep conversations for",
    "Sempre": "Always",
    "Limpar mem?ria": "Clear memory",
    "Limpar agora": "Clear now",
    "Mem?ria limpa ?": "Memory cleared ?",
    "Ligue ou desligue as habilidades extras.": "Enable or disable extra capabilities.",
    "Config. de plugins": "Plugin settings",
    "Ajustes finos de cada plugin.": "Fine-tune each plugin.",
    "Fonte de not?cias": "News source",
    "Google Not?cias": "Google News",
    "Resultados por pesquisa": "Results per search",
    "Modelo de linguagem": "Language model",
    "Reconhecimento de voz": "Speech recognition",
    "S?ntese de voz": "Speech synthesis",
    "Fontes": "Sources",
    "FONTES": "SOURCES",
    "Reabrir ": "Reopen ",
    "Reabrir painel": "Reopen panel",
    "HOJE": "TODAY",
    "HOJE ? 24 HORAS": "TODAY ? 24 HOURS",
    "?ltima: ": "last: ",
    "pr?xima  ": "next  ",
    "pausada": "paused",
    "Evento": "Event",
    "Mensal": "Monthly",
    "Uma vez": "Once",
    "Ao abrir": "At startup",
    "Digite sua resposta...": "Type your answer...",
    "FECHAR": "CLOSE",
    "PR?XIMA  ?": "NEXT  ?",
    "FINALIZAR  ?": "FINISH  ?",
    "RESPONDER": "SUBMIT",
    "Resposta correta": "Correct answer",
    "Resposta esperada: ": "Expected answer: ",
    "Resposta registrada para revis?o": "Answer saved for review",
    "+  NOVA TAREFA": "+  NEW TASK",
    "Nova tarefa": "New task",
    "Nova tarefa %d": "New task %d",
    "Sem prazo": "No due date",
    "Hoje": "Today",
    "Amanh?": "Tomorrow",
    "Esta semana": "This week",
    "Feito agora": "Done just now",
    "Feito ontem": "Done yesterday",
    "Ontem": "Yesterday",
    "Conclu?do": "Completed",
    "Conclu?da": "Completed",
    "CONCLU?DA": "COMPLETED",
    "EM ESPERA": "IDLE",
    "ESCUTANDO": "LISTENING",
    "AGUARDANDO CHAMADA": "WAITING FOR INPUT",
    "Ouvindo seu comando": "Listening to your command",
    "Interpretando o pedido": "Understanding your request",
    "Respondendo por voz": "Responding by voice",
    "Microfone mudo": "Microphone muted",
    "Microfone ligado": "Microphone on",
    "Nada para interromper": "Nothing to interrupt",
    "Fala interrompida": "Speech interrupted",
    "Assistente em espera": "Assistant idle",
    "Esfera: ": "Orb: ",
    "holograma": "hologram",
    "n?cleo neural": "neural core",
    "ligado": "on",
    "desligado": "off",
    "Tarefa: ": "Task: ",
    "JARVIS SYSTEMS  ?  DESKTOP": "JARVIS SYSTEMS  ?  DESKTOP",
    "JARVIS - novo visual (pr?via)": "JARVIS - new interface (preview)",
    "JARVIS ? QUIZ": "JARVIS ? QUIZ",
})
EN_TO_PT.update({
    "JARVIS  /  SYSTEMS": "JARVIS  /  SISTEMA",
    "NEURAL INTERFACE  ?  CONTROL PLANE": "INTERFACE NEURAL  ?  PAINEL DE CONTROLE",
    "SYSTEM ONLINE": "SISTEMA ONLINE",
    "JARVIS  /  SYSTEM SETTINGS": "JARVIS  /  CONFIGURA??ES DO SISTEMA",
    "LIVE CONFIGURATION  ?  LOCAL SECRETS STAY MASKED  ?  CHANGES APPLY THROUGH THE ORIGINAL ENGINE":
        "CONFIGURA??O AO VIVO  ?  SEGREDOS LOCAIS PROTEGIDOS  ?  ALTERA??ES APLICADAS AO MOTOR ORIGINAL",
    "Assistant identity": "Identidade do assistente",
    "Assistant name": "Nome do assistente",
    "Your name": "Seu nome",
    "Assistant voice": "Voz do assistente",
    "Voice and engine": "Voz e motor",
    "Voice and audio": "Voz e ?udio",
    "Conversation engine": "Motor de conversa",
    "JARVIS language": "Idioma do JARVIS",
    "Visual identity": "Identidade visual",
    "Accent color (hex)": "Cor de destaque (hex)",
    "Gemini credentials": "Credenciais do Gemini",
    "Gemini API key": "Chave de API do Gemini",
    "Save identity": "Salvar identidade",
    "Connect your JARVIS": "Conecte seu JARVIS",
    "Personalize the JARVIS interface and conversation. Changes are applied to the running session.":
        "Personalize a interface e a conversa do JARVIS. As altera??es s?o aplicadas ? sess?o em execu??o.",
    "The assistant name appears throughout the desktop interface.":
        "O nome do assistente aparece em toda a interface do computador.",
    "Choose the Live voice and the conversation engine.":
        "Escolha a voz Live e o motor de conversa.",
    "The language used for the interface, assistant replies and speech.":
        "O idioma usado na interface, nas respostas e na fala do assistente.",
    "Choose the language used for the interface, assistant replies and speech.":
        "Escolha o idioma da interface, das respostas e da fala do assistente.",
    "Set the accent color used by the JARVIS HUD and controls.":
        "Defina a cor de destaque usada no HUD e nos controles do JARVIS.",
    "Enter a six-digit color such as #8262ff. A valid value previews immediately.":
        "Digite uma cor de seis d?gitos, como #8262ff. Um valor v?lido ? pr?-visualizado imediatamente.",
    "Leave blank to keep the currently saved key. Secret values are never displayed.":
        "Deixe em branco para manter a chave salva. Valores secretos nunca s?o exibidos.",
    "Paste a new Gemini API key to replace it": "Cole uma nova chave de API do Gemini para substitu?-la",
    "Paste your personal Gemini API key": "Cole sua chave pessoal de API do Gemini",
    "Paste a complete Gemini API key before continuing.":
        "Cole uma chave de API Gemini completa antes de continuar.",
    "Checking the API key securely. The secret is not displayed or logged.":
        "Verificando a chave de API com seguran?a. O segredo n?o ? exibido nem registrado.",
    "VALIDATING WITH GOOGLE...": "VALIDANDO COM O GOOGLE...",
    "VALIDATE AND CONNECT": "VALIDAR E CONECTAR",
    "API key validated and saved locally. JARVIS is ready.":
        "Chave de API validada e salva localmente. O JARVIS est? pronto.",
    "By blaackwood": "Por blaackwood",
    "Assistant identity": "Identidade do assistente",
    "Optional": "Opcional",
    "All categories": "Todas as categorias",
    "Input device": "Dispositivo de entrada",
    "Output device": "Dispositivo de sa?da",
    "Output level": "N?vel de sa?da",
    "Output level updated.": "N?vel de sa?da atualizado.",
    "The selected output does not expose a software volume control.":
        "A sa?da selecionada n?o oferece controle de volume por software.",
    "Devices saved. JARVIS is reconnecting to the selected audio path.":
        "Dispositivos salvos. O JARVIS est? reconectando ? rota de ?udio selecionada.",
    "Settings saved.": "Configura??es salvas.",
    "Search by category, key, value or date?": "Pesquise por categoria, chave, valor ou data?",
    "Persistent memory": "Mem?ria persistente",
    "Search and filter": "Pesquisar e filtrar",
    "Stored entries": "Registros salvos",
    "No memories match this filter.": "Nenhuma mem?ria corresponde a este filtro.",
    "IMPORT NOTE": "IMPORTAR ANOTA??O",
    "Installed extensions": "Extens?es instaladas",
    "Extension setup": "Configura??o de extens?es",
    "Extensions": "Extens?es",
    "SAVE SETTINGS": "SALVAR CONFIGURA??ES",
    "TEST CONNECTION": "TESTAR CONEX?O",
    "Enabled": "Ativado",
    "ERROR": "ERRO",
    "Remote access": "Acesso remoto",
    "Pairing session": "Sess?o de pareamento",
    "Connection link": "Link de conex?o",
    "Temporary access key": "Chave de acesso tempor?ria",
    "COPY LINK": "COPIAR LINK",
    "COPY KEY": "COPIAR CHAVE",
    "Dashboard unavailable": "Painel indispon?vel",
    "Create a temporary pairing session to connect another device to this JARVIS installation.":
        "Crie uma sess?o tempor?ria de pareamento para conectar outro dispositivo a esta instala??o do JARVIS.",
    "Use the temporary link or copy the access key to the other device.":
        "Use o link tempor?rio ou copie a chave de acesso para o outro dispositivo.",
    "The remote dashboard is not running or has not started yet. Start JARVIS again or enable its dashboard integration.":
        "O painel remoto n?o est? em execu??o ou ainda n?o foi iniciado. Reinicie o JARVIS ou ative a integra??o do painel.",
    "Create or manage a key in Google AI Studio ?":
        "Crie ou gerencie uma chave no Google AI Studio ?",
    "Assistant name": "Nome do assistente",
    "Your name": "Seu nome",
    "Gemini Live": "Gemini Live",
    "JARVIS Voice pipeline": "Pipeline de voz do JARVIS",
    "Assistant voice": "Voz do assistente",
    "Conversation engine": "Motor de conversa",
    "Accent color (hex)": "Cor de destaque (hex)",
    "JARVIS language": "Idioma do JARVIS",
    "By blaackwood": "Por blaackwood",
    "MODULE": "M?DULO",
    "OVERVIEW": "VIS?O GERAL",
    "SETUP": "CONFIGURA??O",
    "ENGINE": "MOTOR",
    "AUDIO": "?UDIO",
    "MEMORY": "MEM?RIA",
    "IDENTITY": "IDENTIDADE",
    "PLUGIN CFG": "CONFIG. PLUGINS",
    "REMOTE": "REMOTO",
    "FECHAR": "FECHAR",
    "PR?XIMA  ?": "PR?XIMA  ?",
    "RESPONDER": "RESPONDER",
    "Digite sua resposta...": "Digite sua resposta...",
    "TODAY ? 24 HOURS": "HOJE ? 24 HORAS",
    "SOURCES": "FONTES",
    "NEXT  ?": "PR?XIMA  ?",
    "FINISH  ?": "FINALIZAR  ?",
    "Correct answer": "Resposta correta",
    "Expected answer: ": "Resposta esperada: ",
    "Answer saved for review": "Resposta registrada para revis?o",
    "Type your answer...": "Digite sua resposta...",
    "CLOSE": "FECHAR",
    "SUBMIT": "RESPONDER",
    "+  NEW TASK": "+  NOVA TAREFA",
    "NEW TASK": "NOVA TAREFA",
    "New task": "Nova tarefa",
    "No due date": "Sem prazo",
    "This week": "Esta semana",
    "Done just now": "Feito agora",
    "Done yesterday": "Feito ontem",
    "Yesterday": "Ontem",
    "Paused": "Pausada",
    "Paused ": "Pausada ",
    "Reopen ": "Reabrir ",
    "Reopen panel": "Reabrir painel",
    "last: ": "?ltima: ",
    "next  ": "pr?xima  ",
    "Event": "Evento",
    "Monthly": "Mensal",
    "Once": "Uma vez",
    "At startup": "Ao abrir",
    "Male": "Masculina",
    "Female": "Feminina",
    "Speech speed": "Velocidade da fala",
    "Audio devices": "Dispositivos de ?udio",
    "Choose the microphone and audio output.": "Escolha o microfone e a sa?da de som.",
    "USB headset": "Headset USB",
    "Voice volume": "Volume da voz",
    "What JARVIS keeps between conversations.": "O que o JARVIS guarda entre as conversas.",
    "Keep conversations for": "Lembrar conversas por",
    "Always": "Sempre",
    "Clear memory": "Limpar mem?ria",
    "Clear now": "Limpar agora",
    "Memory cleared ?": "Mem?ria limpa ?",
    "Enable or disable extra capabilities.": "Ligue ou desligue as habilidades extras.",
    "Plugin settings": "Config. de plugins",
    "Fine-tune each plugin.": "Ajustes finos de cada plugin.",
    "News source": "Fonte de not?cias",
    "Google News": "Google Not?cias",
    "Results per search": "Resultados por pesquisa",
    "Language model": "Modelo de linguagem",
    "Speech recognition": "Reconhecimento de voz",
    "Speech synthesis": "S?ntese de voz",
    "Quick assistant controls (click to toggle)": "Controles r?pidos do assistente (clique para alternar)",
    "JARVIS settings": "Configura??es do Jarvis",
    "No due date": "Sem prazo",
    "Today": "Hoje",
    "Tomorrow": "Amanh?",
    "Listening to your command": "Ouvindo seu comando",
    "Understanding your request": "Interpretando o pedido",
    "Responding by voice": "Respondendo por voz",
    "Microphone muted": "Microfone mudo",
    "Microphone on": "Microfone ligado",
    "Nothing to interrupt": "Nada para interromper",
    "Speech interrupted": "Fala interrompida",
    "Assistant idle": "Assistente em espera",
    "Orb: ": "Esfera: ",
    "hologram": "holograma",
    "neural core": "n?cleo neural",
    "on": "ligado",
    "off": "desligado",
    "Task: ": "Tarefa: ",
    "IDLE": "EM ESPERA",
    "LISTENING": "ESCUTANDO",
    "WAITING FOR INPUT": "AGUARDANDO CHAMADA",
})


# Final consistency pass for labels that are still authored in the HUD source.
PT_TO_EN.update({
    "Configura??es do Jarvis": "JARVIS settings",
    "JARVIS - novo visual (previa)": "JARVIS - new interface (preview)",
    "JARVIS SYSTEMS  ?  DESKTOP": "JARVIS  ?  DESKTOP SYSTEM",
    "1-4 estados  N not?cias  S pesquisa  H in?cio  T tarefas  R rotinas  C controles  G config  M mudo  I interromper  O esfera  Espa?o demo  F11  Esc":
        "1-4 states  N news  S search  H home  T tasks  R routines  C controls  G settings  M mute  I interrupt  O orb  Space demo  F11  Esc",
    "SISTEMA ONLINE": "SYSTEM ONLINE",
    "CONFIGURA??ES DO JARVIS": "JARVIS SETTINGS",
    "CONFIGURE EXTENSION SETTINGS  ?": "CONFIGURAR AJUSTES DE EXTENS?ES  ?",
})
EN_TO_PT.update({
    "CONFIGURE EXTENSION SETTINGS  ?": "CONFIGURAR AJUSTES DE EXTENS?ES  ?",
    "JARVIS  /  CONFIGURA??ES DO SISTEMA": "JARVIS  /  SYSTEM SETTINGS",
    "Testing?": "Testando?",
    "?  SYSTEM ONLINE": "?  SISTEMA ONLINE",
    '<a href="https://aistudio.google.com/apikey">Create or manage a key in Google AI Studio ?</a>':
        '<a href="https://aistudio.google.com/apikey">Crie ou gerencie uma chave no Google AI Studio ?</a>',
})


# UTF-8 canonical overrides for HUD/workspace labels.
PT_TO_EN.update({
    "Configura\u00e7\u00f5es do Jarvis": "JARVIS settings",
    "JARVIS  /  CONFIGURA\u00c7\u00d5ES DO SISTEMA": "JARVIS  /  SYSTEM SETTINGS",
    "JARVIS - novo visual (previa)": "JARVIS - new interface (preview)",
    "JARVIS SYSTEMS  \u00b7  DESKTOP": "JARVIS  \u00b7  DESKTOP SYSTEM",
    "1-4 estados  N not\u00edcias  S pesquisa  H in\u00edcio  T tarefas  R rotinas  C controles  G config  M mudo  I interromper  O esfera  Espa\u00e7o demo  F11  Esc":
        "1-4 states  N news  S search  H home  T tasks  R routines  C controls  G settings  M mute  I interrupt  O orb  Space demo  F11  Esc",
    "SISTEMA ONLINE": "SYSTEM ONLINE",
    "CONTROLES": "CONTROLS", "CONFIG": "SETTINGS",
    "IN\u00cdCIO": "HOME", "TAREFAS": "TASKS", "ROTINAS": "ROUTINES",
})
EN_TO_PT.update({
    "JARVIS SYSTEMS  \u00b7  DESKTOP": "JARVIS  \u00b7  SISTEMA DESKTOP",
    "JARVIS  /  CONFIGURA\u00c7\u00d5ES DO SISTEMA": "JARVIS  /  CONFIGURA\u00c7\u00d5ES DO SISTEMA",
    "CONFIGURE EXTENSION SETTINGS  \u2192": "CONFIGURAR AJUSTES DE EXTENS\u00d5ES  \u2192",
    "Testing\u2026": "Testando\u2026",
    "\u25cf  SYSTEM ONLINE": "\u25cf  SISTEMA ONLINE",
    '<a href="https://aistudio.google.com/apikey">Create or manage a key in Google AI Studio \u2197</a>':
        '<a href="https://aistudio.google.com/apikey">Crie ou gerencie uma chave no Google AI Studio \u2197</a>',
    "NEXT  \u2192": "PR\u00d3XIMA  \u2192",
    "FINISH  \u2192": "FINALIZAR  \u2192",
    "SUBMIT": "RESPONDER",
    "CLOSE": "FECHAR",
    "TODAY \u00b7 24 HOURS": "HOJE \u00b7 24 HORAS",
    "SOURCES": "FONTES",
})


# Quiz controls and dialog/status copy.
PT_TO_EN.update({
    "FECHAR": "CLOSE",
    "PR\u00d3XIMA  \u2192": "NEXT  \u2192",
    "FINALIZAR  \u2192": "FINISH  \u2192",
    "RESPONDER": "SUBMIT",
    "Digite sua resposta...": "Type your answer...",
    "Resposta correta": "Correct answer",
    "Resposta esperada: ": "Expected answer: ",
    "Resposta registrada para revis\u00e3o": "Answer saved for review",
    "HOJE \u00b7 24 HORAS": "TODAY \u00b7 24 HOURS",
    "Fontes": "Sources",
    "FONTES": "SOURCES",
})
EN_TO_PT.update({
    "NEXT  \u2192": "PR\u00d3XIMA  \u2192",
    "FINISH  \u2192": "FINALIZAR  \u2192",
    "SUBMIT": "RESPONDER",
    "CLOSE": "FECHAR",
    "Type your answer...": "Digite sua resposta...",
    "Correct answer": "Resposta correta",
    "Expected answer: ": "Resposta esperada: ",
    "Answer saved for review": "Resposta registrada para revis\u00e3o",
    "TODAY \u00b7 24 HOURS": "HOJE \u00b7 24 HORAS",
    "Sources": "Fontes",
    "Edit memory": "Editar mem\u00f3ria",
    "Confirm update": "Confirmar atualiza\u00e7\u00e3o",
    "Replace this saved memory item?": "Substituir este item de mem\u00f3ria salvo?",
    "Possible duplicate": "Poss\u00edvel duplicata",
    "This memory resembles another saved entry. Store it anyway?":
        "Esta mem\u00f3ria se parece com outro registro salvo. Deseja armazen\u00e1-la mesmo assim?",
    "Memory unchanged": "Mem\u00f3ria inalterada",
    "The item was not updated: ": "O item n\u00e3o foi atualizado: ",
    "Memory error": "Erro de mem\u00f3ria",
    "Confirm deletion": "Confirmar exclus\u00e3o",
    "Forget this saved memory?": "Esquecer esta mem\u00f3ria salva?",
    "Import memory": "Importar mem\u00f3ria",
    "Short title:": "T\u00edtulo curto:",
    "Paste information JARVIS should remember (up to 12,000 characters):":
        "Cole as informa\u00e7\u00f5es que o JARVIS deve lembrar (at\u00e9 12.000 caracteres):",
    "Memory imported": "Mem\u00f3ria importada",
    "Saved ": "Salvo ",
    " searchable memory part(s).": " trecho(s) pesquis\u00e1vel(is) na mem\u00f3ria.",
    "Import failed": "Falha na importa\u00e7\u00e3o",
    "Paste a complete Gemini API key before continuing.":
        "Cole uma chave de API Gemini completa antes de continuar.",
    "Checking the API key securely. The secret is not displayed or logged.":
        "Verificando a chave de API com seguran\u00e7a. O segredo n\u00e3o \u00e9 exibido nem registrado.",
    "The API validation service could not start. Check the installation and try again.":
        "O servi\u00e7o de valida\u00e7\u00e3o da API n\u00e3o p\u00f4de iniciar. Verifique a instala\u00e7\u00e3o e tente novamente.",
    "The API key could not be validated.": "N\u00e3o foi poss\u00edvel validar a chave de API.",
    "The API key was validated, but local setup could not be saved: ":
        "A chave de API foi validada, mas a configura\u00e7\u00e3o local n\u00e3o p\u00f4de ser salva: ",
    "Could not change output level: ": "N\u00e3o foi poss\u00edvel alterar o n\u00edvel de sa\u00edda: ",
    "Could not save audio devices: ": "N\u00e3o foi poss\u00edvel salvar os dispositivos de \u00e1udio: ",
    "Could not save settings: ": "N\u00e3o foi poss\u00edvel salvar as configura\u00e7\u00f5es: ",
    "Test completed.": "Teste conclu\u00eddo.",
})


# Live state, activity log and dynamic operation labels.
PT_TO_EN.update({
    "EM ESPERA": "IDLE",
    "ESCUTANDO": "LISTENING",
    "PENSANDO": "THINKING",
    "FALANDO": "SPEAKING",
    "Aguardando chamada": "Waiting for input",
    "Ouvindo seu comando": "Listening to your command",
    "Interpretando o pedido": "Understanding your request",
    "Respondendo por voz": "Responding by voice",
    "Microfone mudo": "Microphone muted",
    "Microfone ligado": "Microphone on",
    "Nada para interromper": "Nothing to interrupt",
    "Fala interrompida": "Speech interrupted",
    "Assistente em espera": "Assistant idle",
    "Esfera: ": "Orb: ",
    "n\u00facleo neural": "neural core",
    "ligado": "on",
    "desligado": "off",
    "Tarefa: ": "Task: ",
    "Falhou: ": "Failed: ",
    "Detalhe indispon\u00edvel: ": "Detail unavailable: ",
    "Rotina n\u00e3o alterada: ": "Routine unchanged: ",
    "Test completed.": "Teste conclu\u00eddo.",
    "Never run": "Nunca executada",
    "Running": "Em execu\u00e7\u00e3o",
    "Queued": "Na fila",
    "Scheduled": "Agendada",
    "Waiting quota": "Aguardando cota",
    "Paused": "Pausada",
    "Cancelled": "Cancelada",
    "Failed": "Falhou",
    "Completed": "Conclu\u00edda",
})
EN_TO_PT.update({
    "IDLE": "EM ESPERA",
    "LISTENING": "ESCUTANDO",
    "THINKING": "PENSANDO",
    "SPEAKING": "FALANDO",
    "Waiting for input": "Aguardando chamada",
    "Microphone muted": "Microfone mudo",
    "Microphone on": "Microfone ligado",
    "Nothing to interrupt": "Nada para interromper",
    "Speech interrupted": "Fala interrompida",
    "Assistant idle": "Assistente em espera",
    "Orb: ": "Esfera: ",
    "neural core": "n\u00facleo neural",
    "Task: ": "Tarefa: ",
    "Failed: ": "Falhou: ",
    "Detail unavailable: ": "Detalhe indispon\u00edvel: ",
    "Routine unchanged: ": "Rotina n\u00e3o alterada: ",
    "Never run": "Nunca executada",
    "Running": "Em execu\u00e7\u00e3o",
    "Queued": "Na fila",
    "Scheduled": "Agendada",
    "Waiting quota": "Aguardando cota",
    "Cancelled": "Cancelada",
    "Failed": "Falhou",
    "Completed": "Conclu\u00edda",
})


# Canonical UTF-8 translations override legacy labels and guarantee one UI locale.
PT_TO_EN.update({
    "Configura\u00e7\u00f5es do Jarvis": "JARVIS settings",
    "Controles r\u00e1pidos do assistente (clique para alternar)": "Quick assistant controls (click to toggle)",
    "C\u00f3digo de pareamento": "Pairing code",
    "Atalho na \u00e1rea de trabalho": "Desktop shortcut",
    "Cria um \u00edcone para abrir o Jarvis com um clique.": "Creates a shortcut to open JARVIS with one click.",
    "In\u00edcio autom\u00e1tico": "Automatic startup",
    "Dispositivos de \u00e1udio": "Audio devices",
    "Escolha o microfone e a sa\u00edda de som.": "Choose the microphone and audio output.",
    "Limpar mem\u00f3ria": "Clear memory",
    "Mem\u00f3ria limpa \u2713": "Memory cleared \u2713",
    "Fonte de not\u00edcias": "News source",
    "Google Not\u00edcias": "Google News",
    "S\u00edntese de voz": "Speech synthesis",
    "HOJE \u00b7 24 HORAS": "TODAY \u00b7 24 HOURS",
    "\u00faltima: ": "last: ",
    "pr\u00f3xima  ": "next  ",
    "PR\u00d3XIMA  \u2192": "NEXT  \u2192",
    "FINALIZAR  \u2192": "FINISH  \u2192",
    "Resposta registrada para revis\u00e3o": "Answer saved for review",
    "Amanh\u00e3": "Tomorrow",
    "Conclu\u00eddo": "Completed",
    "Conclu\u00edda": "Completed",
    "CONCLU\u00cdDA": "COMPLETED",
    "n\u00facleo neural": "neural core",
    "JARVIS SYSTEMS  \u00b7  DESKTOP": "JARVIS  \u00b7  DESKTOP SYSTEM",
    "JARVIS - novo visual (pr\u00e9via)": "JARVIS - new interface (preview)",
    "NEURAL INTERFACE  \u00b7  CONTROL PLANE": "NEURAL INTERFACE  \u00b7  CONTROL PLANE",
    "EM ESPERA": "IDLE",
    "ESCUTANDO": "LISTENING",
    "PENSANDO": "THINKING",
    "FALANDO": "SPEAKING",
    "Aguardando chamada": "Waiting for input",
    "Ouvindo seu comando": "Listening to your command",
    "Interpretando o pedido": "Understanding your request",
    "Respondendo por voz": "Responding by voice",
    "Microfone mudo": "Microphone muted",
    "Microfone ligado": "Microphone on",
    "Nada para interromper": "Nothing to interrupt",
    "Fala interrompida": "Speech interrupted",
    "Assistente em espera": "Assistant idle",
    "Esfera: ": "Orb: ",
    "Tarefa: ": "Task: ",
    "Falhou: ": "Failed: ",
    "Detalhe indispon\u00edvel: ": "Detail unavailable: ",
    "Rotina n\u00e3o alterada: ": "Routine unchanged: ",
})
EN_TO_PT.update({
    "JARVIS  /  SYSTEM SETTINGS": "JARVIS  /  CONFIGURA\u00c7\u00d5ES DO SISTEMA",
    "JARVIS  /  CONFIGURA\u00c7\u00d5ES DO SISTEMA": "JARVIS  /  CONFIGURA\u00c7\u00d5ES DO SISTEMA",
    "JARVIS SYSTEMS  \u00b7  DESKTOP": "JARVIS  \u00b7  SISTEMA DESKTOP",
    "NEURAL INTERFACE  \u00b7  CONTROL PLANE": "INTERFACE NEURAL  \u00b7  PAINEL DE CONTROLE",
    "LIVE CONFIGURATION  \u00b7  LOCAL SECRETS STAY MASKED  \u00b7  CHANGES APPLY THROUGH THE ORIGINAL ENGINE":
        "CONFIGURA\u00c7\u00c3O AO VIVO  \u00b7  SEGREDOS LOCAIS PROTEGIDOS  \u00b7  ALTERA\u00c7\u00d5ES APLICADAS AO MOTOR ORIGINAL",
    "MODULE": "M\u00d3DULO", "OVERVIEW": "VIS\u00c3O GERAL",
    "SETUP": "CONFIGURA\u00c7\u00c3O", "AUDIO": "\u00c1UDIO",
    "MEMORY": "MEM\u00d3RIA", "IDENTITY": "IDENTIDADE",
    "PLUGIN CFG": "CONFIG. PLUGINS", "REMOTE": "REMOTO",
    "Voice and audio": "Voz e \u00e1udio",
    "Personalize the JARVIS interface and conversation. Changes are applied to the running session.":
        "Personalize a interface e a conversa do JARVIS. As altera\u00e7\u00f5es s\u00e3o aplicadas \u00e0 sess\u00e3o em execu\u00e7\u00e3o.",
    "Enter a six-digit color such as #8262ff. A valid value previews immediately.":
        "Digite uma cor de seis d\u00edgitos, como #8262ff. Um valor v\u00e1lido \u00e9 pr\u00e9-visualizado imediatamente.",
    "Paste a new Gemini API key to replace it": "Cole uma nova chave de API do Gemini para substitu\u00ed-la",
    "Checking the API key securely. The secret is not displayed or logged.":
        "Verificando a chave de API com seguran\u00e7a. O segredo n\u00e3o \u00e9 exibido nem registrado.",
    "API key validated and saved locally. JARVIS is ready.":
        "Chave de API validada e salva localmente. O JARVIS est\u00e1 pronto.",
    "Output device": "Dispositivo de sa\u00edda",
    "Output level": "N\u00edvel de sa\u00edda",
    "Output level updated.": "N\u00edvel de sa\u00edda atualizado.",
    "The selected output does not expose a software volume control.":
        "A sa\u00edda selecionada n\u00e3o oferece controle de volume por software.",
    "Devices saved. JARVIS is reconnecting to the selected audio path.":
        "Dispositivos salvos. O JARVIS est\u00e1 reconectando \u00e0 rota de \u00e1udio selecionada.",
    "Settings saved.": "Configura\u00e7\u00f5es salvas.",
    "Search by category, key, value or date\u2026": "Pesquise por categoria, chave, valor ou data\u2026",
    "Persistent memory": "Mem\u00f3ria persistente",
    "No memories match this filter.": "Nenhuma mem\u00f3ria corresponde a este filtro.",
    "IMPORT NOTE": "IMPORTAR ANOTA\u00c7\u00c3O",
    "Installed extensions": "Extens\u00f5es instaladas",
    "Extension setup": "Configura\u00e7\u00e3o de extens\u00f5es",
    "Extensions": "Extens\u00f5es",
    "SAVE SETTINGS": "SALVAR CONFIGURA\u00c7\u00d5ES",
    "TEST CONNECTION": "TESTAR CONEX\u00c3O",
    "Pairing session": "Sess\u00e3o de pareamento",
    "Connection link": "Link de conex\u00e3o",
    "Temporary access key": "Chave de acesso tempor\u00e1ria",
    "Dashboard unavailable": "Painel indispon\u00edvel",
    "Create a temporary pairing session to connect another device to this JARVIS installation.":
        "Crie uma sess\u00e3o tempor\u00e1ria de pareamento para conectar outro dispositivo a esta instala\u00e7\u00e3o do JARVIS.",
    "Use the temporary link or copy the access key to the other device.":
        "Use o link tempor\u00e1rio ou copie a chave de acesso para o outro dispositivo.",
    "The remote dashboard is not running or has not started yet. Start JARVIS again or enable its dashboard integration.":
        "O painel remoto n\u00e3o est\u00e1 em execu\u00e7\u00e3o ou ainda n\u00e3o foi iniciado. Reinicie o JARVIS ou ative a integra\u00e7\u00e3o do painel.",
    "Create or manage a key in Google AI Studio \u2197":
        "Crie ou gerencie uma chave no Google AI Studio \u2197",
    "NEXT  \u2192": "PR\u00d3XIMA  \u2192",
    "FINISH  \u2192": "FINALIZAR  \u2192",
    "TODAY \u00b7 24 HOURS": "HOJE \u00b7 24 HORAS",
    "Audio devices": "Dispositivos de \u00e1udio",
    "Choose the microphone and audio output.": "Escolha o microfone e a sa\u00edda de som.",
    "Clear memory": "Limpar mem\u00f3ria",
    "Memory cleared \u2713": "Mem\u00f3ria limpa \u2713",
    "News source": "Fonte de not\u00edcias",
    "Google News": "Google Not\u00edcias",
    "Speech synthesis": "S\u00edntese de voz",
    "JARVIS settings": "Configura\u00e7\u00f5es do JARVIS",
    "Tomorrow": "Amanh\u00e3",
    "neural core": "n\u00facleo neural",
    "last: ": "\u00faltima: ",
    "next  ": "pr\u00f3xima  ",
    "Test completed.": "Teste conclu\u00eddo.",
})


# HUD controls and built-in settings choices.
PT_TO_EN.update({
    "Desligado": "OFF", "Ligado": "ON",
    "DESLIGADO": "OFF", "LIGADO": "ON",
    "Masculina": "Male", "Feminina": "Female",
    "Portugu\u00eas (BR)": "Portuguese (Brazil)", "Ingl\u00eas": "English",
    "Lenta": "Slow", "Normal": "Normal", "R\u00e1pida": "Fast",
    "Microfone padr\u00e3o": "Default microphone",
    "Alto-falantes": "Speakers", "Fones de ouvido": "Headphones",
    "Masculino": "Male", "Feminino": "Female",
    "PARAR": "STOP", "SAIR": "EXIT", "ENTRAR": "ENTER", "DORMIR": "SLEEP",
    "Microfone": "Microphone",
    "Interromper": "Interrupt",
    "Tela cheia": "Full screen",
    "Dormir agora": "Sleep now",
    "Resumo da manh\u00e3": "Morning briefing",
    "Palavra de ativa\u00e7\u00e3o": "Wake word",
    "Apertar para falar": "Push to talk",
    "Visual da esfera": "Orb appearance",
    "Desligado, o Jarvis para de escutar": "When off, JARVIS stops listening",
    "Para a fala e volta ao repouso": "Stops speech and returns to idle",
    "Alterna o modo tela cheia (F11)": "Toggles full-screen mode (F11)",
    "Coloca o assistente em espera": "Puts the assistant on standby",
    "Fala not\u00edcias e agenda ao acordar": "Reads news and calendar when you wake up",
    "Responde quando ouvir o nome dele": "Responds when it hears its name",
    "S\u00f3 escuta com a tecla pressionada": "Only listens while the key is held",
    "Alterna holograma e n\u00facleo neural": "Switches between hologram and neural core",
    "Atalho": "Shortcut",
    "In\u00edcio autom\u00e1tico": "Automatic startup",
    "Velocidade da fala": "Speech speed",
    "Volume da voz": "Voice volume",
    "Mem\u00f3ria de longo prazo": "Long-term memory",
    "Lembrar conversas por": "Remember conversations for",
    "Limpar mem\u00f3ria": "Clear memory",
    "Pesquisa na web": "Web search",
    "Not\u00edcias": "News",
    "Agenda": "Calendar",
    "Controle do PC": "PC control",
    "Fonte de not\u00edcias": "News source",
    "Resultados por pesquisa": "Results per search",
    "Modelo de linguagem": "Language model",
    "Reconhecimento de voz": "Speech recognition",
    "S\u00edntese de voz": "Speech synthesis",
    "Seg": "Mon", "Ter": "Tue", "Qua": "Wed", "Qui": "Thu",
    "Sex": "Fri", "S\u00e1b": "Sat", "Dom": "Sun",
    "Todo dia": "Every day", "Dias \u00fateis": "Weekdays",
    "Fim de semana": "Weekend",
})
EN_TO_PT.update({
    "OFF": "DESLIGADO", "ON": "LIGADO",
    "Male": "Masculina", "Female": "Feminina",
    "Portuguese (Brazil)": "Portugu\u00eas (BR)", "English": "Ingl\u00eas",
    "Slow": "Lenta", "Fast": "R\u00e1pida",
    "Default microphone": "Microfone padr\u00e3o",
    "Speakers": "Alto-falantes", "Headphones": "Fones de ouvido",
    "STOP": "PARAR", "EXIT": "SAIR", "ENTER": "ENTRAR", "SLEEP": "DORMIR",
    "Microphone": "Microfone",
    "Interrupt": "Interromper",
    "Full screen": "Tela cheia",
    "Sleep now": "Dormir agora",
    "Morning briefing": "Resumo da manh\u00e3",
    "Wake word": "Palavra de ativa\u00e7\u00e3o",
    "Push to talk": "Apertar para falar",
    "Orb appearance": "Visual da esfera",
    "When off, JARVIS stops listening": "Desligado, o Jarvis para de escutar",
    "Stops speech and returns to idle": "Para a fala e volta ao repouso",
    "Toggles full-screen mode (F11)": "Alterna o modo tela cheia (F11)",
    "Puts the assistant on standby": "Coloca o assistente em espera",
    "Reads news and calendar when you wake up": "Fala not\u00edcias e agenda ao acordar",
    "Responds when it hears its name": "Responde quando ouvir o nome dele",
    "Only listens while the key is held": "S\u00f3 escuta com a tecla pressionada",
    "Switches between hologram and neural core": "Alterna holograma e n\u00facleo neural",
    "Long-term memory": "Mem\u00f3ria de longo prazo",
    "Remember conversations for": "Lembrar conversas por",
    "Web search": "Pesquisa na web",
    "News": "Not\u00edcias", "Calendar": "Agenda",
    "PC control": "Controle do PC",
    "Mon": "Seg", "Tue": "Ter", "Wed": "Qua", "Thu": "Qui",
    "Fri": "Sex", "Sat": "S\u00e1b", "Sun": "Dom",
    "Every day": "Todo dia", "Weekdays": "Dias \u00fateis",
    "Weekend": "Fim de semana",
})


# Overview and identity copy used by the workspace panels.
EN_TO_PT.update({
    "Neural control center": "Central de controle neural",
    "Live configuration and system modules \u2014 connected directly to this JARVIS installation.":
        "Configura\u00e7\u00e3o ao vivo e m\u00f3dulos do sistema \u2014 conectados diretamente a esta instala\u00e7\u00e3o do JARVIS.",
    "ENGINE CORE": "N\u00daCLEO DO MOTOR",
    "VOICE & AUDIO": "VOZ E \u00c1UDIO",
    "MEMORY": "MEM\u00d3RIA",
    "EXTENSIONS": "EXTENS\u00d5ES",
    "IDENTITY": "IDENTIDADE",
    "REMOTE ACCESS": "ACESSO REMOTO",
    "Microphone, speakers, voice route and input/output levels.":
        "Microfone, alto-falantes, rota de voz e n\u00edveis de entrada e sa\u00edda.",
    "Inspect, search, update and remove stored memories.":
        "Consulte, pesquise, atualize e remova mem\u00f3rias salvas.",
    "Installed plugins, capabilities and their configuration.":
        "Plugins instalados, recursos e suas configura\u00e7\u00f5es.",
    "Secure access session and device pairing.":
        "Sess\u00e3o de acesso seguro e pareamento de dispositivos.",
    "Assistant name, voice, color and conversation mode.":
        "Nome do assistente, voz, cor e modo de conversa.",
    "Leave blank when you prefer the assistant to address you automatically.":
        "Deixe em branco para que o assistente se dirija a voc\u00ea automaticamente.",
    "Routing for hearing, reasoning, speaking, background requests and coding.":
        "Rotas para ouvir, raciocinar, falar, executar solicita\u00e7\u00f5es em segundo plano e programar.",
    "Select the real input/output devices and test the signal path.":
        "Selecione os dispositivos reais de entrada e sa\u00edda e teste a rota de sinal.",
    "Review and maintain the assistant's persistent memory.":
        "Consulte e mantenha a mem\u00f3ria persistente do assistente.",
    "Enable or disable installed capabilities.": "Ative ou desative os recursos instalados.",
    "Configure credentials and settings for connected modules.":
        "Configure credenciais e ajustes dos m\u00f3dulos conectados.",
    "Assistant identity, voice, appearance and conversation engine.":
        "Identidade, voz, apar\u00eancia e motor de conversa do assistente.",
    "Generate a secure pairing session for another device.":
        "Gere uma sess\u00e3o segura de pareamento para outro dispositivo.",
    "Connect JARVIS to its conversation service and finish the local setup.":
        "Conecte o JARVIS ao servi\u00e7o de conversa e conclua a configura\u00e7\u00e3o local.",
    "Neural control center": "Central de controle neural",
    "ENGINE STATUS UNAVAILABLE": "STATUS DO MOTOR INDISPON\u00cdVEL",
    "BACK TO SYSTEM": "VOLTAR AO SISTEMA",
    "MANAGE MODELS  \u2192": "GERENCIAR MODELOS  \u2192",
    "CONFIGURE AUDIO  \u2192": "CONFIGURAR \u00c1UDIO  \u2192",
    "OPEN MEMORY  \u2192": "ABRIR MEM\u00d3RIA  \u2192",
    "MANAGE EXTENSIONS  \u2192": "GERENCIAR EXTENS\u00d5ES  \u2192",
    "CUSTOMIZE JARVIS  \u2192": "PERSONALIZAR JARVIS  \u2192",
    "OPEN REMOTE  \u2192": "ABRIR ACESSO REMOTO  \u2192",
    "Leave blank when you prefer the assistant to address you automatically.":
        "Deixe em branco para que o assistente se dirija a voc\u00ea automaticamente.",
})
PT_TO_EN.update({
    "N\u00daCLEO DO MOTOR": "ENGINE CORE",
    "VOZ E \u00c1UDIO": "VOICE & AUDIO",
    "ACESSO REMOTO": "REMOTE ACCESS",
    "Microfone, alto-falantes, rota de voz e n\u00edveis de entrada e sa\u00edda.":
        "Microphone, speakers, voice route and input/output levels.",
    "Consulte, pesquise, atualize e remova mem\u00f3rias salvas.":
        "Inspect, search, update and remove stored memories.",
    "Plugins instalados, recursos e suas configura\u00e7\u00f5es.":
        "Installed plugins, capabilities and their configuration.",
    "Sess\u00e3o de acesso seguro e pareamento de dispositivos.":
        "Secure access session and device pairing.",
    "Nome do assistente, voz, cor e modo de conversa.":
        "Assistant name, voice, color and conversation mode.",
    "Deixe em branco para que o assistente se dirija a voc\u00ea automaticamente.":
        "Leave blank when you prefer the assistant to address you automatically.",
    "Central de controle neural": "Neural control center",
    "Configura\u00e7\u00e3o ao vivo e m\u00f3dulos do sistema \u2014 conectados diretamente a esta instala\u00e7\u00e3o do JARVIS.":
        "Live configuration and system modules \u2014 connected directly to this JARVIS installation.",
    "VIS\u00c3O GERAL": "OVERVIEW",
})


# Final help-text corrections.
EN_TO_PT.update({
    "Leave blank to keep the currently saved key. Secret values are never displayed.":
        "Deixe em branco para manter a chave salva. Valores secretos nunca s\u00e3o exibidos.",
    "Quick assistant controls (click to toggle)":
        "Controles r\u00e1pidos do assistente (clique para alternar)",
    "NEURAL INTERFACE  \u00b7  CONTROL PLANE":
        "INTERFACE NEURAL  \u00b7  PAINEL DE CONTROLE",
    "LIVE CONFIGURATION  \u00b7  LOCAL SECRETS STAY MASKED  \u00b7  CHANGES APPLY THROUGH THE ORIGINAL ENGINE":
        "CONFIGURA\u00c7\u00c3O AO VIVO  \u00b7  SEGREDOS LOCAIS PROTEGIDOS  \u00b7  ALTERA\u00c7\u00d5ES APLICADAS AO MOTOR ORIGINAL",
})
