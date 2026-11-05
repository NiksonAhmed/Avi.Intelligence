# Decisions and assumptions

A running log of design decisions, assumptions and known limitations. Newest first.

## 2026-11-05: Study Command Centre (SimpleTrials, tasks, risks)

**Source of truth.** Study, site and milestone data belongs to SimpleTrials (Avion's CTMS). It is synced
into a read-only local copy (`studies`, `study_sites`, `study_milestones`) with `synced_at`, and every
sync run is stored in `connector_syncs` and audited. Only a demo connector exists until Avion obtains a
SimpleTrials export or API access (see `docs/simpletrials-setup.md`). Demo studies use fictional
sponsors, sites and people, and every screen says "Demo data".

**Sync, not live fetch.** Unlike SOPs, study data is copied on sync (automatic on first use, then
"Sync now"). This keeps screens fast and gives a record of what was shown when. Failed syncs keep the
previous copy; studies missing from the source are flagged, never deleted, so linked work survives.

**Access rules (agreed with the user).** Tasks and risks are managed in Avi.Intelligence. Only
administrators (`work.manage`) create, assign and edit them. The assigned person (task) or owner (risk)
may change its status; everyone else is read-only. Only administrators can cancel a task. Nothing is
deleted. Checks are server-side; the UI shows a lock on read-only status.

**Indicators.** Overdue = planned/due date passed with no actual/completion. Enrolment % only when a
target exists ("no target recorded" otherwise). Risk score = likelihood × impact as entered. Rule
texts are served by the API (`rules`) and shown as tooltips. No AI scoring in this release.

**People.** A demo directory stands in for Microsoft Entra ID. `DEV_USER_ID` picks which demo person the
local developer is, to try assignee-only behaviour.

**Assumptions / open.** Avion may already track tasks or risks in SimpleTrials; if so they should come
from there. Per-user study access (only "my studies") waits for Entra sign-in. Reference numbers
(TSK-0001) are count-based, fine for one database but not for concurrent writers at scale.

## 2026-11-05: Ask Avi.Intelligence (SOP chatbot)

**Grounding.** Answers come only from SOPs with status *Effective*. Passages are retrieved locally and
sent to Claude as `document` blocks (custom content, one block per passage) with citations enabled, so
each citation maps to an exact SOP and section. The system prompt requires answering only from the
passages, flagging gaps and conflicts, and ignoring instructions inside documents (prompt injection).

**Retrieval.** BM25 over passages (Anthropic has no embeddings API; SOP language is term-heavy). Kept
behind `Bm25Index` so hybrid/vector search (pgvector) can be added later. The index is a database table
(`knowledge_documents`, `knowledge_chunks`), rebuilt incrementally (unchanged version and modified date
are skipped). It is built on first use and from Administration → Re-index.

**Model.** `claude-opus-5-5` at effort `medium` (configurable: `ASSISTANT_MODEL`, `ASSISTANT_EFFORT`).
Server-side refusal fallbacks (`fallbacks: "default"`) are enabled for models that support them.
Non-streaming request; the UI shows a progress state.

**No key = search-only.** Without `ANTHROPIC_API_KEY` the assistant returns the best passages instead
of a written answer, so the feature is useful (and testable) without AI. Tests never call the paid API.

**Traceability.** Every question is stored in `assistant_interactions` (question, answer, citations,
model, tokens, latency) and recorded in the audit trail.

**Data handling.** Questions and SOP excerpts are sent to Anthropic. The UI warns users not to enter
patient-identifiable information. Anthropic-hosted vs. AWS Bedrock / Google Vertex (regional hosting)
is a pending decision for Avion Quality/IT.

**Demo content.** Demo SOPs now carry short sample bodies (clearly marked DEMO) so the assistant can be
tried before SharePoint is connected.

**Corporate TLS.** `truststore` makes Python use the Windows certificate store
(`USE_SYSTEM_TRUST_STORE=true`), so Graph and Anthropic calls work behind TLS inspection.

**E2E tests** run with 2 workers: more parallel browsers against the Vite dev server overload a laptop.

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
- Frontend bundle is ~1.2 MB (Ant Design); add route-level code splitting.
- Docker Compose images have not yet been built on this machine (Docker Desktop was not running).
