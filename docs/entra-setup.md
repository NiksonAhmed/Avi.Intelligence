# Microsoft sign-in (Entra ID) for Avi.Intelligence

This guide is for the Microsoft 365 / Entra administrator. It sets up single sign-on: Avion staff open
Avi.Intelligence and sign in with their usual Microsoft work account.

**First trial: one role.** Only the **Admin** role is created and given to one person. Everyone else at
Avion who signs in becomes a **Viewer** (read-only) automatically. More roles can be added later (see the
end of this guide) without any change to the app.

Time needed: about 15 minutes.

## What this does and does not change

Everything below is created **inside one new app registration called Avi.Intelligence**.

- It does **not** change any user, group, licence, mailbox, Teams or SharePoint permission.
- The role you create exists only on this app. No other application can see or use it.
- No tenant-wide setting is changed. Conditional Access, user consent settings and default permissions are
  not touched.
- The only Microsoft Graph permission is **User.Read**: the signed-in person's own name and email.
- Removing access later is one step: delete the app registration.

**Please don't:**
- **Add people to an existing group to give them a role.** If that group is also used by another app,
  they would get that app's access too. Assign the role to people directly, or create new groups used
  only for this app (for example `AviIntel-Admin`).
- **Turn on "Assignment required".** Leaving it off is what lets every Avion employee sign in as a Viewer.

## Step 1: Register the app

1. Go to **https://entra.microsoft.com**, then **Identity → Applications → App registrations → New registration**.
2. **Name:** `Avi.Intelligence`
3. **Supported account types:** *Accounts in this organizational directory only (Avion only, single tenant)*.
4. **Redirect URI:** platform **Single-page application (SPA)**, address `http://localhost:5173`
5. Click **Register**.
6. On the app's **Overview** page, note the two values below. Neither is a secret, so they can be emailed.
   - **Application (client) ID**
   - **Directory (tenant) ID**
7. Open **Authentication**. Under *Single-page application*, add a second redirect URI,
   `http://127.0.0.1:5173`, and click **Save**. Leave everything else on the page as it is.

## Step 2: Let the app sign people in to itself

1. Open **Expose an API**.
2. Next to **Application ID URI**, click **Add**, accept the suggested `api://<client ID>`, then **Save**.
3. Click **Add a scope** and fill in:
   - **Scope name:** `access_as_user` (exactly this)
   - **Who can consent:** Admins and users
   - **Admin consent display name:** `Sign in to Avi.Intelligence`
   - **Admin consent description:** `Lets Avi.Intelligence know who you are.`
   - **State:** Enabled
   Then click **Add scope**.
4. Open **API permissions → Add a permission → APIs my organization uses** (or **My APIs**), choose
   **Avi.Intelligence**, then **Delegated permissions**, tick `access_as_user`, and click **Add permissions**.
   `Microsoft Graph · User.Read` is already listed; leave it.
5. Click **Grant admin consent for Avion** and confirm. Staff are then not asked to approve anything when
   they first sign in. The consent covers only this app.

## Step 3: Create the Admin role (on this app only)

1. Open **App roles → Create app role**.
2. Fill in:
   - **Display name:** `Admin`
   - **Allowed member types:** Users/Groups
   - **Value:** `admin` (exactly this, lower case)
   - **Description:** `Full access to Avi.Intelligence, including administration and the audit trail.`
   - Tick **Do you want to enable this app role?**
3. Click **Apply**.

## Step 4: Give the Admin role to one person

1. Go to **Identity → Applications → Enterprise applications** and open **Avi.Intelligence**. It was
   created automatically in step 1.
2. Open **Users and groups → Add user/group**.
3. **Users:** pick the person. **Select a role:** Admin. Click **Assign**.
4. In **Properties**, check that **Assignment required?** is **No**, which is the default.

## Step 5: Switch sign-in on in Avi.Intelligence

On the computer running Avi.Intelligence, add these two lines to the `.env` file in the repository folder,
using the values from step 1:

```
ENTRA_TENANT_ID=<Directory (tenant) ID>
ENTRA_CLIENT_ID=<Application (client) ID>
```

Restart the backend. To switch sign-in off again, blank both lines and restart. The app then goes back to
development mode.

## Step 6: Check it works

1. Open **http://localhost:5173**. Microsoft's sign-in page should appear, or you may be signed in
   straight away if you're already signed in to Microsoft 365.
2. At the top right you should see your own name, **Role: Admin** and **Signed in with Microsoft**. The gold
   "Development mode" tag should be gone.
3. **Audit Trail** shows a *Signed in with Microsoft as admin* entry.
4. Ask a colleague without the role to sign in. They should see **Role: Viewer**, and no Administration or
   Audit Trail pages.
5. **Sign out** is in the menu under your name.

**If something goes wrong:**
- *"AADSTS50011: redirect URI mismatch"*: the address in the browser isn't one of the redirect URIs in step 1.
  Use `http://localhost:5173` or add the address you used.
- *"AADSTS65001: consent"*: admin consent wasn't granted (step 2.5).
- *Role shows Viewer for the admin:* the role value isn't exactly `admin`, or it was assigned on a different
  app. Sign out and back in after changing it.

## Avion's roles

Avion's app roles (created 23 Nov 2026) and what each becomes in Avi.Intelligence. The **Value** is what
matters; case, spaces and punctuation are ignored. Anyone with no role is a Viewer. If someone has more
than one role, the one with more access wins.

| Value in Entra | In Avi.Intelligence | Access |
|---|---|---|
| `SuperAdmin` | Admin | Everything, including Administration (connectors, CRA site assignments) |
| `Director` | Director | Every page, report and the Audit Trail; assigns tasks; can view any role's Overview. No Administration settings, no Data Management downloads |
| `PM` (or `ProjectManager`) | Project Manager | Studies, reports, Audit Trail; assigns study and general tasks |
| `ClinOps` | Clinical Operations | CRAs, CTAs and physics: all pages read-only plus their own tasks; Overview with sites, visits, eTMF and Data Management |
| `DataManagement` (or `DM`, `DataManager`) | Data Manager | As Clinical Operations, plus Data Management Excel downloads |
| `QA` | QA | SOPs and quality; assigns SOP, vendor, system and general tasks; Audit Trail |
| no role | Viewer | Read-only |

To use another Value, add it to `ENTRA_ROLE_MAP` in `.env` (JSON), for example
`ENTRA_ROLE_MAP={"Physicist": "clinical_operations"}`. Our own names (`admin`, `director`, `project_manager`,
`clinical_operations`, `data_manager`, `qa`, `cra`, `cta`, `safety`, `business_development`, `viewer`) always work.

When the app moves off a laptop to a proper web address, add that address as another SPA redirect URI in
step 1.
