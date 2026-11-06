# Decisions and assumptions

A running log of design decisions, assumptions and known limitations. Newest first.

## 2026-11-06: SharePoint live (Avion SOP library)

- Connected to `sites/AM` → "Procedures and SoPs" → "1. Avion SoPs" with the Entra app
  (`Sites.Selected`, read-only grant on that one site; other sites return Access denied).
- **Approved only (user decision):** drafts, documents under review and superseded versions are never
  listed, opened, downloaded or given to the chatbot. Enforced in the connector, not just the UI.
- **SOPs + their forms (user decision):** forms/templates are linked to their SOP by numbering
  (`CO-005-A` → `CO-SOP-005`). Change controls, executed records and unnumbered files
  are hidden.
- Status combines folder (`Approved` / `Draft Unapproved` / `Superseded`) and the Document Status column;
  a document is Effective only if neither says otherwise. Assumption: Avion files approved documents in
  `Approved` folders consistently (true for all 55 SOPs found).
- Document version, Effective / Next Review dates, sign-off and change history are read from inside
  each approved SOP (cover page + "Change History" table) during indexing and stored with the index.
  Precedence: SharePoint column → document → file name. Nothing is inferred: a blank Effective Date
  stays blank (approval date shown alongside). Dates are read day-first (Australian usage).
  SharePoint's version number counts saves and is not shown (user decision).
- DocuSign stamps the Effective Date month-first on signed PDFs; ambiguous numeric dates take the
  reading closest to the sign-off date. `Complete_with_Docusign_…` files are signed copies, not
  signature pages (corrected after first assuming otherwise).
- Forms/templates are not read inside (not indexed); their version comes from the file name.
- Known gaps: Effective/Next Review dates are blank for most SOPs in SharePoint; CO-SOP-013's title is
  cut short by DocuSign and has no Word copy to restore it from.
- **Current approved SOPs only (user decision):** before each chatbot question the index is synced
  (changed files re-read, unapproved dropped) and passages are used only from SOPs in the live
  approved list whose file is unchanged since it was read. SOP pages ignore details read from an older
  copy of a file; a fresh SharePoint listing triggers a background re-read of changed files.
- **Forms/templates download as Word (user request):** the Word copy filed next to the signed PDF is
  attached to the form and served via `?format=word` (only through its approved form; not by its own
  id). SOPs stay PDF-only. Live library: 76 of 86 forms have a Word copy, 6 are filed only as Word,
  4 only as PDF (CO-014-A, DM-001-E, DM-001-F, SM-TEM-001).
- Tests never reuse a running backend (it may be live); each e2e run starts with a fresh database.

## 2026-11-06: SimpleTrials API connector (read-only)

**Access.** SimpleTrials REST API v1, enabled by an Avion SimpleTrials Administrator (Premium Plus),
**read-only**, starting with the Sandbox study only. Workspace/All Studies access needs Avion approval.
Keys live only in `.env`; they travel as URL query parameters (vendor design), so URLs are never
logged, keys are masked in all log output and kept out of errors and stored sync messages.

**Plan mirrors the CTMS.** All *Milestones & Tasks* entries are stored in SimpleTrials order (phases,
tasks, milestones). A first rule ("zero duration = milestone") wrongly dropped First Patient In (2-day
duration), so SimpleTrials' fixed milestone codes (`system_name`) also mark milestones.

**Two statuses** per entry: Progress (vs current end date) and Schedule (current vs original end;
red beyond 30 days). Completed = 100% complete, because the API has no actual completion date.
**Key milestones** (coded ones + a configurable name list) alone drive Portfolio headline figures.

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
