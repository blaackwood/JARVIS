# JARVIS installation guide

## Windows installer (recommended)

The supported one-click installer is for **Windows 10/11 x64**.

1. Download JARVIS-Setup.exe from [GitHub Releases](https://github.com/blaackwood/JARVIS/releases/latest).
2. Run it. Installation is per-user and does not require administrator privileges.
3. Launch JARVIS from the Start Menu shortcut.
4. On first launch, enter your own Gemini API key and validate it.

The installer bundles the Python runtime and application dependencies. Python
and Git are not required on the target computer. It does not turn on wake-word
listening or register a Windows auto-start entry; both remain optional settings
controlled from the app.

The installer is not code-signed yet. Windows SmartScreen may show an
unrecognized-app warning. Only obtain it from the official GitHub Releases
page linked above.

## Requirements and hardware

- Windows 10/11, 64-bit, for the packaged installer.
- Internet access for Gemini Live, web services and browser automation.
- A microphone and speakers/headphones for voice conversation.
- A dedicated GPU is not required for the basic software-rendered holographic
  avatar. Advanced 3D experiences depend on the graphics hardware and drivers.
- A tested minimum RAM requirement has not yet been established.
- The installer bundles Chromium Headless Shell for local browser QA.
  Interactive browser control launches your own installed Chrome, Edge or
  Firefox; browser profiles are not copied into the installer.

macOS/Linux users can install from source; the packaged installer is Windows
only.

## First-run API configuration

JARVIS requires the user's own Gemini API key. Create one in
[Google AI Studio](https://aistudio.google.com/apikey), start the app, paste
the key into the setup field and validate it. The first-run gate does not
accept a blank key. Selecting an alternate/local provider later does not
erase the key required for initial provisioning.

The key is written to config/api_keys.json. The file is excluded by Git,
but this implementation stores it in plain text. Protect your operating
system account and never share or commit that file.

## Install from source

### Windows PowerShell

~~~powershell
git clone https://github.com/blaackwood/JARVIS.git
cd JARVIS
py -3.13 -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
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
.\\.venv\\Scripts\\python.exe _jarvis_agent_ui\\server.py
~~~

For the Electron wrapper, install Node.js, then run:

~~~powershell
cd _jarvis_agent_ui\\desktop
npm install
npm start
~~~

Set JARVIS_ROOT if the Electron wrapper is launched from a location where it
cannot infer the repository root. User task history and approvals are created
locally under _jarvis_agent_ui/data/; that folder is ignored by Git.

### Local wake word

The Hey JARVIS listener is opt-in. Enable it in JARVIS settings and allow the
application to download the model/runtime. The optional wake daemon is built
for Windows; see wake_native/README.md for the native alternative.

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

## Built-in browser QA

The JARVIS Agent workbench uses the browser QA utility bundled with this
repository. It relies on the included core/browser_qa.py service and does
not require the unlicensed local Skill from the original developer machine.

Check Playwright and Chromium:

~~~powershell
python tools/jarvis_browser_qa.py --check
~~~

Run browser QA against a web project:

~~~powershell
python tools/jarvis_browser_qa.py --project-dir C:\\path\\to\\your\\web-project
~~~

The runner only starts recognized local development servers on 127.0.0.1,
captures desktop/mobile screenshots, reports console/network/HTTP errors,
and stores evidence locally outside the repository. It does not install
packages or browsers automatically. The project must already have its
dependencies installed and a supported web entry point.

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
