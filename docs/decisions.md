# Decisions and assumptions

A running log of design decisions, assumptions and known limitations. Newest first.

## 2026-11-24: Conferences read from the BD document library (Excel schedules)

**Decisions (user, 24 Nov 2026):** the Conferences page reads the BD team's workbooks in the "Conferences"
library on the Avion Business Development Activities site (read-only Sites.Selected grant for the
Avi.Intelligence app, made 24 Nov). Set `CONFERENCES_SHAREPOINT_LIBRARY=Conferences` and
`CONFERENCES_SHAREPOINT_SITE_URL` to the BD site; the list reader stays for later.
- **Newest per half:** in each "Conferences YYYY" folder, Excel files are grouped as H1, H2 or the whole year
  from their names, and the newest of each is read. Files without "Budget" in the name come first, so the older
  "Schedule & Budget_H1_2027" never brings back the two conferences dropped in "H1 2027_Revised_V2".
- **2026 included:** its only workbooks are "Schedule & Budget" files; their "Conference Schedule" and
  "Conference Budget" sheets are combined (website and registration from one, gov support and reason from the
  other). No priority or attendees for most of 2026, because those sheets do not record them.
- **Only sheets named "Conference ..."** are read: never the per-conference cost sheets, "Suggested ..."
  sheets or planning sheets. Any column whose header says budget or cost is dropped before reading.
- The same conference written two ways (same name in the year, or same start date and city) is shown once.
  Rows without a name or a readable date (totals, footnotes) are skipped.
- Cities added: Phoenix, Salt Lake City, and "Taipai" (as spelled in a schedule). "California" and "Taiwan"
  alone stay "not on the map" rather than guessing a city.

## 2026-11-24: Conferences follow the BD schedules (priority, people, clashes; never budget)

**Decisions (user, 24 Nov 2026):** the Conferences page keeps its layout and glowing world map, and shows what
the BD team's schedules hold. BD keeps one list per year in SharePoint (folders "Conferences 2026" and
"Conferences 2027"); the API connection comes next.
- **Priority 1 / 2 / 3** (green, yellow, orange as in the schedules) replaces "Avion's role" (Exhibiting,
  Speaking, ...), which the schedules do not have: pins, chips, the Priority 1 tile and the Excel export.
- **Who is going** (initials, e.g. "MM (JB)"), **tags** from the comment (BIO Partnering, AUS Delegate),
  **government support / trade mission** (its own column or named in the comment), **registration** as
  written ("EBR to 30 Jan") with the deadline read from it, **website**, and the **reason** (why go).
- **Date clashes are found from the dates** (no more orange writing): overlapping conferences in the year,
  "booked twice" when the same person goes to both. A tile, a card, a "!" on the map label and a note in the
  table; clashes are worked out over the whole year whatever the filters.
- **Budget is never read or shown** (the 16 Nov decision stands): the reader has no budget field at all, so
  "Budget AUD" and the Grand Totals are ignored.
- Text dates like "7-10 Jan", "29 Apr - 01 May" need the schedule's year (from its folder or file); without it
  they are not guessed. Registration "Feb-26" means the end of February 2026; "TBD/TBA" is no date.
- Cities added to the map table: Chantilly, Belfast, Canberra, Cologne, Gold Coast.
- Demo conferences stay fictional (initials AB, CD, EF are no one's) until the lists are connected.

## 2026-11-24: SimpleTrials test studies are left out (Workspace key)

**Decision (user, 24 Nov 2026):** with the Workspace (all studies) key, the test studies "Sandbox Study" and
"TC 01 EC 01" are hidden, not shown marked as test. `SIMPLETRIALS_EXCLUDED_STUDIES` (numbers or names,
comma-separated, any capitals) is checked before anything else about a study is read, so none of their sites,
tasks, documents, deviations or visits are fetched or stored, which also spares the API rate limit. Studies
stored before the exclusion are hidden from the Portfolio and their pages (404). The next sync marks them no
longer in SimpleTrials, which Reports, Overview, Work and Ask already leave out. Sandbox testing still works
with the Sandbox study key and an empty list.

## 2026-11-23: Site validation shows the sites' own survey answers (until physics' record is connected)

**Decisions (user, 23 Nov 2026):** until Avion physics' own validation record (dates, certificates, phantom
scans) is found and connected, Site validation reads the same Site Feasibility Tracker as Site feasibility
(one shared download, `TrackerDownload`) and shows each site's latest survey answers, clearly labelled.
- Source order: the three SharePoint lists when `SITE_VALIDATION_SITES_LIST` is set; otherwise the tracker's
  survey answers when the tracker is connected; otherwise demo sites. `SITE_VALIDATION_MODE=mock` = demo.
