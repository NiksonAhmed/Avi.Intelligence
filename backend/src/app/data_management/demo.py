"""Demo Viedoc export, used when no Viedoc connection is configured. Clearly labelled demo everywhere.

Built in Viedoc's own export format (zip of CSVs, a header row followed by a row of column IDs), so the
same reader is exercised. Dates are relative to the app's today. All sites, subjects and queries are
fictional.
"""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import date, datetime, timedelta

from app.studies.clock import today as app_today

from .export_reader import PENDING_COLUMNS, QUERY_COLUMNS, REVIEW_COLUMNS, SDV_COLUMNS

STUDY_CODE = "DEMO_DM"
_SITES = [("101", "Demo Hospital North"), ("102", "Demo Cancer Centre"), ("201", "Demo Clinic Auckland")]
_FORMS = [
    ("LBCC", "Clinical chemistry", "LBORRES_ALT", "ALT result", "LB_RANGE_ALT"),
    ("VS", "Vital signs", "VSORRES_SYSBP", "BP sys (mmHg) result", "VS_RANGE_SYSBP"),
    ("EG", "ECG", "EGORRES_QRS", "QRS interval", "EG_RANGE_QRS"),
    ("AE", "Adverse events", "AESTDAT", "Start date", "AE_DATE_CHECK"),
]
_EVENTS = [("E01_SCR", "Screening"), ("E03_D1", "Day 1"), ("E07_D7", "Day 7")]

# (site index, subject number, form index, event index, history), history = (state, days ago, role)
_QUERIES: list[tuple[int, int, int, int, list[tuple[str, int, str]]]] = [
    (0, 1, 0, 0, [("Query Raised", 2, "")]),
    (0, 1, 1, 1, [("Query Raised", 9, "")]),
    (0, 2, 2, 1, [("Query Raised", 12, ""), ("Query Resolved", 8, "Study Coordinator")]),
    (0, 3, 0, 2, [("Query Raised", 20, ""), ("Query Resolved", 15, "Study Coordinator"),
                  ("Query Closed", 14, "")]),
    (0, 3, 2, 2, [("Query Raised", 6, ""), ("Query Resolved", 3, "Study Coordinator")]),
    (1, 1, 2, 0, [("Query Raised", 40, "")]),
    (1, 1, 2, 1, [("Query Raised", 35, "")]),
    (1, 2, 2, 1, [("Query Raised", 18, ""), ("Query Resolved", 16, "Study Coordinator"),
                  ("Query Raised", 10, "Data Manager"), ("Query Resolved", 4, "Study Coordinator")]),
    (1, 2, 1, 2, [("Query Raised", 7, ""), ("Query Resolved", 6, "Study Coordinator")]),
    (1, 3, 3, 1, [("Query Raised", 25, ""), ("Query Closed", 22, "")]),
    (1, 4, 0, 0, [("Query Raised", 5, "")]),
    (2, 1, 0, 1, [("Query Raised", 3, ""), ("Query Resolved", 1, "Study Coordinator")]),
    (2, 2, 1, 1, [("Query Raised", 14, "")]),
    (2, 2, 2, 2, [("Query Raised", 11, ""), ("Query Resolved", 9, "Study Coordinator"),
                  ("Query Closed", 8, "")]),
]  # fmt: skip
# (site index, subject number, form index, event index) of unconfirmed missing data
_MISSING = [(0, 1, 0, 1), (0, 2, 0, 1), (0, 2, 1, 2), (1, 1, 0, 0), (1, 2, 0, 1), (1, 3, 1, 1), (1, 4, 2, 0),
            (2, 1, 1, 1), (2, 2, 0, 2)]  # fmt: skip
# (site index, subject number, form index, event index, days pending)
_PENDING = [(0, 3, 1, 2, 4), (1, 1, 0, 2, 21), (1, 4, 1, 1, 9), (1, 4, 2, 1, 9), (2, 2, 3, 2, 2)]


# SDV demo: subjects per site, two visits, three forms (fields needing SDV) plus each visit date.
_SDV_SUBJECTS = {0: [1, 2, 3], 1: [1, 2, 3, 4], 2: [1, 2]}
_SDV_VISITS = [("E01_SCR", "Screening", 60), ("E03_D1", "Day 1", 30)]
_SDV_FORMS = [("VS", "Vital signs", 6), ("EG", "ECG", 5), ("LBCC", "Clinical chemistry", 8)]


def _sdv_done(site: int, subject: int, visit: int, fields: int) -> int:
    """Site 101: screening fully verified, Day 1 half; site 102: screening for subjects 1-2; 201: none."""
    if site == 0:
        return fields if visit == 0 else fields // 2
    if site == 1 and visit == 0 and subject <= 2:
        return fields
    return 0


def _subject(site: int, n: int) -> str:
    return f"{_SITES[site][0]}-{n:03d}"


def _stamp(base: date, days_ago: int) -> str:
    moment = datetime(base.year, base.month, base.day, 9, 30) - timedelta(days=days_ago)
    return moment.strftime("%Y-%m-%d %H:%M")


def _csv(columns: list[str], rows: list[dict[str, str]]) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=columns)
    writer.writeheader()
    writer.writerow(
        {c: c.replace(" ", "").replace("&", "").replace("(", "").replace(")", "") for c in columns}
    )
    writer.writerows(rows)
    return out.getvalue().encode("utf-8-sig")


