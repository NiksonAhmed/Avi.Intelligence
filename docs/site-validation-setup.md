# Site validation: connecting the SharePoint lists

Avi.Intelligence reads the site validation data from **three SharePoint lists**, read-only, through
Microsoft Graph, the same way it reads the SOP library and the conferences list. Until the lists are set,
the page shows demo sites, labelled as demo data.

The tracker is marked sensitive. Connect real data only once Microsoft sign-in is in place, so each person
signs in as themselves.

## 1. Create the lists

Create them on the SOP site, or on another SharePoint site. If you use another site, also set
`SITE_VALIDATION_SHAREPOINT_SITE_URL` and give the Entra app read access to that site (Sites.Selected).

Use the column names below when you create each column. SharePoint keeps the first name you type as the
column's internal name, and the app looks for that name. If a column already exists under another name,
map it with `SITE_VALIDATION_FIELD_MAP` (see step 3). Only the columns marked *required* must be filled in;
a row without them is skipped and counted in Administration.

### List 1: Sites (one row per site)

| Column | Type | Notes |
|---|---|---|
| `Title` | Single line of text | Site name. *Required.* Validation and scan rows refer to this name. |
| `Department` | Single line of text | |
| `City` | Single line of text | Places the pin. *City or State required.* |
| `State` | Choice | NSW, VIC, QLD, SA, WA, TAS, ACT, NT (full names also work) |
| `Latitude`, `Longitude` | Number | Optional: an exact pin position. Otherwise the city, then the middle of the state. |
| `LastSurveyReturnDate` | Date | |
| `ARTnetAccreditation` | Single line of text | e.g. "Yes (64Cu, 90Y)", "Intending", "No" |
| `SitePhysicist` | Single line of text | |
| `Radiopharmacy` | Yes/No | Radiopharmacy or hot lab on site |
| `LicensedFor` | Choice (multiple) | 64Cu, 68Ga, 90Y, 177Lu, 225Ac. "Cu-64" and similar spellings also work. |
| `PETOnSite`, `SPECTOnSite`, `DoseCalibratorOnSite`, `GammaCounterOnSite` | Yes/No | Equipment on site. A manufacturer filled in also counts as on site. |
| `PETManufacturer`, `PETModel`, `PETInstalled`, `PETLastCalibration`, `PETMaintenance`, `PETReplacement` | Text, text, date, date, text, text | The same six columns for `SPECT…`, `DoseCalibrator…` and `GammaCounter…` |
| `Phantoms` | Choice (multiple) | NEMA IEC Body Phantom, ARTnet long half-life radionuclide insert, PTW Freiburg, IEC Phantom with spheres, Uniformity phantom, Water phantom, None |
| `PhantomUsedForStudyScans` | Choice | Yes / No / Not Known |
| `QAQCRecordsAccess` | Choice | Yes / No / Not Known |
| `QAQCMonthly` | Choice | Can QA/QC be submitted monthly? |
| `DailyQCStorage` | Single line of text | How daily QC data is recorded and stored |
| `QAQCRoutinePETCT`, `QAQCRoutineSPECTCT`, `QAQCRoutineCT`, `QAQCRoutineMRI` | Multiple lines of text | |
| `PACS` | Single line of text | |
| `DICOMExport` | Choice | Yes / No |
| `TransferMethods` | Choice (multiple) | sFTP, FTP, Web (https), Digital media |

### List 2: Validations (one row per equipment and isotope)

| Column | Type | Notes |
|---|---|---|
| `Site` | Lookup to Sites (Title), or text | *Required.* Must match a site name in the Sites list. |
| `Equipment` | Choice | PET/CT, SPECT/CT, Dose calibrator, Gamma counter. *Required.* |
| `Isotope` | Choice | 64Cu, 68Ga, 90Y, 177Lu, 225Ac. *Required.* |
| `ValidatedBy` | Choice | ARTnet, Core lab, Sponsor |
| `ValidatedOn` | Date | Date of certification. *Required.* |
| `FilesAvailable` | Yes/No | Certificate files on file. "No" shows as **Files missing**. |
| `NextReview` | Date | Only if the physicist or core lab gave a date; otherwise 12 months after `ValidatedOn`. |

### List 3: Phantom scans (one row per scan)

| Column | Type | Notes |
|---|---|---|
| `Site` | Lookup to Sites (Title), or text | *Required.* |
| `Study` | Single line of text | Protocol number |
| `Equipment` | Choice | as above. *Required.* |
| `Isotope` | Choice | as above. *Required.* |
| `Status` | Choice | Booked, Scanned, Submitted to core lab, Passed, Failed. *Required.* |
| `ScanDate` | Date | When it is booked for, or when the status last changed. *Required.* |

The phantom scan stages are a first version; they will follow the physics work tracker once it is reviewed.

## 2. Tell Avi.Intelligence the list names

In the server's `backend/.env` (never committed):

```
SITE_VALIDATION_SITES_LIST=Site validation - Sites
SITE_VALIDATION_VALIDATIONS_LIST=Site validation - Validations
SITE_VALIDATION_SCANS_LIST=Phantom scans
# Only if the lists are not on the SOP site:
# SITE_VALIDATION_SHAREPOINT_SITE_URL=https://avionmedical.sharepoint.com/sites/Physics
```

The SharePoint app credentials (`SHAREPOINT_TENANT_ID`, `SHAREPOINT_CLIENT_ID`, `SHAREPOINT_CLIENT_SECRET`)
are the same ones used for the SOP library. Restart the backend after changing `.env`.

## 3. If a column has a different name

Map our field to the list's column internal name (find it in the list settings, or in the column's URL):

```
SITE_VALIDATION_FIELD_MAP={"sites.city": "Suburb", "validations.validated_on": "CertDate"}
```

Field names are `sites.<field>`, `validations.<field>` and `scans.<field>`, as listed in
`backend/src/app/site_validation/sharepoint.py` (`DEFAULT_FIELDS`). An unknown field name is refused
with an error naming it.

## 4. Check it

Open **Administration → Connectors → SharePoint: site validation (physics)** and press **Test connection**.
It shows the site and list names, how many sites, validations and phantom scans were read, and any rows it
could not use (and why). The Site validation page then shows the real sites, with "Open in SharePoint" on
each site.
