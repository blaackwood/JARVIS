# Security and privacy

## API keys and local configuration

- Each installation must use its owner's Gemini API key.
- The setup screen validates the key with Google before saving it.
- The current config manager stores the key in plain text in
  config/api_keys.json. Protect the OS account and local disk.
- config/api_keys.json*, provider secrets, .env files, Cloudflare .dev.vars,
  and local key files are ignored by Git.
- Never attach local config, logs, task-state folders, screenshots or memory
  archives to issues or pull requests.

## Data sent to external services

JARVIS is local-first, not offline-only.

- Live voice conversations use Google Gemini Live. Audio and conversation
  content are sent to Google's service for model processing.
- The file processor is scoped to the file selected/dropped by the user;
  that file's content is sent to the configured Gemini model for analysis.
- Alternate AI providers, web services, messaging integrations and optional
  cloud connectors receive the data needed for the operation the user requests.
- Screen/camera analysis may send relevant captured content to the active AI
  provider when the user invokes those features.

Do not send confidential files or private screen content to a provider unless
you are comfortable with that provider's terms and data handling.

## Desktop permissions and actions

The assistant can interact with the local desktop, browser, files and system.
Use authorization settings and confirmation prompts. Review destructive
operations before approving them. Do not run JARVIS with elevated privileges
unless a specific feature genuinely requires it.

## Reporting a vulnerability

Do not publish credentials, exploit details, private logs or personal data in
a public issue. Report suspected vulnerabilities privately to the repository
maintainer through GitHub's security reporting workflow.
