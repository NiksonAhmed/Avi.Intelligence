# Decisions and assumptions

A running log of design decisions, assumptions and known limitations. Newest first.

## 2026-11-05: First slice, SharePoint SOPs

**Scope.** First working feature: *Documents and Knowledge → SOPs*, read from SharePoint, plus the app
shell, role checks, audit trail and admin connector diagnostics. Other sections show honest
"not available yet" pages.

**Stack** (per the product brief, for an empty repository): React + strict TypeScript + Vite + Ant Design +
React Router + TanStack Query; FastAPI + Pydantic + SQLAlchemy + Alembic; SQLite for local demo,
PostgreSQL via Docker Compose. Python dependencies are locked with `uv` (`uv.lock`), Node with
`package-lock.json`.

**SharePoint access.** App-only Microsoft Graph with `Sites.Selected` (least privilege: only granted sites).
No Graph SDK: a small `httpx` client with token caching, retry on 429/503/504 honouring `Retry-After`,
pagination, and SSRF guards (only `graph.microsoft.com` is called with the token; downloads stream from
the pre-authenticated SharePoint URL *without* the token).

**SOP scope enforcement.** The API only serves documents that appear in the configured library/folder
listing. A request for any other drive item id returns 404, even if the app could technically read it.

**Caching.** The SOP list is cached in memory for `SHAREPOINT_CACHE_MINUTES` (default 5). Users can force a
refresh. Indexing documents into the database (for AI search) comes with the AI assistant.

**Status rules.** Status column → content approval → version number → Unknown. The source is shown to
users (`statusSource`) so inferred values are never presented as fact.

**Demo mode.** Without credentials the app runs on clearly labelled demo SOPs (owners are role titles,
not people). Demo downloads are plain-text placeholders marked "DEMO DOCUMENT".

**Authentication.** Not implemented yet. In development every request runs as a local user whose role
is set by `DEV_USER_ROLE`. With `APP_ENV=production` the API refuses all requests (401) until Microsoft
Entra ID sign-in is added. **Do not deploy beyond a developer machine before sign-in exists.**

**Roles.** admin, project_manager, cra, data_manager, safety, viewer. Permissions: `sop.read`,
`sop.download` (all staff except viewer), `audit.read` (admin, project manager), `connector.manage`
(admin). Enforced server-side; the UI only hides what the server would refuse.

**Audit trail.** Append-only `audit_events` table (no update/delete endpoints). Records SOP downloads
and connector tests with user, role, time, IP and details. Every row carries `tenant_id` so the product
can later serve other CROs.

**Provenance.** UI convention: *Source record* (from a system), *AI suggestion* (must be verified),
*Approved decision* (named approver). See `frontend/src/components/ProvenanceTag.tsx`.

**No fabricated metrics.** Summary numbers are computed from real records only; the notification centre
is empty until a notification source exists.

**Time zone.** Dates display in `Australia/Sydney` (configurable) because SharePoint stores date-only
columns as UTC instants.

### Known limitations / next steps
- Microsoft Entra ID sign-in and Entra group → role mapping.
- Templates and study documents tabs (same connector, different libraries).
- AI assistant over *Effective* SOPs with citations.
- Frontend bundle is ~1.2 MB (Ant Design); add route-level code splitting.
- Docker Compose images have not yet been built on this machine (Docker Desktop was not running).
