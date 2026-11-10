# SimpleTrials connector (studies, sites, milestones)

SimpleTrials is Avion's CTMS and remains the **system of record** for studies. Avi.Intelligence only
reads from it and keeps a read-only copy in its own database, stamped with the sync time. Nothing in
Avi.Intelligence writes back to SimpleTrials.

## Modes

| Mode | How data arrives |
|---|---|
| `api` (**working**, tested on the Sandbox study) | SimpleTrials REST API v1 with a **read-only** key |
| `mock` | Fictional demo studies, labelled "Demo data" on every screen |

`SIMPLETRIALS_MODE=auto` (default) uses the API when credentials are set, otherwise demo data.

## Enabling the API (no vendor contact needed)

Requirements (SimpleTrials API Guide, Dec 2025): a **Premium Plus** subscription and a SimpleTrials
user of type **Administrator**.

1. SimpleTrials → **Administration → Subscription & Settings → Customer Details → Manage API**.
2. Choose the scope and enable **Read-only Access** only (never Full Access):
   - one study (start with the **Sandbox** study, which holds fictitious data), or
   - **Workspace/All Studies** (needed to list all studies; approve with Avion first).
3. **View Credentials** and put them in the repo-root `.env` (never in chat, email or Git):

```ini
SIMPLETRIALS_BASE_URL=https://app.simpletrials.com/api/v1/   # eu. or apac. for other hosting
SIMPLETRIALS_STUDY_ID=        # single-study access
SIMPLETRIALS_STUDY_KEY=
SIMPLETRIALS_CUSTOMER_ID=     # workspace access (takes precedence when set)
SIMPLETRIALS_CUSTOMER_KEY=
```

4. Check: `cd backend; uv run python -m app.check_simpletrials`, then restart the backend.

### How the connector reads SimpleTrials

| Avi.Intelligence | SimpleTrials API |
|---|---|
| Study list | `GET /studies` (workspace access only) |
| Study details, enrolled, target | `GET /study`: `number`, `name`/`description`, `sponsor`, `phase_display`, `status_display`, `actual_enrolled`, `revised_targets`/`original_targets.enrolled` |
| Sites | `GET /sites`: `number`, `organization_display_name`, PI, `status_display` + `substatus_display`, `detail.site_activation_actual`, `detail.subjects_enrolled_actual/target` |
| Milestones & tasks | `GET /tasks`: the **whole** *Milestones & Tasks* plan in SimpleTrials order. Phase = has children; milestone = zero duration or a SimpleTrials milestone code (`system_name`, e.g. `fpi`); task = the rest. `baseline_start_date` / `start_date` (original / current start), `baseline_end_date` / `end_date` (original / current end), `percent_complete` |

| eTMF document metadata | `GET /documents`: `placeholder` (expected, not yet filed), `state` (`staged` / `uploaded`), `tmf_level`, `site_id`, `document_path` (section = first folder below the study, or below `BY SITE/<site>`), `common_name`/`title`, `doc_status_display`, `qc_status` and QC dates, `uploaded_at`, `signature_date`/`doc_version_on`, `expires_on`, `expiration_status`, `doc_version`. Records that are another record's `precursor_id` (older versions) or have a `parent_type` (e.g. payment attachments) are left out. |

The API has **no actual completion date** for milestones, so "Completed" means 100% complete in
SimpleTrials. Patient-level data (`/subjects`) is deliberately not read.

**eTMF: metadata only.** Files are never downloaded, and file names, links, descriptions, user ids and
the investigator names inside folder paths are not stored. If `/documents` cannot be read (for example
the key has no eTMF access), the study still syncs and the last eTMF copy is kept.

**Known gap (Nov 2026):** with the single-study Sandbox key, `/documents` returns the site-level documents
exactly as the eTMF dashboard shows them (e.g. site 1001: 54), but only 6 of the study's 221 study-level
TMF documents (none of the 91 Final ones). `/documents` accepts only the `state` filter, and no other
eTMF endpoint exists. Open question for SimpleTrials: which call returns study-level TMF documents, and
whether a Workspace key sees more. Until then the eTMF report under-counts filed study-level documents.

### Two statuses per plan entry

| Status | Rule |
|---|---|
| **Progress** (vs current end date) | Completed (100%) · Overdue (current end passed, < 100%) · Due soon (within 14 days) · In progress (started) · Not started (start in future) |
| **Schedule** (current vs original end date) | On plan · Slipped +N days (amber; red when more than 30) · Ahead −N days · No original date |
| Start moved (tag on the current start) | "starts +Nd" / "starts −Nd" when the current start differs from the original start |

### Key milestones

Key milestones (★) drive the Portfolio headline (overdue count, next milestone); other plan entries
never do. They are SimpleTrials' coded milestones (`project_start_date`, `first_siv`, `fps`, `fpi`,
`all_sites_activated`, `lps`, `lpi`, `lpo`, `project_end_date`) plus the names in
`SIMPLETRIALS_KEY_MILESTONES` (semicolon-separated; numbering and case ignored). Default:
Protocol Finalized; First Ethics Approval; Database Hard Lock; Clinical Study Report Finalized.

### Security

- Keys are sent as URL query parameters (SimpleTrials' design). Avi.Intelligence never logs request
  URLs, masks `study_key`/`customer_key` in all log output, and keeps keys out of error messages.
- Only `GET` requests are made, one at a time (the API is rate limited), with back-off on HTTP 429.
- Only `app|eu|apac.simpletrials.com` over HTTPS is accepted as the API address.
- The SimpleTrials API Guide is confidential to licensed subscribers: do not commit it to this repo.

## What is synced

| Record | Fields |
|---|---|
| Study | protocol number, title, sponsor, phase, therapeutic area, status, countries, project manager, enrolment target |
| Site | site number, name, country, principal investigator, status, activation date, enrolled, enrolment target |
| Milestone | name, planned date, actual date |

Field names will be adjusted to match the SimpleTrials export once a sample is available.

## Sync behaviour

- The first time anyone opens a study screen, a sync runs automatically.
- Administrators can run **Sync now** (Study Portfolio or Administration → Connectors). Each sync is
  recorded (`connector_syncs`) and audited.
- A failed sync never deletes data: screens keep showing the last successful copy and say so.
- A study that disappears from SimpleTrials is flagged *No longer in SimpleTrials* rather than deleted,
  so its tasks and risks are kept.

## Indicators (no estimates)

| Indicator | Rule |
|---|---|
| Overdue milestone | Planned date has passed and SimpleTrials has no actual date |
| Due soon | Planned within the next 14 days, not completed |
| Enrolment % | Enrolled (sum of sites) ÷ study target. **Not shown** if there is no target |
| Overdue task | Due date passed and the task is not completed or cancelled |
| Risk score | Likelihood × impact as entered (1–3 each). 6+ High, 3–4 Medium, 1–2 Low |

## Tasks, risks and issues: who can do what

| Action | Administrator | Assigned person / risk owner | Everyone else |
|---|---|---|---|
| View tasks, risks, studies | ✓ | ✓ | ✓ |
| Create, assign, edit | ✓ | — | — |
| Change status | ✓ | ✓ (own items only) | — |
| Cancel a task | ✓ | — | — |

Nothing is deleted: tasks are cancelled and risks closed. Every change is in the Audit Trail.

Until Microsoft sign-in is added, people come from a demo directory (`backend/src/app/auth/directory.py`).
To try the assignee view locally, set for example `DEV_USER_ID=demo-cra-1` and `DEV_USER_ROLE=cra`
in `.env` and restart the backend.

