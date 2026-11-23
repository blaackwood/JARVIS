# Installation guide

## Requirements

- Python 3.11 to 3.13 (3.13 is the tested target).
- Git.
- Windows 10/11 for the complete desktop-control workflow. macOS/Linux
  dependency markers are supported, but OS-specific tools differ.
- Microphone and speakers/headphones for voice conversation.
- Internet access for Gemini Live, web search and browser automation.

## Install from source

### Windows PowerShell

~~~powershell
git clone https://github.com/blaackwood/JARVIS.git
cd JARVIS
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
$env:PYTHONUTF8 = "1"
python setup.py
python main.py
~~~

### macOS / Linux

~~~bash
git clone https://github.com/blaackwood/JARVIS.git
cd JARVIS
python3.13 -m venv .venv
source .venv/bin/activate
export PYTHONUTF8=1
python setup.py
python main.py
~~~

The setup script installs dependency markers for the current platform and
tries to install Playwright Chromium and Firefox. Browser installation can
be retried with:

~~~bash
python -m playwright install chromium firefox
~~~

## First-run API configuration

JARVIS requires the user's own Gemini API key. Create one in Google AI Studio,
start the app, paste the key into the protected setup field, and validate it.
The first-run gate does not accept a blank key or a local-only shortcut.

The key is written to config/api_keys.json. The file is excluded by Git,
but the current implementation stores it in plain text. Protect your operating
system account and never share or commit that file.

## Optional capabilities

### Stockfish chess engine

Download a platform-appropriate Stockfish build from
https://stockfishchess.org/download/. Place the executable in tools/stockfish/,
add it to PATH, or configure its path in the chess tool. The executable is not
included in this repository. See tools/stockfish/README.md.

### OpenCode and Codex coding agents

The existing-project coding agent requires the OpenCode CLI to be installed
and authenticated separately. The JARVIS Agent workbench can also connect to
the official Codex App Server through the Codex CLI; install the CLI and sign
in with your own eligible account. Neither CLI nor its credentials is bundled.

### Agent workbench desktop shell

The local web workbench can be started from the repository root with:

~~~powershell
.\.venv\Scripts\python.exe _jarvis_agent_ui\server.py
~~~

For the Electron wrapper, install Node.js, then run:

~~~powershell
cd _jarvis_agent_ui\desktop
npm install
npm start
~~~

Set JARVIS_ROOT if the Electron wrapper is launched from a location where it
cannot infer the repository root. User task history and approvals are created
locally under _jarvis_agent_ui/data/; that folder is ignored by Git.

### Local wake word

The Hey JARVIS listener is opt-in. Enable it in JARVIS settings and allow the
application to download the model/runtime. The native C++ daemon is an optional
Windows-only build; see wake_native/README.md.

### Remote dashboard

Open JARVIS settings and configure the Remote panel. Pair your phone using the
private pairing code/QR displayed by the application. Do not share the pairing
code or expose the dashboard port to untrusted networks.

### Cloudflare reminder connector

The independent Worker in cloudflare/ requires your own Cloudflare account,
D1 database, Worker secrets, and deployment. Follow cloudflare/README.md.
The checked-in wrangler.toml is a template; replace the database ID with your
own. Never commit .dev.vars or production secrets.

### Alternate providers and integrations

Provider settings can use other local or hosted language models, speech
recognition, and voices. Install optional packages and provide credentials
only in the settings for the provider you choose. GitHub integration uses the
official GitHub CLI (gh) and its operating-system credential store. Other
integrations may require separate accounts, OAuth approval, or API keys.

## Tests

Run the focused first-run API and setup-gate tests:

~~~bash
python -m unittest tests.test_api_key_validation tests.test_setup_api_gate -v
~~~

Run the full test collection:

~~~bash
python -m unittest discover -s tests -v
~~~

Some integration tests require Windows, optional system tools, local services,
browser binaries, or an authenticated provider. A skipped or unavailable
integration is not evidence that the feature works on every platform.
