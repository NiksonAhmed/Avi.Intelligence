# Connecting Avi.Intelligence to Avion SharePoint (SOP library)

Avi.Intelligence reads SOPs from SharePoint using Microsoft Graph with an **app-only**
(client-credentials) registration. It only **reads**: it never edits, uploads or deletes documents.

## 1. App registration (Microsoft Entra ID, done by IT)

1. Entra admin centre → **App registrations** → **New registration**
   - Name: `Avi.Intelligence`
   - Supported account types: *Accounts in this organisational directory only*
2. **Certificates & secrets** → New client secret (record the value and its expiry date).
   A certificate is preferred for production; client secrets are fine for development.
3. **API permissions** → Add → Microsoft Graph → **Application permissions** →
   **`Sites.Selected`** → *Grant admin consent*.

`Sites.Selected` gives the app **no access to any site** until a site is explicitly granted (step 2).
Avoid `Sites.Read.All`: it would let the app read every site in the tenant.

## 2. Grant the app read access to the SOP site (SharePoint admin)

Using PnP PowerShell:

```powershell
Grant-PnPAzureADAppSitePermission -AppId <client-id> -DisplayName "Avi.Intelligence" `
  -Site https://<tenant>.sharepoint.com/sites/<QualitySite> -Permissions Read
```

Or with Graph (as an admin holding `Sites.FullControl.All`), `POST /v1.0/sites/{site-id}/permissions`:

```json
{ "roles": ["read"],
  "grantedToIdentities": [{ "application": { "id": "<client-id>", "displayName": "Avi.Intelligence" } }] }
```

## 3. Configure Avi.Intelligence

Put the values in the repo-root `.env` file (copy `.env.example`). Never commit this file or paste
secrets into chat, email or tickets.

```ini
SHAREPOINT_TENANT_ID=<directory (tenant) id>
SHAREPOINT_CLIENT_ID=<application (client) id>
SHAREPOINT_CLIENT_SECRET=<secret value>
SHAREPOINT_SITE_URL=https://<tenant>.sharepoint.com/sites/<QualitySite>
SHAREPOINT_SOP_LIBRARY=Documents          # library name as shown in SharePoint
SHAREPOINT_SOP_FOLDER=SOPs                # optional: limit to a folder (and its subfolders)
```

### Avion's current configuration

```ini
SHAREPOINT_SITE_URL=https://netorg4530830.sharepoint.com/sites/AM
SHAREPOINT_SOP_LIBRARY=Procedures and SoPs
SHAREPOINT_SOP_FOLDER=1. Avion SoPs
SHAREPOINT_SOP_EXCLUDE_FOLDERS=Avion Document Register;R3 Guideline Implementation
SHAREPOINT_SOP_FILE_TYPES=docx,doc,pdf
```

SOPs are organised in department subfolders (`01. Clinical Operations` … `10. Medical Physics`). When the
library has no department column, the department is taken from that subfolder name without its number.
Only Word and PDF files count as SOPs; other files in the folder (e.g. Excel trackers) are ignored.

## 4. Check the connection

```powershell
cd backend
uv run python -m app.check_sharepoint
```

This prints each check (token, site, library, columns, documents) and the library's column
**internal names**. The same information is in the app under **Administration → Connectors**.

## 5. Map your columns (if needed)

Avi.Intelligence tries common column names for each SOP field (see Administration → Connectors).
If your library uses different names, set `SHAREPOINT_SOP_FIELD_MAP` using internal names:

```ini
SHAREPOINT_SOP_FIELD_MAP={"sop_number": "DocNo", "status": "ApprovalStatus", "review_date": "NextReview"}
```

### How SOP status is decided

1. A status column (e.g. *Document Status*) if the library has one: values like *Approved/Effective*,
   *In review*, *Draft*, *Superseded*, *Retired* are recognised.
2. Otherwise SharePoint **content approval** (Approved / Pending / Draft / Rejected).
3. Otherwise the **version number**: major versions (`3.0`) are treated as published and minor
   versions (`3.1`) as drafts. The UI labels this *(inferred)*.

If none applies, the status shows as *Unknown*. Avi.Intelligence never guesses beyond these rules.

## Troubleshooting

| Message | Likely cause |
|---|---|
| `AADSTS7000215: Invalid client secret` | Secret value wrong or expired (use the *value*, not the secret ID). |
| `AADSTS700016: Application ... was not found` | Wrong client ID or tenant ID. |
| `Access denied` / 403 on the site | `Sites.Selected` site grant (step 2) missing. |
| `Document library "X" was not found` | Check `SHAREPOINT_SOP_LIBRARY`; the message lists the libraries that exist. |
| Owner shows "—" | Person columns are resolved via the site's user list; access may be restricted. |
| Certificate errors on a corporate network | See *Corporate network / TLS inspection* in the README. |
