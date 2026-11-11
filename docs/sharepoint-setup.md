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

### What Avi.Intelligence shows (verified against the library, 2026-11-06)

Connected 2026-11-06: **55 approved SOPs and 86 forms/templates** out of ~776 files in the folder.

| In SharePoint | In Avi.Intelligence |
|---|---|
| `CO-SOP-001 …`, `DM-SOP-002_…` | SOP, number `CO-SOP-001` (department prefix kept) |
| `CO-005-A …` | Form/template of `CO-SOP-005`, shown under that SOP |
| `SM-TEM-001 …`, `MP-FRM-001 …` | Stand-alone form/template |
| `Complete_with_Docusign_PM-SOP-002_…` | DocuSign's signed copy of that document; used when no plainly named signed PDF exists |
| `CC-012_…`, `Executed Forms` folders, unnumbered files (e.g. Avi.Data specifications) | Hidden (`SHAREPOINT_SOP_NUMBERED_ONLY=true`) |
| Folders `Approved` | Effective (unless the Document Status column says otherwise) |
| Folders `Draft Unapproved`, `…/Superseded` (also "Superceded"), `SOP under Revision` | Hidden (`SHAREPOINT_SOP_APPROVED_ONLY=true`) |
| Signed PDF + Word copy in `Word_Documents_DoNotEdit` | One entry: the PDF; version and full title taken from the Word copy if the PDF name lacks them. For **forms/templates** the Word copy is offered as a **Word** download (for filling in) next to the PDF; SOPs are only issued as the signed PDF. Downloads are audited with the format. |

- **Read from inside each approved SOP** (when the chatbot index is built): the cover page (Version
  Number, Effective Date, Next Review Date, Prepared / Reviewed / Approved By with dates) and the
  "Change History" table. Order of precedence: SharePoint column → the document → the file name.
  When the file name states another version than the document (e.g. ST-SOP-001: file 1.0, document
  2.0), the page shows "File name says 1.0". A blank Effective Date on the cover stays blank; the
  approval date is shown next to it, never substituted.
- On signed PDFs **DocuSign stamps the signing date into the Effective Date box** as a separate layer,
  in US month-first format ("11/10/2025" = 10 Nov 2025). Cover values are therefore read by position
  (text to the right of each label), and a numeric date that reads both ways takes the reading
  closest to the sign-off date.
- **Version** otherwise comes from the file name (`_2.0`, `v1.1`, `v_1.0`; DocuSign's `_20` = 2.0), never
  from SharePoint's own version number, which only counts saves (e.g. 6.0) and is not shown.
- **Title** comes from the file name; the Title column is ignored when it holds the template's
  placeholder ("SOP Template").
- **Ask Avi.Intelligence** indexes approved SOPs only, not forms or templates.

### Keeping up with changes in SharePoint

| Change in SharePoint | When Avi.Intelligence shows it |
|---|---|
| SOP added, moved to Superseded / Draft, renamed, column edited | Within `SHAREPOINT_CACHE_MINUTES` (5) on the next page load, or at once with *Refresh from SharePoint* |
| New or changed file (dates, sign-off, change history read from inside) | Re-read in the background right after that refresh; until then the page shows no document dates rather than the old ones |
| Any change, for the chatbot | Before every question the index is brought in line (new/changed files read, unapproved SOPs dropped), and only SOPs approved in SharePoint right now, as their current file, are used |

Re-index in Administration is only needed to force a full rebuild.
- SharePoint's Effective / Next Review columns are mostly blank, so the dates come from the documents.
  As of 2026-11-06 all 55 SOPs have both dates except: IT-SOP-001 (both boxes blank on the signed
  copy) and MW-SOP-008 (no signed v2.0 PDF filed; the Word copy has no Effective Date).
- Medical Physics SOPs (`10. Medical Physics`) are all marked Draft and sit outside an Approved
  folder, so they do not appear until approved and filed.

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
| `General exception while processing` (HTTP 401) on the site | The token has no permissions: `Sites.Selected` shows "Not granted" — click *Grant admin consent* in API permissions. |
| `AADSTS700016: Application ... was not found` | Wrong client ID or tenant ID. |
| `Access denied` / 403 on the site | `Sites.Selected` site grant (step 2) missing. |
| `Document library "X" was not found` | Check `SHAREPOINT_SOP_LIBRARY`; the message lists the libraries that exist. |
| Owner shows "—" | Person columns are resolved via the site's user list; access may be restricted. |
| Certificate errors on a corporate network | See *Corporate network / TLS inspection* in the README. |
