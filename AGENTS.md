# Repository instructions

## Scope

The active product is aapad-snehi/. Treat blip-caption-api/ and
bluesky_test.ipynb as historical experiments unless a task explicitly targets
them.

## Workflow

- Inspect the active branch, status, remotes, and relevant docs before editing.
- For features or major modifications, create a dedicated branch and record the
  plan, scope, major edits, and verification in top-level specs/.
- Preserve unrelated user changes and keep commits scoped.
- Use rg and rg --files for repository search.

## Product and safety invariants

- Keep deterministic demo mode as the no-credential default.
- Never label seeded, fallback, social, or ordinary news data as live official
  warnings.
- Preserve provenance labels and human confirmation for review and dispatch.
- Keep provider credentials backend-only in ignored .env files. Examples and
  notebooks must use placeholders or environment variables.
- Do not claim authentication/RBAC for the current public prototype routes.
- Do not claim live-provider behavior until the environment gate, provider
  configuration, request flag, and runtime response are all verified.

## Verification

From aapad-snehi/backend, run python -m pytest.

From aapad-snehi/web, run npm test and npm run build.

Check the running API at /health and /docs; the backend root may intentionally
not be the application page.
