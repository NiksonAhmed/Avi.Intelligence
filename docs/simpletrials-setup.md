# SimpleTrials connector (studies, sites, milestones)

SimpleTrials is Avion's CTMS and remains the **system of record** for studies. Avi.Intelligence only
reads from it and keeps a read-only copy in its own database, stamped with the sync time. Nothing in
Avi.Intelligence writes back to SimpleTrials.

## Modes

| Mode | Status | How data arrives |
|---|---|---|
| `mock` | **Available now** | Fictional demo studies, labelled "Demo data" on every screen |
| `import` | Next | SimpleTrials export files (Excel/CSV) uploaded by an administrator, or dropped in a SharePoint folder |
| `api` | Later, if SimpleTrials offers it | Scheduled sync over the SimpleTrials API with a read-only key |

The screens do not change between modes; only the connector does.

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

## Questions to ask SimpleTrials

1. Do you provide an API for our account? Can we have the documentation?
2. How does authentication work (API key, OAuth)? Can we have a **read-only** credential?
3. Is there an additional cost?
4. Can reports (study list, sites, milestones, enrolment) be exported on a schedule?