- Read from the Feasibility sheet's imaging sections: equipment on site (PET/CT, SPECT/CT, dose calibrators,
  gamma counter: manufacturer, model, installation, last calibration, maintenance), "calibrated (by ARTnet)
  for <isotope>?" answers with any certification date and certificate/files answer, phantom availability,
  QA/QC routines, PACS, DICOM export and transfer methods. Licensed isotopes, ARTnet accreditation and the
  radiopharmacy come from the same answers Site feasibility uses. Contacts are never read.
- New status **"Calibrated (site's answer)"** (blue ✓): never due, overdue or files missing, even with a date,
  because physics has not checked it. A blue banner says the answers are the sites' own.
- **Tiles from what the tracker holds** (user, 23 Nov: the tracker gains rows, not new columns): sites
  reporting a calibration; ARTnet accredited; PET/CT or SPECT/CT on site (or the filtered equipment);
  phantoms listed; answers over 12 months old (amber, same rule as Site feasibility's survey due). Review
  dates, files missing and phantom-scan tiles return only with physics' own record. Phantom details stay in
  each site panel and on the map.
- First read of the real file (counts only): 31 sites (same ids as Site feasibility); equipment on site:
  15 dose calibrators, 10 PET/CT, 9 SPECT/CT, 9 gamma counters; 8 calibrations reported at 5 sites (most
  answers are "No" or "Not known"); 1 with a date; 7 sites list phantoms.

## 2026-11-23: Avion's Entra roles

**Decisions (user, 23 Nov 2026):** Avion created app roles in Entra with its own names, kept as they are;
the app translates them (`DEFAULT_ROLE_MAP` in `app/auth/entra.py`, more via `ENTRA_ROLE_MAP` in `.env`):
`SuperAdmin` -> Admin (the developer, full access); `Director` -> **Director** (new role: everything and the
audit trail, assigns tasks, may view any role's Overview, but no Administration settings); `ClinOps` ->
**Clinical Operations** (new role for CRAs, CTAs and physics: same permissions as CRA/CTA, Overview with
sites, visits, eTMF, Data Management, risks and SOPs); `DataManagement` (also `DM`/`DataManager`) -> Data Manager (its own Entra role);
`QA` -> QA; `PM`/`ProjectManager` -> Project Manager. No role -> Viewer.
- Director does **not** get Data Management downloads: the 2026-11-12 rule (Admin and Data Manager only)
  stands unless the user changes it.

## 2026-11-23: Site feasibility reads the tracker workbook in SharePoint

**Decisions (user, 23 Nov 2026):**
- The Site Feasibility Tracker stays an Excel workbook in SharePoint (folder "Site Feasibility Questionnaire
  Template"); the team keeps editing it. No conversion to SharePoint lists. The app downloads it read-only
  with the existing SharePoint app credentials (the app already had read access to that site; checked
  23 Nov) and reads two sheets: **Feasibility** (one row per site survey) and **Post-Activation _ DRAFT**
  (one row per project). Switched on by `SITE_FEASIBILITY_DRIVE_ID` and `SITE_FEASIBILITY_ITEM_ID` in
  `.env`; blank = demo sites. Refreshed every `SHAREPOINT_CACHE_MINUTES` and by the page's Refresh button.
- **The "Validation" sheet is not site validation**: it holds the dropdown options for the Feasibility sheet
  (Country, State, Survey Type, Manufacturer, ...). Site validation (validated dates, expiry, phantom scans)
  is not in this workbook; its source is still to be found (likely the physics work tracker).
- The hidden **Contacts** sheet is never read.

**How the workbook is read:**
- Columns are found by header wording (row with "Name of Site"; the section row above it), so inserting or
  moving columns does not break anything. The template's own spellings are handled ("117Lu" means 177Lu,
  "myelofribrosis").
- Answers starting with Yes/No become "Yes"/"No"; other answers stay as written ("Not applicable"). For the
  recommendation, "Not known" / "Unknown" / "TBC" count as not answered (Not assessed), not as "No".
- Weeks like "12-14" become 13; dates as Excel dates or dd/mm/yyyy, "Jun 2025".
- One site (name + department) with several surveys: the latest survey is shown.
- Map pin: a city named in the address (built-in table), else the middle of the state. No online geocoding.
- Post-Activation rows join their site by name + department (or by name when it is unique); actual
  enrolment is the sum of the "What was the actual enrolment" columns; assessment scores are capped at each
  criterion's maximum, and the lowest (latest) assessed project's scores are shown.
- First read of the real file (counts only): 31 sites, 1 older survey folded in, 26 projects joined, 5
  Post-Activation rows not matched to a Feasibility site (names differ), no assessment scores filled in yet.
- Tests use a made-up workbook with the tracker's header wording; they never read the real file.

## 2026-11-19: Microsoft sign-in (Entra ID), starting with one role

**Decisions (user, 19 Nov 2026):**
- **Single sign-on with Microsoft Entra ID**, switched on by `ENTRA_TENANT_ID` and `ENTRA_CLIENT_ID` in `.env`
  (neither is secret). Blank = the development sign-in as before; production still refuses requests without
  sign-in. Setup guide for the Entra admin: `docs/entra-setup.md`.
- **Roles are app roles on the Avi.Intelligence app registration only**, so nothing else in Avion's Microsoft
  setup changes (Avion has no roles defined in Microsoft today). The role values match ours (`admin`,
  `project_manager`, ...). **First trial: Admin only**, assigned to one person. **Anyone at Avion who signs in
  without a role is a Viewer** ("Assignment required" stays off), matching "all Avion employees may view".
  Several roles: the one with the most access wins.
- Admin guidance: assign roles to people directly or to groups made for this app only (never add people to a
  group that grants other access); no tenant-wide changes; only `User.Read` plus the app's own
  `access_as_user` scope.

**How it works:** the website signs in with MSAL (redirect), then sends its access token for this app once to
`POST /api/v1/auth/session`. The backend checks it against Microsoft's signing keys (tenant, audience, issuer,
expiry, and that it is a person's delegated token) and keeps it in an HttpOnly, SameSite=Strict cookie on
`/api`, so plain download links (Excel exports, SOPs) work unchanged. Nothing is stored server-side; the
cookie expires with the token and the website renews it every 30 minutes (and once on a 401). A fresh
sign-in is audited (`user.signed_in`); renewals are not. `DELETE /auth/session` signs out. Tests and browser
tests never contact Microsoft (test signing key; Entra blanked in both).

**Not yet:** per-person "My studies" and task assignment to Entra people (the demo directory still lists the
people tasks can be assigned to); hosting beyond a laptop.

## 2026-11-18: Site feasibility page; Study Portfolio is the one list of studies

**Decisions (user, 18 Nov 2026):**
- **Site feasibility** (`/site-feasibility`, Sites group, first): can a site run our studies? Built from the
  tracker's Feasibility sheet (site details and recommendation, predicted timelines, experience by indication,
  IP readiness, general equipment, administrative turnaround) and its Post-Activation sheet (projects,
  enrolment against prediction, the Overall Site Assessment score, maximum 40). **All Avion employees may
  view** (permission `site_feasibility.view`, every role). Demo data until the tracker is in SharePoint; the
  feasibility lists are connected with the other Microsoft connections after sign-in.
- **Split with Site validation:** the tracker's detailed imaging sections (PET/CT, SPECT/CT, CT, MRI, dose
  calibrators, gamma counter, phantoms and QA/QC, image transfer) are only 4–12% filled on the Feasibility
  sheet and stay on Site validation. (Corrected 2026-11-23: the workbook's "Validation" sheet holds only
  the dropdown options, not site validations; see the 2026-11-23 entry.) Shared fields (licensed
  isotopes, ARTnet) appear on both. The same site on both pages is matched by name, and the feasibility panel
  links to it ("Open on Site validation").
