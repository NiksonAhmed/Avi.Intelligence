# Deploying Avi.Intelligence to AWS

A handover for the IT administrator who will host Avi.Intelligence. It covers what the app is, what to build in
AWS, the settings and secrets it needs, and the checks before go-live. Questions about the app itself go to the
Avi.Intelligence owner.

## 1. What the app is

An internal web app for Avion's clinical operations staff. Staff sign in with their Microsoft (Entra) account.
It **reads** from other systems and keeps a working copy in its own database:

| Source | What it reads | Access |
|---|---|---|
| SimpleTrials (CTMS) | Studies, sites, plans, eTMF metadata, action items, deviations, site visits | Read-only API key |
| Microsoft SharePoint (Graph) | Approved SOPs and forms, the site feasibility tracker, BD conference schedules | App registration, `Sites.Selected`, read-only grants on two sites |
| Viedoc (EDC) | Data-management figures: queries, SDV, missing data (subject IDs only) | Read-only API client. **Not live yet**: real studies only after go-live on AWS and Quality sign-off |

It never writes back to these systems. No patient-level data comes from SimpleTrials. Budgets and eTMF file
names are not stored. EDC data is never sent to AI.

Data stored by the app itself (exists nowhere else): tasks created in Avi.Intelligence, the audit trail, CRA site
assignments, report snapshots. **This is the data that needs backups.**

## 2. Architecture

Two containers and a PostgreSQL database. Both Dockerfiles are in the repository.

```
 Browser ──HTTPS──> Load balancer (TLS) ──> frontend (nginx :8080) ──/api/──> backend (FastAPI :8000) ──> PostgreSQL
                                                                                   │
                                                                                   └──outbound HTTPS──> Microsoft, SimpleTrials, Viedoc
```

| Part | Build | Notes |
|---|---|---|
| `frontend` | `frontend/Dockerfile` | Static React app served by nginx. nginx proxies `/api/` to the backend and sets security headers (CSP, X-Frame-Options and others; see `frontend/nginx.conf`). |
| `backend` | `backend/Dockerfile` | Python 3.12, FastAPI. Runs as a non-root user. **Applies database migrations on start** (`alembic upgrade head`). Health check: `GET /api/health` returns `{"status":"ok"}`. |
| Database | PostgreSQL 16 | Connection string in `DATABASE_URL` (`postgresql+psycopg://…`). |

`docker-compose.yml` runs the same three parts locally and is a working reference for how they connect.

### Important: run exactly one backend instance

The backend runs its own background jobs: the hourly SimpleTrials sync and the Viedoc sync. **Two or more backend
instances would run every sync twice.** Run one backend task (desired count 1, no auto-scaling) until the jobs are
moved out. The frontend can scale freely.

## 3. Suggested AWS setup

Region: **ap-southeast-2 (Sydney)**, so the data stays in Australia.

| Need | Suggested service |
|---|---|
| Containers | ECS on Fargate: one service for the frontend, one for the backend (desired count 1). Images in ECR. |
| HTTPS | Application Load Balancer with an ACM certificate. Redirect HTTP to HTTPS. |
| Database | RDS for PostgreSQL 16, **encrypted at rest**, automated backups (at least 14 days suggested), in private subnets. A small instance is enough to start. |
| Secrets | AWS Secrets Manager, injected into the backend task as environment variables (section 4). |
| Network | Containers and RDS in private subnets. Outbound internet through a NAT gateway (section 5). Security groups: load balancer → frontend, frontend → backend, backend → RDS only. |
| Logs | CloudWatch Logs. The backend writes one JSON line per request. Keys are masked in logs. |
| Address | A name such as `avi.<avion-domain>` pointing at the load balancer. |

Optional: limit the load balancer to Avion's office or VPN IP ranges (AWS WAF or security group). Everyone still
has to sign in with Microsoft either way.

A simpler alternative for a trial is one small EC2 instance running `docker compose`, with RDS for the database.
The ECS setup above is the recommended long-term option.

**Nginx and the backend address.** `frontend/nginx.conf` proxies to `http://backend:8000`, the name used in
Docker Compose. On ECS, either give the backend that name (ECS Service Connect / Cloud Map) or route `/api/*` to
the backend directly at the load balancer.

## 4. Settings and secrets

The full list with comments is in `.env.example` at the repository root. **Never put real values in the
repository, email or chat.** The app owner enters secret values into Secrets Manager or gives them over in person
or through a password manager.

Set for production:

