# Avi.Intelligence

**Smarter clinical trial operations.** An AI-assisted CRO operations platform for Avion Medical,
designed to become a configurable product for other Contract Research Organisations.

> **Status: early development.** Implemented so far: the app shell, *Documents and Knowledge → SOPs*
> (read from SharePoint), the Study Command Centre (SimpleTrials demo data), tasks, risks and issues,
> role-based access, an audit trail and connector diagnostics.
> Sign-in (Microsoft Entra ID) is **not** implemented yet, so run it on a developer machine only.

## What works today

| Area | Details |
|---|---|
| SOP library | Lists SOPs from a SharePoint library/folder with number, version, status, effective and review dates, owner, department. Search, filter, detail page, version history, download, open in SharePoint. |
| Status honesty | Status shows where it came from (status column, content approval, or inferred from version). Demo data is labelled everywhere. |
| Roles | admin, project_manager, cra, data_manager, safety, viewer, enforced in the API. |
| Audit trail | Append-only record of SOP downloads and connector tests. |
| Administration | SharePoint connection test, library columns and field mapping, AI index status and re-index. |
| Study Portfolio and Command Centre | Studies, sites, milestones and enrolment from SimpleTrials (**demo data** until SimpleTrials is connected; see [docs/simpletrials-setup.md](docs/simpletrials-setup.md)). One workspace per study with milestones, sites, tasks and risks. Overdue and enrolment indicators follow stated rules; nothing is estimated. |
| My Tasks, Risks and Issues | Administrators create and assign tasks and risks; only the assigned person (or risk owner) can change the status; everyone else is read-only. Every change is audited. |
| Ask Avi.Intelligence | Chatbot (Documents and Knowledge → Ask, or the header button) that answers from **effective SOPs only**, with numbered citations to SOP and section, labelled as an AI suggestion. Without an API key it shows the most relevant SOP passages instead. Every question is logged. |

Roadmap: SimpleTrials export import, then API → Entra ID sign-in → templates and study documents →
Avie Safety database, Viedoc, Rave and email connectors.

### AI assistant set-up

1. Create an API key at [console.anthropic.com](https://console.anthropic.com) and add it to `.env` as
   `ANTHROPIC_API_KEY` (never commit it or paste it into chat).
2. Restart the backend. Administration → Connectors shows "AI answers on".
3. Ask a question. The SOP index is built automatically on first use; use **Re-index SOPs now** after
   SOPs are published or superseded.

How it works: SOP files (.docx, text-based .pdf, .txt) are split into sections and indexed (BM25 search).
For each question the best-matching passages from up to 5 effective SOPs are sent to Claude
(`claude-opus-5-5` by default) as citable documents; Claude must answer only from them and say when they
don't cover the question. Draft, in-review and superseded SOPs are never indexed. Question text and SOP
excerpts leave your network and are processed by Anthropic, so confirm this with Quality/IT before
using real SOPs.

## Repository layout

```
backend/    FastAPI, SQLAlchemy, Alembic, pytest      (Python 3.12, uv)
frontend/   React, TypeScript, Vite, Ant Design        (Node 24, npm)
docs/       sharepoint-setup.md, simpletrials-setup.md, decisions.md
docker-compose.yml   PostgreSQL + API + web app
```

## Prerequisites

- **Python 3.12** and **[uv](https://docs.astral.sh/uv/)**
- **Node.js 24 LTS** (22.22+ works). With nvm for Windows: `nvm install 24; nvm use 24`
- Optional: Docker Desktop (for the PostgreSQL / Compose setup)

## Run locally (SQLite, demo or live SharePoint)

```powershell
# 1. Configuration
Copy-Item .env.example .env          # then edit .env (SharePoint values optional)

# 2. Backend: http://127.0.0.1:8000  (API docs at /api/docs)
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 3. Frontend (second terminal): http://127.0.0.1:5173
cd frontend
npm ci
npm run dev
```

Without SharePoint credentials the app runs on **labelled demo SOPs**. To connect to Avion SharePoint,
follow [docs/sharepoint-setup.md](docs/sharepoint-setup.md) and check with
`uv run python -m app.check_sharepoint`.

To see the app as another role, set `DEV_USER_ROLE` in `.env` (e.g. `viewer`) and restart the backend.

## Run with Docker Compose (PostgreSQL)

```powershell
Copy-Item .env.example .env
docker compose up --build            # http://localhost:8080
```

## Tests and checks

```powershell
cd backend
uv run pytest                        # unit + API tests (simulated Microsoft Graph, no network)
uv run ruff check src tests alembic
uv run mypy                          # strict

cd frontend
npm run lint; npm run typecheck; npm test; npm run build
npx playwright install chromium      # once
npm run e2e                          # starts backend (demo mode) + frontend, desktop and tablet
```

CI runs all of the above on every push and pull request (`.github/workflows/ci.yml`).

## Configuration

All configuration is via environment variables; see [.env.example](.env.example). Secrets live in `.env`
locally (git-ignored) and in a secret store (e.g. Azure Key Vault) in production.

| Environment | `APP_ENV` | Database | Notes |
|---|---|---|---|
| Development | `development` | SQLite file | Development user from `DEV_USER_ROLE` |
| Test | `test` | in-memory / throwaway SQLite | Used by pytest and Playwright |
| Production | `production` | PostgreSQL | API docs disabled; requests refused until sign-in exists |

## Corporate network / TLS inspection

If `uv` fails with `invalid peer certificate: UnknownIssuer`, your network inspects TLS. Use the
Windows certificate store: `uv sync --system-certs` (or set `UV_SYSTEM_CERTS=1`).

## Security notes

- SharePoint access is read-only via `Sites.Selected` (only explicitly granted sites).
- The API only serves documents inside the configured SOP library/folder.
- Access tokens are never sent to download hosts. Downloads stream through the API and are audited.
- Security headers on all responses. The dev servers bind to `127.0.0.1` only.
- See [docs/decisions.md](docs/decisions.md) for assumptions and known limitations.