- Recommendation (diagnostics and/or therapeutics) colours the map; a survey over 12 months old pulses.
  Unanswered questions show "Not answered", and each site shows how much of its survey is answered.
- Per-study IP questions in the tracker ("[Insert Study IP]", named products) are not modelled yet; they
  belong with per-study qualifications.
- **Study Command Centre has no menu item.** Its study picker repeated the Study Portfolio; the Portfolio is
  the one list and opens a study's Command Centre. `/command-centre` redirects to `/portfolio`; the
  breadcrumb reads Study Portfolio › protocol.

## 2026-11-18: One Risks and Issues view; charts first in every report; Sites menu group

**Decisions (user, 18 Nov 2026):**
- **Risks and Issues has no page of its own.** It repeated the Reports tab. The menu item is gone;
  `/risks` (old links, bookmarks) opens Reports → Risks and issues, and the Overview card and Ask
  Avi.Intelligence answers link there. Study Command Centre keeps its per-study list.
- **Charts first, long lists folded, on every report tab.** The breakdown charts always show; the full
  lists sit under "More detail" (a tile still opens the fold and scrolls to it; the PDF prints everything).
  Risks and issues and Deviations: priority/severity, category and age shown, the full list folded.
  Study delivery: milestone timeline and site activation shown, the sites table folded. Work management:
  tasks by study shown, overdue tasks folded. eTMF: completeness by site and TMF section and QC status
  shown; expiring documents and filing timeliness folded. Quality: review schedule and change log folded.
