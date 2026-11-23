# JARVIS

**A desktop AI assistant created by blaackwood.**

Português: [README.pt-BR.md](README.pt-BR.md)

JARVIS is a local-first desktop assistant with a holographic interface, live
voice conversation, computer and browser control, specialized actions, coding
workflows, persistent memory, scheduled tasks, visual lessons, and optional
remote integrations.

The main conversation engine is Google Gemini Live. Every installation must
use the installing user's own Gemini API key. No developer key, personal
memory, conversation archive, or local account configuration is included.

> JARVIS is a desktop application, not a hosted SaaS service. Capabilities
> depend on the operating system, local permissions, optional dependencies,
> and external accounts the user chooses to configure.

## What JARVIS can do

- **Talk and listen:** live voice conversations, spoken responses, configurable
  voice and audio devices, push-to-talk, microphone controls, and optional
  local wake-word activation.
- **Control the desktop:** inspect visible applications, interact with
  accessible controls, use mouse/keyboard automation, capture the screen,
  manage windows, and annotate the desktop with visual pointers.
- **Work with files:** open, inspect, search, create, move, copy, rename and
  delete files; process a file explicitly selected or dropped into JARVIS.
- **Browse the web:** navigate websites, search, click, type, scroll, read pages,
  manage tabs, play YouTube media, and look up weather and flight options.
- **Build software:** edit and explain code, create new projects, work on
  existing projects through coding agents, run checks, and use the separate
  JARVIS Agent workbench.
- **Remember and organize work:** local conversation history, semantic memory,
  project context, reminders, recurring routines, focus sessions, and
  background tasks.
- **Teach visually:** holographic 3D scenes, annotated diagrams, guided visual
  lessons, and dedicated chess assistant, coach, and teacher tools.
- **Extend the assistant:** 39 third-party Skills are redistributed with their
  original licences; optional provider, GitHub, Cloudflare, dashboard, and
  desktop-agent integrations are documented separately.

The complete action catalogue is in FEATURES.md. Skill origins and licence
status are in SKILLS.md.

## First run: your own Gemini API key

1. Install Python 3.11 to 3.13 (Python 3.13 is the tested target) and Git.
2. Clone this repository and enter its directory.
3. Create a virtual environment, install requirements, and run JARVIS:

   ~~~powershell
   py -3.13 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   $env:PYTHONUTF8 = "1"
   python setup.py
   python main.py
   ~~~

4. On first launch, the setup screen asks for your own Gemini API key.
   Create one in Google AI Studio (https://aistudio.google.com/apikey),
   paste it into JARVIS, and validate it. The main interface stays locked
   until Google accepts the key.

The key is saved locally in config/api_keys.json. It is ignored by Git, but
the current configuration implementation stores it as plain text. Protect
your operating-system account and never share or commit that file. API usage
and any charges belong to your own Google account.

See INSTALLATION.md for optional components and troubleshooting.

## Optional components

- **Stockfish:** chess features require a separately downloaded Stockfish UCI
  engine. The executable is not bundled in this repository.
- **OpenCode / Codex:** coding-agent workflows require their respective CLI
  installations and user sign-in.
- **Cloudflare reminders:** deploy the optional Worker and D1 database using
  your own Cloudflare account and secrets.
- **Remote dashboard:** pair a phone with the local dashboard from JARVIS
  settings; keep the pairing code private.
- **Local wake word and local speech:** optional model/runtime downloads.
- **Other providers and services:** configure each provider's own key or
  account in JARVIS settings.

## Privacy and security

JARVIS runs desktop tools locally, but it is not offline-only. Live voice
conversation uses Google's Gemini service. The file processor sends the file
the user explicitly selects to the configured Gemini model for analysis.
Other cloud providers and integrations receive the data needed for the
operation the user requests.

JARVIS includes authorization checks and confirmation gates for sensitive
operations. Review SECURITY.md before enabling desktop automation or external
integrations.

No API keys, user memory, chat histories, task queues, private project data,
logs, screenshots, or local provider configuration are part of this source
distribution.

## Platforms

The setup script supports Windows, macOS, and Linux dependency markers, but
OS-specific functions differ. The complete desktop workflow and installer are
primarily developed for Windows 10/11. The native wake daemon and Windows UI
Automation path are Windows-only.

## Licensing and attribution

- Original JARVIS source code is licensed under the MIT License (LICENSE),
  copyright blaackwood.
- Third-party Skills, assets, engines, libraries, and dependencies retain
  their original licences. See THIRD_PARTY_NOTICES.md and SKILLS.md.
- Three Skill entries without an explicit redistribution licence at
  their pinned commit are reference-only and are not copied here.

The JARVIS MIT licence does not relicense any third-party component.