| Setting | Value |
|---|---|
| `APP_ENV` | `production` (the app then refuses to run without Microsoft sign-in and hides its API docs) |
| `DATABASE_URL` | `postgresql+psycopg://<user>:<password>@<rds-endpoint>:5432/<db>` (**secret**) |
| `CORS_ORIGINS` | `https://avi.<avion-domain>` |
| `APP_TIME_ZONE` | `Australia/Sydney` |
| `LOG_LEVEL` | `INFO` |
| `USE_SYSTEM_TRUST_STORE` | `false` (only needed on Avion's office network) |

Sign-in (Microsoft Entra), not secret:

| Setting | Value |
|---|---|
| `ENTRA_TENANT_ID` | Avion's tenant (directory) ID |
| `ENTRA_CLIENT_ID` | The *Avi.Intelligence* app registration's client ID |
| `ENTRA_ROLE_MAP` | Leave empty unless the app roles change (see `docs/entra-setup.md`) |

Connections. Values marked **secret** go in Secrets Manager:

| Setting | Notes |
|---|---|
| `SHAREPOINT_TENANT_ID`, `SHAREPOINT_CLIENT_ID` | Same app registration as sign-in |
| `SHAREPOINT_CLIENT_SECRET` | **secret**. Expires around November 2027: set a reminder to rotate it |
| `SHAREPOINT_SITE_URL`, `SHAREPOINT_SOP_*` | The SOP library (copy from the current setup) |
| `SITE_FEASIBILITY_DRIVE_ID`, `SITE_FEASIBILITY_ITEM_ID` | The feasibility tracker workbook |
| `CONFERENCES_SHAREPOINT_LIBRARY`, `CONFERENCES_SHAREPOINT_SITE_URL` | The BD conference schedules |
| `SIMPLETRIALS_BASE_URL`, `SIMPLETRIALS_CUSTOMER_ID` | Workspace (all studies) access |
| `SIMPLETRIALS_CUSTOMER_KEY` | **secret** (read-only key) |
| `SIMPLETRIALS_EXCLUDED_STUDIES` | `Sandbox Study,TC 01 EC 01` (test studies left out) |
| `VIEDOC_CONNECTIONS__<NAME>__API_URL`, `…__CLIENT_ID`, `…__ENVIRONMENT` | One set per Viedoc study. Later, after Quality sign-off |
| `VIEDOC_CONNECTIONS__<NAME>__CLIENT_SECRET` | **secret** |
| `VIEDOC_ALLOW_LIVE`, `DATA_MANAGEMENT_ENABLED` | Leave `false` until the Viedoc go-ahead |
| `ANTHROPIC_API_KEY` | **secret**. Not used yet (the assistant runs without AI for now) |

Do **not** set `DEV_USER_ROLE` or `DEV_USER_ID` in production. They are a local development stand-in for sign-in
and are ignored when `APP_ENV=production`.

## 5. Outbound network access (backend only)

The backend needs outbound HTTPS (port 443) to:

| Host | For |
|---|---|
| `login.microsoftonline.com` | Microsoft sign-in keys and app tokens |
| `graph.microsoft.com` | SharePoint |
| `*.sharepoint.com` | SharePoint file downloads |
| `app.simpletrials.com` | SimpleTrials API |
| The Viedoc API host(s) in `VIEDOC_CONNECTIONS__*__API_URL` | Viedoc (later) |
| `api.anthropic.com` | AI assistant (later) |

No inbound access is needed apart from the load balancer. The frontend needs no outbound access.

## 6. Microsoft Entra change (Avion's Microsoft admin)

In the *Avi.Intelligence* app registration, under **Authentication → Single-page application**, add the new
address as a redirect URI, e.g. `https://avi.<avion-domain>`. Without it, sign-in fails with `AADSTS50011`.
Nothing else in Entra changes. The app roles, API scope and SharePoint site grants stay as they are.

Recommended at the same time:
- **Enterprise applications → Avi.Intelligence → Properties → Assignment required: Yes**, then assign the
  people or group who should use the app. Without this, anyone in Avion's tenant can sign in as a viewer.
- Make sure a Conditional Access policy requires **MFA** for this app.

## 7. Data on first start

The new database starts empty. Migrations create the tables, and the first syncs fill them from SimpleTrials and
SharePoint (the SimpleTrials sync takes a few minutes, because its API is rate limited).

Tasks, the audit trail and site assignments created on the current local copy are **not** carried over unless
the app owner asks for a one-off export and import. Decide this before go-live.

## 8. Deploying updates

1. Build both images from the `main` branch and push them to ECR.
2. Update the ECS services. The backend applies any new database migrations as it starts.
3. Check `GET /api/health`, then sign in and open the Portfolio page.

The repository's GitHub Actions CI (`.github/workflows/ci.yml`) runs the tests and linters on every pull request.
Deploy only from `main` after CI passes. Automating build and deploy from `main` (GitHub Actions to ECR and ECS
with an OIDC role, no stored AWS keys) is a good next step.

## 9. Go-live checklist

- [ ] Images built from `main`. Both open pull requests (Conferences, SimpleTrials) merged first.
- [ ] RDS encrypted, automated backups on, not publicly accessible.
- [ ] All secrets in Secrets Manager. None in the task definition as plain text, the image or the repository.
- [ ] `APP_ENV=production`, `CORS_ORIGINS` set to the real address, `DEV_USER_*` not set.
- [ ] One backend task only.
- [ ] HTTPS only. HTTP redirects to HTTPS.
- [ ] Entra redirect URI added. Assignment required on. MFA policy covers the app.
- [ ] Sign-in works, and each role sees what it should (an admin and a viewer account at least).
- [ ] Portfolio shows the 4 real studies. SOPs, Conferences and Site feasibility show live data, not "demo".
- [ ] CloudWatch logs arriving. An alarm on the backend health check.
- [ ] Restore from an RDS backup tested once.

## 10. What not to share

The IT administrator needs repository access and this guide. They do **not** need, and should not receive:
- the local `.env` file or any key value by email or chat (enter secrets directly into Secrets Manager);
- the SimpleTrials API guide (confidential vendor document);
- the site feasibility tracker or any downloaded study files.