- **Menu.** A new **Sites** group holds Site validation, which is about sites across all studies, not one
  study. Later site feasibility work joins it. Studies is ordered widest view first: Reports and Insights,
  Study Portfolio, Study Command Centre (later folded into the Portfolio), Data Management. Group order stays Studies, Sites, Knowledge,
  Business, Admin: Business has one occasional item and most staff never use it; revisit (perhaps a
  role-based order) if Business grows.

## 2026-11-17: Site validation status (physics request), demo data first

**Decision (user, 17 Nov 2026):** a graphical, site-based view of each site's validation status and
capabilities: equipment (PET/CT, SPECT/CT, dose calibrator, gamma counter), isotope validations and phantoms.
Click a site on a big map of Australia and its capabilities pop up. A front end to the site validation
tracker plus the physics phantom status, which should be site-based. Everyone may view. Demo data until the
tracker is in SharePoint. Mock-up: https://claude.ai/artifact/6v46oTbdBtEHbskDtySwL7 (third row).
- **Menu:** Sites → Site validation (`/site-validation`; moved from Studies on 18 Nov), permission `site_validation.view` (all roles).
- **Source:** `app/site_validation/`. Fields follow the Site Feasibility Tracker's sections: Site Details,
  Equipment, PET/CT, SPECT/CT, Dose Calibrator (PET and SPECT), Gamma Counter System, Phantoms and QA/QC,
  Image Data Storage and Transfer, plus isotope licences (IP). Its "117Lu" is read as 177Lu.
- **Rules:** next review is the date the physicist or core lab gave, otherwise 12 months after validation.
  Overdue: the date has passed. Files missing: validated but the certificate is not on file. Due soon: within
  60 days. Booked: a phantom scan is booked and nothing is validated yet. A pin's colour is the site's worst
  status for the filters chosen; sites needing attention pulse.
- **Site panel:** facts, an equipment × isotope grid with a "Licensed for" row, scanner details (installed,
  last calibration, maintenance, replacement plans), phantoms and QA/QC, phantom scans, image transfer.
- **Map:** drawn from approximate coastline points (no map service), styled like the Conferences map.
- **SharePoint connector (user decision 17 Nov 2026: "SharePoint"):** three lists (Sites, Validations,
  Phantom scans), read-only through Microsoft Graph like Conferences; demo sites until
  `SITE_VALIDATION_SITES_LIST` is set. Columns and setup: docs/site-validation-setup.md. Administration →
  Connectors has a card with the lists, what was read, rows it could not use and a Test connection button.
  Pins come from Latitude/Longitude columns, else a built-in table of Australian cities, else the middle of
  the state. Each city tag on the map also shows how many phantoms the site has.
- **Not yet:** the physics work tracker's phantom scan columns (statuses are a placeholder: Booked → Scanned
  → Submitted to core lab → Passed / Failed); the rest of the feasibility tracker (experience, IP,
  administrative, post-activation, scoring) is a later stage. The tracker is marked sensitive: real data only
  after Microsoft sign-in.

