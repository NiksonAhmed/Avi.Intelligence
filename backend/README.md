# Avi.Intelligence API

FastAPI backend. See the repository [README](../README.md) for setup.

```
src/app/
  main.py                    app factory, middleware (request id, security headers, JSON logs)
  core/                      settings (pydantic-settings), structured logging
  auth/rbac.py               roles, permissions, current user (development stub until Entra ID)
  audit/                     append-only audit trail model + service
  db/session.py              SQLAlchemy engine/session
  api/sops.py                /api/v1/sops ...
  api/admin.py               /api/v1/me, /connectors/sharepoint, /audit-events
  connectors/sharepoint/     Graph client, live + demo connectors, pure mapping logic
  check_sharepoint.py        CLI: uv run python -m app.check_sharepoint
alembic/                     database migrations
tests/                       pytest (simulated Microsoft Graph; no network needed)
```

```powershell
uv sync                      # add --system-certs behind a TLS-inspecting proxy
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
uv run pytest; uv run ruff check src tests alembic; uv run mypy
```

API docs (development only): http://127.0.0.1:8000/api/docs
