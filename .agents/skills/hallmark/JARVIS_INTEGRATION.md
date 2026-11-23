# JARVIS integration notes

Upstream: https://github.com/nutlope/hallmark
Version: 2.0.0
Pinned commit: 04977e1
License: MIT

JARVIS invokes this skill on web tasks alongside jarvis-web-workflow, frontend-design, and webapp-testing. The JARVIS workflow is the harness adapter:

- Infer the Hallmark intake from the current request and conversation; do not repeat the four-question interview when context is sufficient.
- Use local theme selection/draw/scaffold and sloplint --render on new pages and major design work.
- No photo-library downloads, Wikimedia fetches, Together comps, or other external requests unless the user explicitly approves.
- User requirements, project facts, existing design systems, accessibility, and behavior take precedence over generic style gates. Record justified deviations honestly.
- SVG/CSS diagrams, maps, data visualizations, and requested illustrations are valid when they serve the product; do not use them as generic filler.
- For app/dashboard scope use --scope app; for small fixes preserve the existing system; use the redesign branch only when requested.
- sloplint supplements but does not replace Playwright and human visual inspection. Never fabricate a clean result.

Upstream SKILL.md, references, scripts, agent prompts, and MIT license remain unmodified.