## 2026-11-16: Reports open on a Summary; full reports behind it; new tab order

**Decision (user, 16 Nov 2026):** "too much information, we want information if someone requires it";
keep both: a lively summary for everyone (and the executive team) and the detailed reports for those who
work in them. Light theme. Mock-up: https://claude.ai/artifact/6v46oTbdBtEHbskDtySwL7 (second row).
- **Reports opens on Summary** (`GET /reports/summary`, `app/reports/summary.py`). Every figure is taken from
  the full reports, so both always agree: four cards (patients enrolled, key milestones overdue, open risks
  and issues, open deviations, each with the change since about 30 days ago), **Studies at a glance** (one
  card per study: Off track / At risk / On track with the reason), enrolment by month (new that month and
  the total, against the target), three weekly trends, a sites ring, and four rings that are true
  percentages and about studies only (eTMF complete, enrolment, sites activated, key milestones on time;
  SOP reviews and tasks on time belong to the Quality and Work tabs).
- **Study status rules:** Off track when a key milestone is overdue; otherwise At risk when a key milestone
  still to complete has slipped more than 30 days, an open issue is overdue, a major or critical deviation
  is open, or a site is late to activate; otherwise On track.
- **Detail only when asked:** clicking a card, ring or study opens a side panel (a one-line summary and up
  to six items behind the number) with **Open the full report** (that tab; a study opens Study delivery
  filtered to it). No subject numbers anywhere.
- **Tab order:** Summary, Study delivery, Risks and issues, Protocol deviations, eTMF, Quality (SOPs), Work
  management: studies first (SimpleTrials), then company-wide (SharePoint, Avi.Intelligence tasks).
- Enrolment by month and the weekly trends build up from the saved daily figures (nothing back-filled).

## 2026-11-16: Business Development role; grouped menu; Ask Avi.Intelligence on its own; no conference costs

**Decisions (user, 16 Nov 2026)**, mock-up approved: https://claude.ai/artifact/6v46oTbdBtEHbskDtySwL7.
- **Business Development role from the start** (`business_development`): conferences, SOPs, their own
  tasks, Ask Avi.Intelligence, and the **study portfolio at portfolio level only** (status, phase, sites,
  enrolment). No Study Command Centre, reports, risks and issues, deviations, eTMF, Data Management or audit
  trail. New permissions: `portfolio.read` (the portfolio list and the Overview; everyone) and `task.view`
  (My Tasks; everyone); `study.read` now means study detail. BD's Overview: Next conferences, then Study
  portfolio; its third "Needs your attention" figure is conference registrations due.
- **Conferences are edited only in SharePoint** by the BD team; Avi.Intelligence stays read-only.
- **No conference costs** ("we are not having any cost"): `conference.cost`, the cost fields, the Excel cost
  column and the cost answers are removed (supersedes 13 Nov).
- **Menu grouped** and the same order for everyone: Overview, My Tasks, Ask Avi.Intelligence; Studies
  (Portfolio, Command Centre, Risks and Issues, Reports, Data Management); Knowledge (Documents); Business
  (Conferences); Admin (Administration, Audit Trail). Each person sees only the items their role allows
  (Administration only with `connector.manage`, Audit Trail only with `audit.read`; both pages already
  refused others). Business stays below Studies: most staff never use it, and BD land on it via their
  Overview.
- **Ask Avi.Intelligence has its own page** (`/ask`; `/documents/ask` redirects) and menu item, since it
  answers about everything, not only SOPs. The top bar's SOP-only search is now one **"Search or ask
  anything"** box (Ctrl K) that opens Ask with the question. The SOP list keeps its own search.