def demo_export(today: date | None = None) -> bytes:
    t = today or app_today()
    qc = QUERY_COLUMNS
    query_rows: list[dict[str, str]] = []
    for number, (s, n, f, e, history) in enumerate(_QUERIES, start=1):
        form_id, form_name, item_id, item_label, check = _FORMS[f]
        for state, days_ago, role in history:
            query_rows.append(
                {
                    qc["number"]: str(number),
                    qc["site_name"]: _SITES[s][1],
                    qc["site_code"]: _SITES[s][0],
                    qc["subject_id"]: _subject(s, n),
                    qc["event_id"]: _EVENTS[e][0],
                    qc["event_name"]: _EVENTS[e][1],
                    qc["form_id"]: form_id,
                    qc["form_name"]: form_name,
                    qc["item_id"]: item_id,
                    qc["item_label"]: item_label,
                    qc["raised_on"]: "Item",
                    qc["query_type"]: "Validation",
                    qc["edit_check"]: check,
                    qc["query_text"]: f"Demo: please check the {item_label.lower()}.",
                    qc["state"]: state,
                    qc["resolution"]: "Demo answer" if state == "Query Resolved" else "",
                    qc["user_name"]: "Demo Coordinator"
                    if role == "Study Coordinator"
                    else ("Demo DM" if role else ""),
                    qc["at"]: _stamp(t, days_ago),
                    qc["user_role"]: role,
                }
            )
    for s, n, f, e in _MISSING:
        form_id, form_name, item_id, item_label, _check = _FORMS[f]
        query_rows.append(
            {
                qc["site_name"]: _SITES[s][1],
                qc["site_code"]: _SITES[s][0],
                qc["subject_id"]: _subject(s, n),
                qc["event_id"]: _EVENTS[e][0],
                qc["event_name"]: _EVENTS[e][1],
                qc["form_id"]: form_id,
                qc["form_name"]: form_name,
                qc["item_id"]: item_id,
                qc["item_label"]: item_label,
                qc["query_type"]: "Unconfirmed missing data",
            }
        )
    pc = PENDING_COLUMNS
    pending_rows = [
        {
            pc["site_name"]: _SITES[s][1],
            pc["site_code"]: _SITES[s][0],
            pc["subject_id"]: _subject(s, n),
            pc["event_id"]: _EVENTS[e][0],
            pc["event_name"]: _EVENTS[e][1],
            pc["form_id"]: _FORMS[f][0],
            pc["form_name"]: _FORMS[f][1],
            pc["pending_since"]: _stamp(t, days),
        }
        for s, n, f, e, days in _PENDING
    ]
    sdv_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []
    sc, rc = SDV_COLUMNS, REVIEW_COLUMNS
    for s, subjects in _SDV_SUBJECTS.items():
        for n in subjects:
            for v, (event_id, event_name, days_ago) in enumerate(_SDV_VISITS):
                visit_date = (t - timedelta(days=days_ago)).isoformat()
                base = {
                    sc["site_name"]: _SITES[s][1],
                    sc["site_code"]: _SITES[s][0],
                    sc["subject_id"]: _subject(s, n),
                    sc["event_seq"]: str(v + 1),
                    sc["event_id"]: event_id,
                    sc["event_name"]: event_name,
                    sc["event_date"]: visit_date,
                }
                parts: list[tuple[str | None, str | None, int, str]] = [
                    (None, None, 1, "Event date"),
                    *[(f, nm, k, "Item") for f, nm, k in _SDV_FORMS],
                ]
                for seq, (sdv_form, sdv_form_name, fields, reviewed) in enumerate(parts):
                    done = (
                        _sdv_done(s, n, v, fields) if sdv_form else (1 if _sdv_done(s, n, v, 2) == 2 else 0)
                    )
                    form = {
                        **base,
                        sc["form_id"]: sdv_form or "",
                        sc["form_name"]: sdv_form_name or "",
                        sc["form_seq"]: str(seq) if sdv_form else "",
                    }
                    for i in range(fields):
                        verified = i < done
                        sdv_rows.append(
                            {
                                **form,
                                "Item Id": f"{sdv_form or 'EVENTDATE'}_{i + 1}",
                                sc["reviewed_item"]: reviewed,
                                sc["sdv_by"]: "Demo CRA" if verified else "",
                                sc["sdv_at"]: _stamp(t, days_ago - 5) if verified else "",
                            }
                        )
                    complete = done == fields
                    review_rows.append(
                        {
                            **form,
                            rc["reviewed_item"]: "Form" if sdv_form else "Event date",
                            rc["data_by"]: "Demo DM" if complete else "",
                            rc["data_at"]: _stamp(t, days_ago - 6) if complete else "",
                            rc["sdv_by"]: "Demo CRA" if complete else "",
                            rc["sdv_at"]: _stamp(t, days_ago - 5) if complete else "",
                            rc["signed_by"]: "Demo Investigator" if complete and s == 0 else "",
                            rc["signed_at"]: _stamp(t, days_ago - 7) if complete and s == 0 else "",
                            rc["lock_by"]: "Demo DM" if complete and s == 0 and n == 1 else "",
                            rc["lock_at"]: _stamp(t, days_ago - 8) if complete and s == 0 and n == 1 else "",
                        }
                    )
    stamp = datetime(t.year, t.month, t.day).strftime("%Y%m%d_%H%M%S")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr(f"{STUDY_CODE}_{stamp}_Queries.csv", _csv(list(qc.values()), query_rows))
        archive.writestr(f"{STUDY_CODE}_{stamp}_Pending_forms.csv", _csv(list(pc.values()), pending_rows))
        archive.writestr(f"{STUDY_CODE}_{stamp}_SDV.csv", _csv([*SDV_COLUMNS.values(), "Item Id"], sdv_rows))
        archive.writestr(
            f"{STUDY_CODE}_{stamp}_Review_status.csv", _csv(list(REVIEW_COLUMNS.values()), review_rows)
        )
        archive.writestr(f"{STUDY_CODE}_{stamp}_README.txt", b"Demo export: fictional data.")
    return buf.getvalue()
