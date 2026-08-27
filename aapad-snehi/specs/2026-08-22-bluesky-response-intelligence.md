# Bluesky helper-search implementation record

Date: 2026-08-22
Approval received: `APPROVE PLAN`
Branch: `feature/bluesky-response-intelligence`

## Approved scope correction

After approving the original broader plan, the user explicitly narrowed the feature:

- follow the authenticated `atproto.Client` login and `search_posts` flow demonstrated in `bluesky_test.ipynb`;
- do not use Hugging Face, Transformers, or another model;
- keep intent detection simple and transparent;
- add a dedicated portal page that runs the adapter and displays matching public author IDs.

This correction supersedes the earlier model-selection, helper-persistence, retention, and review-queue design.

## Implemented design

```text
Demo visitor clicks Run Bluesky scan
             |
             v
POST /api/bluesky/scan
             |
             v
atproto.Client login + bounded search_posts
             |
             v
disaster keyword + explicit help-offer keyword rule
             |
             v
unique public author DIDs/handles rendered on /bluesky-helpers
```

- Credentials are backend-only environment values: `AAPAD_BLUESKY_EMAIL` and `AAPAD_BLUESKY_APP_PASSWORD`.
- The adapter does not read the notebook at runtime or copy its plaintext credential into source.
- One configurable query is used, with a default limit of 10 and a hard bound of 50.
- Request-only, negated, generic-positive, and non-disaster posts are excluded.
- Authors are deduplicated by DID.
- Results are returned in memory and are not stored in a helper/person database.
- The quick-demo endpoint and page require no portal account, login, role, token, or sign-in step.
- No post, like, follow, reply, message, volunteer registration, or assignment action exists.
- Bluesky-derived incident candidates, when run through the general pipeline, remain `social` and `unverified` and still require usable India location evidence.

## Files and behavior

- `backend/app/adapters/bluesky.py`: authenticated read-only adapter, result parsing, DID deduplication, safe post links, and incident conversion.
- `backend/app/services/social_intent.py`: deterministic help-offer, request/negation, and capability patterns.
- `backend/app/main.py`: token-free `POST /api/bluesky/scan` demo endpoint with live-adapter and provider-configuration gates.
- `backend/app/config.py` and `.env.example`: bounded query/result configuration and blank credential fields.
- `web/src/pages/BlueskyHelpersPage.tsx`: query input, run action, aggregate counts, author IDs/handles, evidence excerpt, matched terms, and public-post links.
- `web/src/routes.ts`, `web/src/App.tsx`, and `web/src/components/Shell.tsx`: dedicated `/bluesky-helpers` route and navigation entry.
- `docs/bluesky-helper-adapter.md`: setup, behavior, privacy boundary, and verification commands.

## Credential boundary

The notebook contains a credential-bearing login cell. The implementation deliberately does not print, commit, or automatically migrate that value. The account owner should rotate it and place a new Bluesky app password in the ignored local `.env` before running a live scan.

## Verification record

- Focused backend intent, adapter, and scan-endpoint tests: 7 passed.
- Frontend unit tests: 5 files, 10 tests passed.
- TypeScript check and Vite production build: passed.
- Full backend regression after the quick-demo update: 201 tests passed.
- Diff whitespace check, source credential scan, and Python compile check: passed.
- Installed and inspected `atproto==0.0.69`; its `login` and `search_posts` call signatures match the notebook flow.
- Live account smoke: passed after configuring the ignored local `.env`; 10 public posts were scanned and the provider source reported `healthy`. No credential was printed, committed, or sent to the browser.

## Quick-demo scope update

At the user's request, the portal authentication layer was removed after the initial implementation:

- removed login, signup, session restoration, role switching, and sign-out UI;
- removed auth API routes, bearer-token handling, JWT configuration/dependency, seeded accounts, and backend role dependencies;
- kept live-provider gates, Bluesky server-side credentials, explicit assignment confirmation, duplicate protection, and human-review warnings.
