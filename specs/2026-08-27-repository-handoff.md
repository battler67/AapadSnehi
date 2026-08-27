# Repository handoff and publication

Date: 2026-08-27

## Scope

Publish a safe, reproducible snapshot of the full AapadSnehi workspace to
https://github.com/battler67/AapadSnehi.git on main, so it can be cloned and
continued on another computer.

## Included

- The complete active aapad-snehi/ source tree, tests, docs, and feature specs.
- The legacy blip-caption-api/ source.
- A sanitized, output-cleared Bluesky experiment notebook.
- Workspace README, curated project context, agent instructions, and this handoff
  record.

## Excluded

- Nested .git metadata and private Codex/session memory.
- .env files, credentials, local databases/uploads, dependencies, caches,
  screenshots, logs, and build output.

## Credential remediation

The Bluesky email and app password found in shareable configuration/notebook
material were replaced with placeholders/environment lookups before staging. The
previous app password must be rotated at the provider because it was stored in
plaintext locally.

## Repository approach

The outer repository is the canonical portable repository. Nested repositories are
flattened into ordinary directories for a one-command clone while their local Git
metadata is preserved outside the staged snapshot.

## Verification

Completed before publication:

- Backend: 202 tests passed.
- Frontend: 11 tests passed across 5 files.
- TypeScript/Vite production build passed.
- Staged comparison against sensitive values in the ignored local .env found no
  matches.
- No .env, nested .git, dependency, build, coverage, artifact, or database path is
  staged.

Pending until publication:

- Remote branch and commit verification after push.
