# Third-party notices and provenance

The MIT licence at the repository root applies only to original JARVIS
code authored by blaackwood. It does not relicense third-party content.

## Agent Skills

- 39 Skills are redistributed with the licences of their original repositories.
- Anthropic Skills with per-skill Apache-2.0 files keep those files in each Skill directory.
- Skills copied from Superpowers, REA and Vercel include the upstream repository's MIT licence in each copied Skill directory.
- Hallmark retains its own MIT licence and contributor attribution.
- Two Anthropic entries without an explicit licence at the pinned commit are reference-only; their text is not copied.
- Full source/commit mapping: SKILLS.md and skills-lock.json.

## REA workflow documentation

The supporting REA workflow documents under docs/development/ are copied
from morluto/rea at the same commit recorded in skills-lock.json and retain
that repository's MIT licence in docs/development/LICENSE.

## MediaPipe canonical face mesh

core/face_model.obj contains the MediaPipe canonical face mesh. The OBJ
header identifies the upstream source and copyright: MediaPipe Authors,
2019 to 2023. The asset is under Apache License 2.0; see
core/MEDIAPIPE-APACHE-2.0.txt.

## CryptoJS

dashboard/static/crypto-js.min.js is CryptoJS. Its MIT licence and
copyright notice are retained in dashboard/static/CRYPTOJS-LICENSE.txt.

## Stockfish

The chess integrations communicate with Stockfish through the UCI protocol.
The Stockfish binary and source are not redistributed here. tools/stockfish/
contains attribution and the GPL-3.0 licence notice for the separately
downloaded engine. Download it from https://stockfishchess.org/download/.

## Python, Node.js and operating-system dependencies

requirements.txt and _jarvis_agent_ui/desktop/package.json declare
dependencies installed by users from their package registries. They retain
their own upstream licences and notices; consult their package metadata and
official project repositories. No virtual environment, Node modules, or
compiled runtime bundle is included.

## Optional services

Google Gemini, GitHub CLI, OpenCode, Codex, Cloudflare, messaging services,
web search providers and other integrations are independent products.
Their names describe compatibility only. Their trademarks, services, API
terms, accounts and licences remain with their respective owners.
