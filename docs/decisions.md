# Decisions and assumptions

A running log of design decisions, assumptions and known limitations. Newest first.

## 2026-11-11: Data Management (Viedoc) as a self-contained module (agreed before any code)

- User decision: build Data Management **inside Avi.Intelligence**, not as separate software, but keep its
  code self-contained so it could be split out later. Workflow plan: Viedoc sandbox → read-only connector
  → checks → Data Management tab → per-site Excel for CRAs → sites answer in Viedoc → next sync picks up
  the answers (map: https://claude.ai/artifact/KTaxiayBgygwhSbsgCLf4w).
- **Module boundary:**
  - Backend code lives in `app/data_management/`, with the connector in `app/connectors/viedoc/`.
  - **One-way dependency:** the module may use the shared foundations (auth and roles, audit, database
    session, the study list), but nothing outside it imports from it. An automated test enforces this.
  - Its own tables with a `dm_` prefix, linked to studies by study id only, so they could move to a
    separate database.
  - Its own API section (`/api/v1/data-management/...`) and permissions (`dm.view`, `dm.approve`,
    `dm.export`), granted to existing roles.
  - Frontend in `src/modules/data-management/` (own pages, hooks and types), reached by one menu entry.
  - An on/off setting, `DATA_MANAGEMENT_ENABLED`, defaulting to off until the module is ready.
- **Ground rules:** read-only towards Viedoc (nothing is written back; sites answer in Viedoc itself);
  tests never call the real Viedoc API; credentials only in `.env`.
- **One API client per study (user's understanding; Step 0 confirms).** Viedoc API access is expected to be
  set up per study, possibly also per environment (test and production). Avi.Intelligence therefore holds a
  **list of Viedoc connections**, each with a name, a sandbox or live label, API address, client ID and
  secret. Secrets stay in `.env`; a settings screen shows the connections, never the secrets. Adding a
  study means adding one connection entry, with no code change. If one client turns out to cover several
  studies, every study it can see is listed.
- **Sandbox first, live later.** Every study and record keeps its sandbox or live label, shown clearly on
  screen (as the SimpleTrials Sandbox is today). Sandbox and live data are never mixed in views, Reports or
  exports. **Live connections are not read** unless `VIEDOC_ALLOW_LIVE=true` (off by default), which is only
  turned on after Avion's data-protection and Quality sign-off, so a live key added by mistake reads
  nothing. The same rules apply to live data: read-only, subject IDs only, no EDC data sent to AI.
- **Exception to the "no patient-level data" rule:** EDC queries are subject-level by nature, so this
  module may store **subject IDs and query metadata only**: no names, initials, dates of birth or free
  text that could identify a patient. **No EDC data is ever sent to an AI model.** Pending Quality
  sign-off.
- **Validation (GxP):** if the module is used to manage data queries in regulated studies, Quality may
  require computerised system validation. The boundary above lets the module be validated on its own;
  to be confirmed with Quality early.
- **Labels:** every item in the tab is labelled RECORD (from Viedoc), RULE FINDING (our check) or, later,
  AI SUGGESTION (needs a human), so a check result is never mistaken for an EDC record. Every number links
  back to the Viedoc records behind it.
- **Query stages tracked:** Raised (edit check, DM or CRA) → Open at site (the site's clock) → Resolved by
  site, waiting on approval (our clock) → Approved / Closed. A rejected answer goes back to Open at site and
  counts as a re-open. Both clocks are reported. (In the sample export every row was waiting on approval.)
- **Views:** Overview, Queries, Missing data, Labs, Deviations, Check quality (edit checks that fire often
  and are always answered the same way, e.g. QRS → "NCS") and Site export. AI suggestions come later.
- **Proposed access** (existing roles; nobody can change Viedoc data from here):

  | Role | Data Management tab | Scope | Task / risk from a finding | Site Excel |
  |---|---|---|---|---|
  | Admin | Yes | All studies | Yes | Yes |
  | Data Manager | Yes | Assigned studies | Yes | Yes |
  | Project Manager | Yes | Their studies | Study tasks only | Yes |
  | CRA | Yes | Their sites only | Own tasks only | Their sites |
  | QA | Read-only | All studies | Risks only | No |
  | CTA, Pharmacovigilance | No | — | — | — |

  "Assigned studies" and "their sites" need study/site assignments, which Avi.Intelligence does not hold
  yet (they arrive with Entra sign-in or a simple assignment list).

### Build steps

Each step is shown before it is committed, and pushed only when agreed. Work happens on
`feature/data-management`.

| Step | Delivers | Done when |
|---|---|---|
| **0. Sandbox API discovery** | The user creates a sandbox API client in Viedoc API Manager and puts its client ID, secret and API address in `.env`. A read-only probe script lists what comes back (queries with history, clinical data, visit schedule, lab ranges, deviation flags), recording field names, IDs and limits, and confirms how a client is scoped (one study or several, one environment or several). | We know which views the API can feed and how clients map to studies, and the user has reviewed the findings. No screens before this. |
| **1. Connector and Queries view** | `dm_` tables and migration; read-only hourly sync (connector in `app/connectors/viedoc/`); Overview and Queries views with ageing (0–7, 8–14, 15–30, 30+ days). | Sandbox query counts match Viedoc. |
| **2. Site Excel export** | A per-site file for CRAs listing only actionable items (subject, visit, form, field, query text, days open; items waiting on our approval left out), with role and site filtering. | A CRA sees only their sites. |
| **3. Missing data and Labs** | Expected forms not started or not submitted, overdue visits; out-of-range lab values, missing units or ranges, a field missing across many subjects (vendor issue). | Checked against known gaps in the sandbox. |
| **4. Deviations and rules** | Viedoc deviation flags plus rule-based candidates (visit windows, ECG not done); per-study rule settings; turning a finding into a Task or a Risk under the existing rules. | Findings link to tasks and risks correctly. |
| **5. Reports and tests** | A Data Management section in Reports and Insights; daily snapshots and trends; full tests and docs. | Full test suites pass; docs updated. |

### Decisions needed before Step 1

1. Who approves site answers in Viedoc: DM, CRA or both? This decides who owns the waiting-on-approval
   backlog.
2. Ageing targets: for example, sites answer within 5 working days and we approve within 3 (drives the
   red/amber flags).
3. Source of truth for protocol deviations: Viedoc, SimpleTrials or both (if both, match them)?
4. Site Excel columns: confirm subject, visit, form, field, query text, raised date, days open. Should
   missing forms be included too?
5. Which sandbox study, and confirmation that it holds only test data. Production studies come later,
   after Avion's data-protection sign-off.
6. Sync frequency: hourly like SimpleTrials, or more often around database lock?

### Step 0 findings (Viedoc sandbox, 11 Nov 2026)

- Sign-in: OAuth 2.0 client credentials against Viedoc's sign-in server, which sits on its own host next
  to the API (`v4apitraining` → `v4ststraining`); the tool finds it from the API address. The client
  first failed with `invalid_client` until it was saved with valid scopes. Granted scopes:
  `viedoc.api.admin.sites.read` and `viedoc.api.clinic.export`.
- API version 2022-01-01 (Swagger at `/swagger/index.html`): no direct query or form endpoints. Clinical
  data and queries come only as an **export**: start → status → download → delete.
- **Rule change (agreed):** "only GET" became "never change study data". Exactly two other calls are
  allowed, both on our own export copy: starting an export and deleting that export file afterwards.
  Every other write endpoint (sites, users, ePRO accounts) is refused in code.
- The export (CSV, zip) holds one file per form plus `Queries.csv` (with history, edit check ID, type,
  state, resolution, role and user), `Pending_forms.csv`, `Items.csv` and `CodeLists.csv`. Each CSV has
  a second header row of column IDs. Query states: Query Raised → Query Resolved → Query Closed. Query
  types: Validation, Unconfirmed missing data, Pending form upgrade. No protocol deviation file in this
  study.

### Step 1 (built, shown before committing)

- Defaults agreed to start: query text and staff names kept (sandbox test data; to be decided again
  before any live study); site answers shown with the role that acted; targets 5 working days (site)
  and 3 (approval), both settings (`DM_SITE_ANSWER_DAYS`, `DM_APPROVAL_DAYS`).
- Sync (hourly, `DATA_MANAGEMENT_SYNC_MINUTES`, plus **Sync now** for Admin and Data Manager): export →
  read in memory → only the listed columns of Queries and Pending forms are kept (demographics and form
  values are never stored) → the export file is deleted from Viedoc → the connection's rows are
  replaced. If anything fails the previous copy stays and the error is shown. Syncs are audited
  (`dm.synced`).
- Each query's current state and timeline are rebuilt from its history rows: open at site (the site's
  clock), answered awaiting approval (our clock), closed; an answer sent back counts as a re-open.
- Data Management tab (menu entry for `dm.view`, only while the module is on): Overview (tiles, sites,
  ageing, forms) and Queries (filters, worst first, timeline). Without a Viedoc connection, or with
  `VIEDOC_MODE=mock` (always in tests and browser tests), a labelled demo study is used.
- First real sandbox sync: DEMO_IS, 314 validation queries (236 open at site, 26 awaiting approval, 52
  closed), 1,845 unconfirmed missing fields, 527 pending forms; all open queries over 30 days old.

### Decisions answered (12 Nov 2026)

1. **Who approves site answers:** both the Data Manager and the CRA, **in Viedoc**. Avi.Intelligence
   stays read-only and only shows the "awaiting approval" backlog.
2. **Ageing targets:** sites answer within **5** working days (agreed). Our approval target stays at
   **3** working days until confirmed. Both are settings.
3. **Before any live study:** query text is kept; people are shown by **role only, never by name**.
   Staff names from Viedoc (query history, SDV, review, sign and lock "by") are no longer stored.
   Dates are kept.
4. **Protocol deviations:** the source is **SimpleTrials** (DM Step 4).
5. **Access:** everyone can open Data Management, read-only (`dm.view` for all roles). Only **System
   Admin and Data Manager** can download data or Excel files (`dm.export`); **CRAs cannot download**.
   Avion's Quality and data-protection sign-off before live studies now also covers this wider read
   access.
6. **Sync now for everyone** (it is read-only towards Viedoc). Viedoc builds one export at a time per
   study, so a second press while a sync is running is refused ("already running"), and a press within
   2 minutes of a successful sync reuses it instead of asking Viedoc again. Every real sync is audited.
7. **Excel downloads (DM Step 2, first part):** **Download Excel** on the Queries and SDV tabs, for
   System Admin and Data Manager only. The file holds exactly the list on screen (same view and
   filters, e.g. one site), plus an About sheet (study, filters, source and as-of time, targets, rules,
   "subject IDs only, roles not names"). Every download is audited (`dm.exported`).

### Step 3: Missing data and Labs (built 12 Nov 2026, shown before committing)

- **Missing data tab:** missing fields (Viedoc "unconfirmed missing data"), pending forms and forms
  awaiting a design upgrade (49 in the sandbox, shown apart). Each missing field now keeps its visit,
  visit date, form, field label and **when the form was saved blank**; the site's clock (5 working days)
  runs from then, and from "pending since" for pending forms. Tiles, sites (most overdue first),
  subjects with the most gaps, fields most often left blank, by visit; quick views Missing fields /
  Overdue / Pending forms / Awaiting upgrade; filters and Excel as on the other tabs.
- **Labs tab, flags only (user decision, 12 Nov 2026):** lab values are read in memory during the sync
  and only the outcome is stored per expected result: reported / missing / not done, out of range (high
  or low) against the normal range entered on the form, unit or normal range missing, the investigator's
  evaluation (normal / abnormal NCS / abnormal CS) and whether a CS result has its AE/MH reference. No
  result values and no normal-range numbers are stored; people open Viedoc to see a value.
- Lab forms are recognised from their CDASH-style item IDs (`…ORRES`, `…ORRESU`, `…ORNR_Lower/Upper`,
  `…RANGE`, `…TEST`, `…CLSIG`, `…CSREF`, `…ND`, `…PERF`/`…LBYN`), in both of Viedoc's layouts (repeating
  rows with an analyte column, or one column set per analyte). Only result items with "LB" in their prefix
  count: vital signs, ECG and the qualitative pregnancy test are left out. The Viedoc API has no lab
  reference-range export, so ranges come from the form (filled for few results in the sandbox).
- Views: To check, Out of range, Clinically significant, Missing results, Not evaluated, No unit, No
  normal range, All; plus by analyte (most often missing first, which shows "missing across many
  subjects") and by site. "Out of range but evaluated normal" is flagged for checking with the site.
- First sandbox sync: 1,845 missing fields (23 subjects), 527 pending forms (oldest 149 days), 49 forms
  awaiting upgrade; labs 472 results on 5 lab forms (72 of 431 expected reported, 41 not done), 3 out of
  range, 7 clinically significant (none with an AE/MH reference), 19 not evaluated, 44 without a normal
  range, 20 without a unit.

## 2026-11-11: Reports and Insights, Steps 3–5 (Work management, Quality (SOPs), eTMF)

All three tabs follow Step 1's pattern: headline tiles, charts that state their rule, filters kept in the
address, an audited Excel export with an About sheet, and print to PDF.

**Work management** (Avi.Intelligence's own tasks, risks and issues; live, no sync needed)
- Tiles: open tasks, overdue, due in 14 days, completed in 30 days (on time = finished on or before the due
  date, by the day the last person finished), open High risks and issues.
- Open tasks by category and by study (Not started / In progress / Blocked, with the overdue count); every
  study in scope is listed, even with no open tasks.
- **Open work by person counts each person's unfinished part**: a task with three people counts once for
  each; someone who has finished their part is not counted (agreed per-person status model).
- Overdue tasks name who it is still waiting on. Risk heat map: 3 × 3 likelihood × impact of Open and
  Mitigating risks and issues (score ≥ 6 High, 3–4 Medium, 1–2 Low), plus the five highest.
- Filters: study and task category. The category filter applies to tasks only; risks always belong to a
  study, so the study filter applies to them too.

**Quality (SOPs)** (the SharePoint library, approved documents, plus what is read from inside each file)
- Review schedule of approved SOPs: next review from SharePoint or the cover page; Overdue (date passed),
  Due within 30 days (same window as the SOP library), Scheduled, No review date. Forms are reviewed with
  their SOP and are not scheduled separately. Each row shows its forms and open Procedures and SOPs tasks.
- Reviews due by month: an Overdue column, then the next 12 months; later ones are counted below.
- Library health findings: approved SOP with no review date; approved SOP or form with no effective date
  (drafts and in-review documents are not flagged); SOP with no owner; file name and cover page disagree
  on the version; form without an editable Word copy; form whose SOP is not in the library; no number.
- Change log: entries from each document's change history issued in the period (3, 6, 12 or 24 months);
  when a file has no readable change history, the date its current version took effect is used instead,
  and the row says so.
- **Training impact** (who is affected by SOP changes) is left out until a training records connector
  exists.

**eTMF** (SimpleTrials `/documents`, metadata only; see docs/simpletrials-setup.md)
- Synced with each SimpleTrials sync into `etmf_documents` (replaced per study, like sites). Expected =
  placeholders (user decision); superseded versions and attachments of other records are left out.
- Completeness = filed ÷ expected; sites with the most missing documents; a site × TMF section heat map;
  QC status as recorded (shown as "No QC recorded" when SimpleTrials has none); filing timeliness in
  working days (Mon–Fri) from the document's own date (signature date, else version date) to filing,
  target 5 working days (user decision), documents without a date shown separately; documents expired
  or expiring within 60 days. The Excel export starts with the full list of missing documents.
- **Known gap:** site-level documents match SimpleTrials' eTMF dashboard exactly, but the single-study key
  receives only 6 of 221 study-level TMF documents, so study-level completeness is understated. The tab
  is shipped with this stated; figures should not be shared until SimpleTrials confirms how to read the
  study-level eTMF (possibly the Workspace key).

## 2026-11-11: Ask Avi.Intelligence about studies (no AI)

- User decision: answer study questions **without an Anthropic key or paid calls**, read-only, but leave room
  to switch on Claude later.
- The Ask box now handles both: a question that mentions a study, site or plan entry, or asks what is due,
  behind, enrolled, activated, or about tasks/risks, gets a **study answer**; questions about procedures
  (SOP, form, template, process, requirements, "how do I", SAE, training…) still go to SOP search.
- Study answers are worked out by fixed rules from the read-only SimpleTrials copy (synced hourly) plus
  Avi.Intelligence's own tasks and risks, using the **same rules as the Study Command Centre and Reports**
  (overdue, due soon = 14 days, slipped > 30 days, on plan). Each answer shows how the question was read,
  the answer, tables linking to the source records, the "data as of" time and follow-up questions. Nothing
  is sent outside Avi.Intelligence, SimpleTrials is not called while answering, and no patient data is read.
- Understood: status (one study, all studies, or a site), what is due (default next 90 days, or "next 30
  days", "this month"…), close-out (phases containing "close", LPO, database lock, CSR, study end), what is
  behind, milestone dates ("When is LPI?"; abbreviations and spelling mistakes tolerated; "first" never
  matches "last"), enrolment against target, site activation, open tasks and risks. A plan entry's name
  only counts when the question is about timing or names a study or site, so "site initiation visit"
  alone stays an SOP search.
- Every study question is recorded like SOP questions (`assistant_interactions`, mode `study-lookup`) and in
  the audit trail (`assistant.asked`, kind `study`).
- **Later, with an Anthropic key:** the look-ups in `app/assistant/study_tools.py` are already written as
  tools (typed inputs, descriptions, `anthropic_tool_definitions()`, `run_tool()`), so Claude can be given
  them unchanged for free-form questions. Until that is built and agreed, study questions stay rule-based
  even when a key is set.
- Limitations: it understands questions built from words it knows, one subject at a time; there is no
  enrolment history yet (only today's figure against target), so recruitment pace is not judged.

## 2026-11-09: Task categories (Procedures and SOPs, Vendor, Computer system, General)

- Tasks now have a **category**: Study (as before), Procedures and SOPs, Vendor, Computer system, General.
  Existing tasks became Study tasks; the study is now optional (only Study tasks have one).
- **Procedures and SOPs tasks** name one or more SOPs/forms (user decision: one or more), chosen only from
  the live approved list; the server re-checks each one. The SOP number, title and version are stored
  with the task when it is raised (`task_documents`), so it still reads "Review CO-SOP-005 v2.0" after
  v3.0 is approved. SOPs already on a task keep their original snapshot when the task is edited.
- **Vendor / Computer system:** the name is typed on each task (user decision; no managed list yet, so
  spelling variants count separately in reports).
- **Who assigns what (user decision):** permissions per category (`task.assign.<category>`).
  Admin: all. Project Manager: Study and General (not Procedures and SOPs). New role **Quality Assurance
  (`qa`)**: Procedures and SOPs, Vendor, Computer system and General. Whoever may assign a category may
  also edit and cancel its tasks. QA and PM also see the audit trail (assumption).
- **Own tasks (user decision):** everyone except viewers (CRA, new **Clinical Trials Associate (`cta`)**,
  Data Manager, Pharmacovigilance, and PM/QA outside their categories) may create tasks for themselves
  only, for their own tracking, and edit or cancel them. Never Procedures and SOPs tasks: only QA and
  Admin create those, even for themselves. Own tasks are visible to everyone (read-only to others).
  The Safety role is now labelled "Pharmacovigilance".
- **Several people per task (user decision):** each person has their own status (`task_assignees`); the
  task shows "1 of 3 completed" and is Completed when everyone is done, Blocked if anyone is blocked,
  In progress once anyone has started. Only someone who may edit the task cancels it; setting a status
  in the edit form applies to everyone. Re-assigning keeps the statuses of people who stay. Existing
  tasks were migrated with their single assignee.
- Each SOP/form page lists its open tasks and offers "New task" to administrators and QA.
- Portfolio open-task counts include Study tasks only.

## 2026-11-09: Reports and Insights, Step 1 (foundations) and Study delivery

- User decisions: SimpleTrials sync **hourly** (`SIMPLETRIALS_SYNC_MINUTES=60`, 0 = off, never in tests);
  **Excel and PDF** exports; **daily snapshots** start now; eTMF "expected" = placeholders, filing target
  5 working days (for the eTMF step).
- The hourly sync runs inside the API process (no extra service); each run is an ordinary read-only sync
  recorded as "system (scheduled)". The first sync of each day stores a small snapshot of key figures
  (`report_snapshots`) so trends can be drawn later; history starts from today.
- **On-time completion:** SimpleTrials' API has no actual completion date. Avi.Intelligence records the
  day a sync first sees a milestone at 100% (`milestone_completions`), but only if an earlier snapshot saw
  it incomplete; milestones already complete when tracking began get no date and are left out of
  on-time figures rather than guessed.
- Site activation compares SimpleTrials' actual activation date with its planned
  (`site_activation_target`) date, now synced.
- Excel exports carry an "About" sheet (scope, data as of, source, rules) and are audited
  (`report.exported`). PDF uses the browser's Save as PDF with a print layout (A4 landscape, navigation
  and filters hidden, colours kept); a generated PDF file can be added later if needed.
- Charts are plain HTML/CSS (no chart library), following the approved mock-up; every chart states its
  rule, every number has a text label, colour is never the only signal.

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
