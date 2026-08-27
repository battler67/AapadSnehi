# AapadSnehi workspace

This repository is the complete, shareable AapadSnehi development workspace. The
primary application is in [aapad-snehi/](aapad-snehi/README.md): a React/Vite
frontend and FastAPI/SQLite backend for disaster-signal review, citizen reports,
volunteer coordination, and administrator-assisted allocation.

The default experience is deterministic and credential-free. Seeded incidents and
volunteers are labelled as demonstration data, and external social/news signals
remain unverified unless their source has an explicit official provenance.

## Repository layout

- aapad-snehi/ — active application, tests, architecture notes, and feature specs.
- blip-caption-api/ — legacy Hugging Face/Gradio captioning experiment; retained
  for reproducibility and not called by the active application.
- bluesky_test.ipynb — sanitized historical Bluesky experiment. It reads
  credentials from environment variables and is not part of the production path.
- PROJECT_CONTEXT.md — concise handoff context and non-negotiable product
  boundaries for future development.
- AGENTS.md — repository instructions for coding agents and contributors.
- specs/ — workspace-level implementation and handoff records.

Nested Git metadata, local credentials, databases, uploads, dependencies, caches,
and build output are intentionally excluded. The repository is a flattened
workspace snapshot so a normal clone contains all source code.

## Clone and run on another Windows computer

Requirements: Git, Node.js 22+, npm 11+, and Python 3.11+.

~~~powershell
git clone https://github.com/battler67/AapadSnehi.git
cd AapadSnehi\aapad-snehi
Copy-Item .env.example .env
~~~

The copied .env contains safe placeholders. No provider credential is required
for the seeded demo.

Start the API:

~~~powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
~~~

In a second terminal, start the frontend:

~~~powershell
cd AapadSnehi\aapad-snehi\web
npm ci
npm run dev
~~~

- Application: http://localhost:5173
- API health: http://localhost:8000/health
- API documentation: http://localhost:8000/docs

For live providers, architecture details, limitations, and all test commands, read
the [application README](aapad-snehi/README.md).

## Quick verification

~~~powershell
cd aapad-snehi\backend
python -m pytest

cd ..\web
npm test
npm run build
~~~

Never commit .env or paste provider credentials into notebooks, source, specs, or
issue logs.
