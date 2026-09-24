# Portal architecture documentation

Scope: create top-level architecture_pic.md from current active application source.
Documentation-only work on existing codex/flood-photo-review branch; no code changes.
Diagrams cover module architecture, citizen/media/rescue flow, task states, data and
privacy boundaries, ingestion/social/edge pipelines, and local/Render deployment.
Explicitly distinguish optional providers, legacy BLIP, prototype routes and local
changes not deployed. Preserve unrelated work and newly present model directories.
Verification: inspect current source and check Markdown diagram fence structure.

## Diagram colors

User-requested documentation styling on the existing branch: added explicit pastel
fills, contrasting borders/text, and a color key to architecture_pic.md. All four
flowcharts and the task states use classes; sequence and ER diagrams use Mermaid
theme variables. Architecture labels and connections remain unchanged.
Verification: seven Mermaid blocks found, each with color styling. No Mermaid
renderer was run; application tests were not rerun for this Markdown-only edit.