- **Livelier reports** (same mock-up), on every tab:
  - **Headline sentence** first: what matters most (e.g. "3 major or critical deviations still open, 5 open
    in all."), worked out by fixed rules from the tile figures (`app/reports/insights.py`; no AI), with a
    short second line. No person is named in a headline.
  - **Tile trends:** each tile's figure is saved once a day (`report_snapshots`, kind `tiles:<report>`,
    last value of the day, all studies only), giving a small trend line (one point a week, up to 12 weeks)
    and the change since about 30 days ago (at least 7), green when better and red when worse. **History
    starts on 16 Nov 2026; nothing is back-filled or estimated**, so lines appear after two weeks and the
    "since" figure after a week. A filtered view (one study, site or department; Quality other than 12
    months) shows no trend. Figures are saved whenever a report or the Overview is opened.
  - **Tiles jump to their chart** (the chart or list behind the number). The existing charts stay.
  - Not done: clicking a chart bar to filter the list below (the tabs' own filters do this today).
  - **Same layout as the mock-up on every tab** (user: "looks different than the mock-up"): one-line toolbar
    (filters, a small "Demo data"/"Sandbox study" tag instead of a banner, as-of, Sync now, Excel, PDF);
    headline; tiles; **two charts side by side; one table; then "More detail" folded** (opened for the PDF
    and when a tile points into it). The rule behind each chart moved behind an ⓘ (still printed in the PDF).
  - Study delivery: **Enrolment over time** (enrolled on each saved day against the final target; SimpleTrials
    has no monthly plan, so there is no plan curve) and a **Sites** table with activation status; the
    milestone timeline and site activation are under More detail.
  - Quality: **change log trimmed** (user: "do we need so much detail of the change log?"): the count and the
    latest 5 under More detail, with "Show all"; the full log stays in Excel. Library health lists 3 names per
    check (and "N more").

## 2026-11-13: Ask Avi.Intelligence answers across the whole app

**Decision (user, 13 Nov 2026): "if I ask anything regarding conference or study or task or risk or SOP or
data management it should be able to answer".** Still no AI for anything but SOP answers (no key yet):
every other answer is worked out by fixed rules from Avi.Intelligence's own data, with links to the
records, using the same rules as the reports.
- **Order:** a question clearly about SOPs, forms or templates goes to SOP search; otherwise a module's
  topic (Conferences, Data Management) when its words match; otherwise the study questions; otherwise SOP
  search.
- **Studies (SimpleTrials):** status, what is due or behind, milestones, enrolment, activation, plus new:
  **risks and issues** (now the SimpleTrials action items; the old register was retired), **protocol
  deviations**, **eTMF** completeness and expiring documents, **upcoming site visits**. "Visit" or
  "document" alone stays an SOP question ("site initiation visit"); it is a study question only with study
  context (upcoming, monitoring, eTMF, expiring, a study or site...).
- **Tasks:** every category, not only study tasks; "my tasks" means the asker's own open tasks.
- **Conferences** (module topic): next conference, the year's list, by city or country, by Avion's role,
  registration deadlines. Demo data is said to be demo. (Costs removed on 16 Nov.)
- **Data Management** (module topic, only while the module is on and for `dm.view`): queries, missing
  data, SDV and lab flags for the default study scope, with per-site tables. **Counts and sites only: no
  subject IDs in answers** (open Data Management for subject-level detail), and no EDC data is sent to AI.
- Modules register their topics themselves (`app/assistant/topics.py`), so the assistant never imports
  them (one-way dependencies).

## 2026-11-13: Conferences (BD) page, demo data first

**Decision (user, 13 Nov 2026).** The BD team's conferences (kept in a SharePoint list) get their own
**Conferences** page, right after Overview, with a world map of where Avion is going; mock-up approved:
https://claude.ai/artifact/ErJQZ2vrCrcQJ6u34AkbJc. **Start with demo data and leave room for the real
list**: the Microsoft admin is on leave and Microsoft has an outage, so the list cannot be connected yet.
- Optional module `app/conferences/` (`CONFERENCES_ENABLED`, on by default; answers 404 when off, menu entry
  hidden). Everyone may view (`conference.view`); **costs only for `conference.cost`** (administrators, until
  a BD role exists). Read-only; nothing is written to SharePoint.
- **Demo until connected:** demo conferences (fictional names, dates relative to today) with a clear
  "Demo conferences: the BD team's SharePoint list is not connected yet" notice, on the page and on the
  Overview card.
- **Ready for the real list:** set `CONFERENCES_SHAREPOINT_LIST` (and `CONFERENCES_SHAREPOINT_SITE_URL` if it
  is not on the SOP site); the Entra app needs read access to that site. Column names are unknown, so each
  field accepts several likely names and `CONFERENCES_FIELD_MAP` names the real ones once BD confirms them.
  Not yet tried against the real list.
- **Pins are placed by city** from a built-in table of conference cities (`geo.py`); no online geocoding, so
  nothing about Avion's plans leaves the system. An unknown city is counted as "not on the map".
- Page: figures (conferences this year, countries, next conference, exhibiting or speaking, registration due
  within 30 days), year and role filters, the map (pulsing next conference; the date-order route was removed at the user's request),
  details with "Open in SharePoint", the list, Sync now, Excel (audited; cost column only for those
  allowed) and PDF. A "Next conferences" card is added to every role's Overview.
- Map outlines: Natural Earth 110m land (public domain), drawn as `frontend/src/assets/world-map.svg`.
- To decide with BD: the list's real name and columns; whether anyone besides administrators sees costs;
  reminders before registration deadlines (suggested: a task to the BD lead two weeks before).

## 2026-11-13: Role-based Overview; CRA site assignments; SimpleTrials site visits

**Decision (user, 13 Nov 2026): "This dashboard will be different depending on your role."** The
Overview (home page) is built per role; mock-up approved:
https://claude.ai/artifact/FuFzDhN7VZmfAp9rNQZPz9.
- **Everyone** gets "Needs your attention" first (their own overdue tasks, tasks due in 7 days and one
  role-specific figure, then their next tasks), when each source was last synced, and **Sync all**
  (SimpleTrials, the SharePoint SOP library and, when Data Management is on and they may sync it, each
  Viedoc study; one failure does not stop the others).
- **Sections per role** (`LAYOUT` in `app/api/overview.py`): Administrator: connectors, studies, risks and
  issues, deviations, eTMF, data management, SOPs, team tasks. Project Manager: studies, risks and issues,
  deviations, eTMF, data management, team tasks, SOPs. CRA: their sites, site visits, data management,
  risks and issues. CTA: eTMF, studies, SOPs. Data Manager: queries, missing data, labs, SDV,
  deviations. Pharmacovigilance: a "safety database not connected yet" notice (until the Avie Safety DB
  connector), lab flags, deviations, SOPs. QA: SOPs, deviations, team tasks, risks and issues. Viewer:
  studies only.
- **Every figure is taken from the existing report or module** (same rules, same numbers) and links to
  the page with the detail; nothing is estimated and no AI is used. A section that cannot load says so
  and the rest of the page still shows.
- **People with two roles:** open on their main role's page with a switch (user decision). Users have
  one role today, so the switch appears only for administrators, who may preview every role's page.
- Data Management adds its sections through a provider it registers itself
  (`app/overview/providers.py`), so the Overview never imports the module (one-way dependencies).

**CRA sites (user decision: from SimpleTrials if possible, otherwise assigned by an Admin).**
SimpleTrials' API does not say which CRA covers which site: `site_contacts` lists site staff only
(Principal Investigator, Study Coordinator), and there is no user or assignment endpoint. So
administrators assign sites to each person in **Administration → CRA site assignments**
(`site_assignments` table, keyed on the study and SimpleTrials' own site id because site rows are rebuilt
on every sync; changes audited as `site_assignment.updated`). Until a CRA has sites, their Overview shows
all sites with a notice saying so.

**SimpleTrials site visits (user decision: show upcoming monitoring visits).** `site_visits` is read with
the study sync into `study_site_visits`: site visits only (subject visits, which carry patient-level
data, are never read), active and not cancelled; kept: site, kind (Pre-study, Initiation, Routine
Monitoring Visit...), status and dates. Not kept: people, contacts, titles, notes, locations. If they
cannot be read, the study still syncs and the previous copy is kept.

## 2026-11-13: Risks and issues come only from SimpleTrials; Risks and issues dashboard; Sync now everywhere

**Decision (user, 13 Nov 2026): "we don't want to allow to create new Risk and issue, it should all be
coming from CTMS".**
- Nothing is raised, edited or status-changed in Avi.Intelligence any more: `POST /risks`, `PATCH
  /risks/{id}` and `POST /risks/{id}/status` are removed (405/404), and the "Raise risk or issue"
  buttons, the risk form and the likelihood × impact register are gone from the Risks and Issues page
  and each study's Risks and issues tab. No risks had been raised in the live database, so nothing was
  lost; the `risks` table is kept, unused, so no migration was needed.
- SimpleTrials' API has no risk register (see 12 Nov), so **its action items are the issues**. The Risks
  and Issues page lists them read-only (study filter, show closed), with Sync now and a link to the
  dashboard. "Open risks" counts on the portfolio and study pages now count open SimpleTrials action
  items.
- **Risks and issues dashboard** (Reports and Insights → Risks and issues), from the same action items:
  tiles (open, overdue, open high priority, due in 14 days, closed in 30 days with median days to
  close), by priority, by category, opened vs closed per month (12 months), ageing of open issues, sites
  (most overdue first) and the full list; study/site filters, Excel and PDF, Sync now.
- The risk heat map and "highest open risks" are removed from Work management (they read the retired
  Avi.Intelligence register); that report is now tasks only.
- **Sync now on every page fed by an API**, for every role: report tabs, Risks and Issues, Study
  Portfolio and Study Command Centre (SimpleTrials, `study.sync`), the SOP library (SharePoint; button
  renamed from "Refresh from SharePoint") and Data Management (Viedoc, already). Admin-only sync stays on
  Administration → Connectors.

**Protocol deviation field names confirmed (13 Nov, two test deviations in the sandbox).** SimpleTrials
returns `severity`/`severity_display`, `category` (empty in the sandbox), `date_deviated` (occurred),
`date_discovered` (identified; falls back to `date_entered`), `date_actioned` + `action_taken`,
`irbec_submission_status` / `irbec_submission_date`, `subject_id` / `subject_number` / `scope_display`,
`all_subjects`, `site_id` / `site_number` / `site_name`, `active`; there is **no status and no
deviation number**. So: a deviation with a Date Actioned counts as closed ("Actioned"), otherwise
"Open"; reportable comes from the IRB/EC submission status ("not required" = no). Subject numbers are
never stored, only whether a deviation is subject-level.

## 2026-11-12: SimpleTrials action items as read-only issues; protocol deviations (DM Step 4)

**What the SimpleTrials API offers (probed read-only with the sandbox study key, field names only).**
`protocol_deviations` exists but the sandbox study has none yet, so its fields are unknown. There is no
risk or issue register endpoint (16 likely names return 404). `action_items` (site/visit follow-ups),
`site_visits`, `events` and `visit_reports` exist.

**Decisions (user, 12 Nov 2026).**
- Risks and Issues pulls SimpleTrials **action items as read-only issues**, labelled "From SimpleTrials",
  next to Avi.Intelligence's own risks register (which is unchanged). They are edited only in
  SimpleTrials and refresh with the hourly SimpleTrials sync. Shown on the Risks and Issues page and on
  each study's Risks and issues tab; hidden when filtering to risks only or "Owned by me" (assignees are
  SimpleTrials users, not Avi.Intelligence people).
- Kept per action item: number, category, sub-category, priority, status, site, opened / due / closed
  dates, description, response and the assignee's display name. Not kept: user ids. **Unblinded and
  inactive items are never read** (unblinded content must not reach blinded staff). Overdue = open and
  past the due date (calendar days). If action items cannot be read, the study still syncs and the
  previous copy is kept.
- **Protocol deviations (user: "add protocol deviation pull as report dashboard"):** a **Protocol
  deviations** tab in Reports and Insights, from SimpleTrials `protocol_deviations`, synced with the
  studies (hourly; if they cannot be read the study still syncs and the previous copy is kept). Tiles
  (total, open, major or critical, per 10 enrolled subjects, median days to identify), by severity, by
  category, monthly trend by severity, ageing of open deviations, sites by rate, and the full list;
  study/site filters, Excel and PDF like the other reports.
- Kept per deviation: number, site, category, severity (normalised to Critical / Major / Minor, keeping
  SimpleTrials' wording otherwise), status, description, dates (occurred, identified, reported, closed),
  reportable to ethics, and only *whether* it concerns a subject. **No subject IDs and no people**
  (no patient-level data from SimpleTrials). Unblinded and inactive records are never read.
- **Field names are not yet verified**: the sandbox study has no deviations, so each field is read from
  SimpleTrials' usual name variants (`map_deviations`). The user adds 2–3 test deviations in the sandbox;
  then the real field names are checked (names only) and the mapping is tightened.
- First sandbox sync: 3 action items (all site 1001, Site Visit, status New), all overdue (212–287 days).

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
