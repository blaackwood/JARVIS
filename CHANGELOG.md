# Changelog

All notable changes to JARVIS are documented here.

## [0.2.0] - 2026-11-23

### Added
- Persistent application language selection: English (US) by default, with Brazilian Portuguese available in Identity settings.
- Consistent localization for HUD modules, status states and keyboard shortcuts.
- Documentation for low-overhead background operation and the optional native Windows wake-word companion.

### Performance notes
- A Windows Task Manager snapshot recorded the native JarvisWakeNative.exe listener at 0.8% CPU and 21.4 MB RAM. This is a point-in-time measurement of that process, not a whole-app benchmark or a guarantee across hardware and workloads.

## [0.1.0] — 2026-11-23

First public Windows installer release.

### Added
- Windows 10/11 x64 per-user installer with Start Menu shortcut.
- Bundled Python 3.13 runtime and application dependencies; Python and Git are not required on the target PC.
- Dedicated JARVIS desktop executable, optional wake-word worker and background task worker.
- Playwright Chromium Headless Shell for local browser QA, with upstream licensing notices retained.
- Brazilian Portuguese and English installation and feature documentation.
- SHA-256 checksum for the Windows installer.

### Privacy and security
- The installer does not enable wake-word listening or register Windows auto-start.
- Users can opt in to those settings from the application.
- No developer API key, personal memory, conversation history, or private local configuration is shipped.
- Each user supplies their own Gemini API key. This release stores it locally in `config/api_keys.json` in plain text; protect the Windows account and never share that file.
- The installer is not code-signed; Windows SmartScreen may display an unrecognized-app warning.

### Requirements and optional integrations
- Windows 10/11, 64-bit; internet access and a user-owned Gemini API key for live voice.
- Microphone and speakers/headphones for voice features.
- Interactive browser control uses Chrome, Edge or Firefox already installed by the user. The bundled Headless Shell is for browser QA.
- Stockfish, OpenCode/Codex, Cloudflare, remote pairing, alternate providers and the separate Electron JARVIS Agent shell require separate setup and/or accounts.
- macOS/Linux users should use the manual source installation documented in INSTALLATION.md.

### Licensing
- Original JARVIS source code is MIT-licensed by blaackwood.
- Third-party Skills, packages, runtimes, Chromium components and assets retain their own upstream licences and notices. See THIRD_PARTY_NOTICES.md and SKILLS.md.
