"""Map SimpleTrials API records to Avi.Intelligence study records.

Field choices (verified against the Sandbox study, Nov 2026):
  * Study: number, name/description, sponsor, phase_display, status_display, actual_enrolled, and the
    enrolment target from revised_targets (when set) or original_targets. Targets are strings; "0"
    means "not set".
  * Site: number, organization_display_name, principal_investigator_full_name, status_display with
    substatus_display, and detail.site_activation_actual / subjects_enrolled_actual /
    subjects_enrolled_target. Country is the third part of `descriptor` ("1001 : Org : USA : PI").
  * Plan: every active entry of "Milestones & Tasks" (/tasks) in SimpleTrials order, as phase / task /
    milestone (see map_plan). end_date is the current plan, baseline_end_date the original plan,
    percent_complete the progress. The API has no actual completion date.
  * eTMF (/documents, metadata only): placeholder = expected but not yet filed; tmf_level and site_id;
    the section is the first folder of document_path below the study (and below "BY SITE/<site>").
    Superseded versions (another record's precursor_id) and attachments of other records
    (parent_type set, e.g. payments) are left out. File names, URLs, descriptions and user ids are
    not kept.
  * Action items (/action_items): number, category_display / subcategory_display, priority_display,
    status, site_number / site_display_name, opened_on / due_on / closed_on, description, response and
    assigned_to_display_name. Closed when closed_on is set or the status says so. Unblinded and
    inactive items are left out; user ids are not kept.
  * Protocol deviations (/protocol_deviations): NOT YET VERIFIED against a real record (the sandbox study
    had none on 12 Nov 2026), so each field is read from SimpleTrials' usual name variants (see
    map_deviations). Subject IDs and people are never kept; unblinded and inactive records are left out.
Nothing is inferred beyond this; missing values stay empty.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from .models import (
    ActionItemRecord,
    DeviationRecord,
    EtmfDocumentRecord,
    MilestoneRecord,
    SiteRecord,
    StudyRecord,
)


def as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        n = int(str(value).strip())
    except ValueError:
        return None
    return n if n >= 0 else None


def as_date(value: Any) -> date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _text(value: Any, limit: int = 255) -> str | None:
    if not isinstance(value, str):
        return None
    text: str = " ".join(value.split())
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "…"


def _target(targets: Any, key: str) -> int | None:
    if not isinstance(targets, dict):
        return None
    n = as_int(targets.get(key))
    return n or None  # "0" means no target set


def enrolment_target(study: dict[str, Any]) -> int | None:
    return _target(study.get("revised_targets"), "enrolled") or _target(
        study.get("original_targets"), "enrolled"
    )


def sponsor_name(study: dict[str, Any]) -> str | None:
    sponsor = study.get("sponsor")
    nested = None
    if isinstance(sponsor, dict):
        nested = sponsor.get("display_name") or sponsor.get("name")
    return _text(study.get("sponsor_display_name") or nested)


def country_names(study: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for c in study.get("study_countries") or []:
        name = c if isinstance(c, str) else None
        if isinstance(c, dict):
            name = next(
                (
                    c[k]
                    for k in ("country_name", "name", "display_name", "country")
                    if isinstance(c.get(k), str)
                ),
                None,
            )
        if name and name not in names:
            names.append(name)
    return names


def map_site(site: dict[str, Any]) -> SiteRecord | None:
    if site.get("active") is False or site.get("id") is None:
        return None
    raw_detail = site.get("detail")
    detail: dict[str, Any] = raw_detail if isinstance(raw_detail, dict) else {}
    status = _text(site.get("status_display"), 64)
    sub = _text(site.get("substatus_display"), 64)
    if status and sub and site.get("substatus") not in (None, "not_applicable"):
        status = f"{status} · {sub}"
    parts = [p.strip() for p in str(site.get("descriptor") or "").split(":")]
    return SiteRecord(
        external_id=str(site["id"]),
        site_number=str(site.get("number") or site["id"]),
        name=_text(site.get("organization_display_name") or site.get("display_name"), 500) or "Unnamed site",
        country=parts[2] if len(parts) >= 4 and parts[2] else None,
        principal_investigator=_text(site.get("principal_investigator_full_name")),
        status=status,
        activation_date=as_date(detail.get("site_activation_actual")),
        activation_target=as_date(detail.get("site_activation_target")),
        enrolled=as_int(detail.get("subjects_enrolled_actual", detail.get("subject_enrolled_actual"))),
        enrolment_target=as_int(detail.get("subjects_enrolled_target")) or None,
    )


# SimpleTrials' fixed codes (`system_name`) for standard study milestones. Always key milestones.
KEY_SYSTEM_CODES = frozenset(
    {
        "project_start_date",
        "first_siv",
        "fps",
        "fpi",
        "all_sites_activated",
        "lps",
        "lpi",
        "lpo",
        "project_end_date",
    }
)
_NUMBERING = re.compile(r"^\s*[\d.]+\s+")


def normalise_name(name: str) -> str:
    """'07.03 Database Hard Lock' -> 'database hard lock' (numbering and case ignored)."""
    return " ".join(_NUMBERING.sub("", name).lower().split())


def parse_key_names(setting: str | None) -> frozenset[str]:
    return frozenset(normalise_name(n) for n in (setting or "").split(";") if n.strip())


def map_plan(tasks: list[dict[str, Any]], key_names: frozenset[str] = frozenset()) -> list[MilestoneRecord]:
    """The whole "Milestones & Tasks" plan, in SimpleTrials order: phases, tasks and milestones.

    * phase: an entry that other entries belong to (has children)
    * milestone: zero duration, or carries a SimpleTrials milestone code (e.g. "fpi", even if it
      has a duration in the plan)
    * task: everything else
    """
    active = [t for t in tasks if t.get("active") is not False and t.get("id") is not None]
    ids = {t["id"] for t in active}
    names = {t["id"]: _text(t.get("name")) for t in active}
    parents = {t.get("parent_task_id") for t in active if t.get("parent_task_id") in ids}
    plan = []
    for t in active:  # list order = SimpleTrials order
        name = _text(t.get("name")) or "Unnamed"
        code = _text(t.get("system_name"), 64)
        if t["id"] in parents:
            kind = "phase"
        elif as_int(t.get("duration_value")) == 0 or code in KEY_SYSTEM_CODES:
            kind = "milestone"
        else:
            kind = "task"
        pct = as_int(t.get("percent_complete"))
        parent = t.get("parent_task_id") if t.get("parent_task_id") in ids else None
        plan.append(
            MilestoneRecord(
                external_id=str(t["id"]),
                name=name,
                kind=kind,  # type: ignore[arg-type]
                start_date=as_date(t.get("start_date")),
                baseline_start_date=as_date(t.get("baseline_start_date")),
                planned_date=as_date(t.get("end_date")),
                baseline_date=as_date(t.get("baseline_end_date")),
                percent_complete=pct if pct is not None and pct <= 100 else None,
                parent_external_id=str(parent) if parent is not None else None,
                phase=names.get(parent) if parent is not None else None,
                system_code=code,
                is_key=kind == "milestone"
                and (code in KEY_SYSTEM_CODES or normalise_name(name) in key_names),
            )
        )
    return plan


def map_study(
    study: dict[str, Any],
    sites: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    key_names: frozenset[str] = frozenset(),
) -> StudyRecord:
    number = _text(study.get("number"), 100) or f"Study {study.get('id')}"
    phase = _text(study.get("phase_display"), 24)
    return StudyRecord(
        external_id=str(study["id"]),
        protocol_number=number,
        title=_text(study.get("name"), 500) or _text(study.get("description"), 200) or number,
        sponsor=sponsor_name(study),
        phase=f"Phase {phase}" if phase else None,
        therapeutic_area=_text(study.get("study_indication") or study.get("program_name")),
        status=_text(study.get("status_display"), 64),
        countries=country_names(study),
        project_manager=None,  # not exposed as a single field by the API
        enrolment_target=enrolment_target(study),
        enrolled=as_int(study.get("actual_enrolled")),
        sandbox=bool(study.get("sandbox")),
        sites=[s for s in (map_site(x) for x in sites) if s is not None],
        milestones=map_plan(tasks, key_names),
    )


def _path_parts(path: Any) -> list[str]:
    """Folders below the study (and below "BY SITE/<site>" or "BY COUNTRY/<country>")."""
    parts = [p.strip() for p in str(path or "").split("/") if p.strip()]
    parts = parts[1:]  # the study name
    if parts and parts[0].upper().startswith("BY "):
        parts = parts[2:]
    return parts


def map_documents(docs: list[dict[str, Any]]) -> list[EtmfDocumentRecord]:
    superseded = {str(d["precursor_id"]) for d in docs if d.get("precursor_id")}
    records: list[EtmfDocumentRecord] = []
    for d in docs:
        if d.get("id") is None or d.get("active") is False or d.get("parent_type"):
            continue
        if str(d["id"]) in superseded:
            continue
        parts = _path_parts(d.get("document_path"))
        level = d.get("tmf_level") if d.get("tmf_level") in ("study", "country", "site") else None
        site = d.get("site_id")
        records.append(
            EtmfDocumentRecord(
                external_id=str(d["id"]),
                level=level or ("site" if site else "study"),
                site_external_id=str(site) if site else None,
                section=(_text(parts[0], 200) if parts else None) or "Unfiled",
                folder=_text(parts[-1], 200) if len(parts) > 1 else None,
                name=_text(d.get("common_name"), 300) or _text(d.get("title"), 300) or "Untitled document",
                filed=d.get("placeholder") is not True,
                doc_status=_text(d.get("doc_status_display") or d.get("doc_status"), 64),
                qc_status=_text(d.get("qc_status"), 64),
                qc_started_on=as_date(d.get("qc_started_at")),
                qc_ended_on=as_date(d.get("qc_ended_at")),
                created_on=as_date(d.get("created_at")),
                uploaded_on=as_date(d.get("uploaded_at")),
                document_date=as_date(d.get("signature_date")) or as_date(d.get("doc_version_on")),
                expires_on=as_date(d.get("expires_on")),
                expired=str(d.get("expiration_status") or "").lower() == "expired",
                version=_text(d.get("doc_version"), 32),
            )
        )
    return records


CLOSED_STATUSES = {"closed", "complete", "completed", "resolved", "done", "cancelled", "canceled"}


def _label(value: Any, limit: int = 64) -> str | None:
    text = _text(value, limit)
    return text.replace("_", " ").capitalize() if text and text.islower() else text


def map_action_items(items: list[dict[str, Any]]) -> list[ActionItemRecord]:
    records: list[ActionItemRecord] = []
    for a in items:
        if a.get("id") is None or a.get("active") is False or a.get("unblinded") is True:
            continue  # unblinded items must never reach blinded staff
        status = _text(a.get("status_display") or a.get("status"), 64)
        closed_on = as_date(a.get("closed_on"))
        records.append(
            ActionItemRecord(
                external_id=str(a["id"]),
                number=_text(str(a["number"]) if a.get("number") is not None else None, 32),
                category=_label(a.get("category_display") or a.get("category")),
                subcategory=_label(a.get("subcategory_display") or a.get("subcategory")),
                priority=_label(a.get("priority_display") or a.get("priority"), 32),
                status=_label(status),
                closed=closed_on is not None or (status or "").lower() in CLOSED_STATUSES,
                site_number=_text(a.get("site_number"), 64),
                site_name=_text(a.get("site_display_name"), 255),
                description=_text(a.get("description"), 2000),
                response=_text(a.get("response"), 2000),
                assignee=_text(a.get("assigned_to_display_name"), 255),
                opened_on=as_date(a.get("opened_on")) or as_date(a.get("created_at")),
                due_on=as_date(a.get("due_on")),
                closed_on=closed_on,
            )
        )
    return records


def _first(d: dict[str, Any], *keys: str) -> Any:
    """The first non-empty value among SimpleTrials' name variants for one field."""
    for key in keys:
        value = d.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def severity_label(value: Any) -> str | None:
    """Critical / Major / Minor from SimpleTrials' wording (e.g. "important", "non-important")."""
    text = _text(str(value) if value is not None and not isinstance(value, str) else value, 64)
    if not text:
        return None
    t = text.lower().replace("_", " ").replace("-", " ")
    if "critical" in t:
        return "Critical"
    if t.startswith(("non ", "not ", "minor")) or "minor" in t:
        return "Minor"
    if "major" in t or "important" in t or "significant" in t:
        return "Major"
    return text[:1].upper() + text[1:]


def _flag(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("yes", "true", "y", "1"):
        return True
    if isinstance(value, str) and value.strip().lower() in ("no", "false", "n", "0"):
        return False
    return None


def _irbec_reportable(d: dict[str, Any]) -> bool | None:
    """IRB/EC submission status: "not required" means not reportable; any other value means it is."""
    status = _first(d, "irbec_submission_status_display", "irbec_submission_status")
    if status is None:
        return True if d.get("irbec_submission_date") else None
    text = str(status).lower().replace("_", " ")
    return not ("not" in text or text in ("no", "none", "n/a", "na"))


def map_deviations(items: list[dict[str, Any]]) -> list[DeviationRecord]:
    records: list[DeviationRecord] = []
    for d in items:
        if d.get("id") is None or d.get("active") is False or d.get("unblinded") is True:
            continue
        # SimpleTrials has no deviation status: one with a Date Actioned counts as closed ("Actioned").
        closed_on = as_date(
            _first(d, "date_actioned", "closed_on", "resolved_on", "closed_at", "resolved_at", "date_closed")
        )
        status = _label(_first(d, "status_display", "status")) or ("Actioned" if closed_on else "Open")
        site = _first(d, "site_id", "study_site_id")
        number = _first(d, "number", "deviation_number", "pd_number")
        records.append(
            DeviationRecord(
                external_id=str(d["id"]),
                number=_text(str(number), 32) if number is not None else None,
                site_external_id=str(site) if site is not None else None,
                site_number=_text(_first(d, "site_number"), 64),
                site_name=_text(_first(d, "site_display_name", "site_name"), 255),
                category=_label(
                    _first(
                        d,
                        "category_display",
                        "category",
                        "deviation_type_display",
                        "deviation_type",
                        "type_display",
                        "type",
                    ),
                ),  # fmt: skip
                severity=severity_label(
                    _first(
                        d,
                        "severity_display",
                        "severity",
                        "classification_display",
                        "classification",
                        "importance_display",
                        "importance",
                        "grade",
                    ),
                ),  # fmt: skip
                status=status,
                closed=closed_on is not None or (status or "").lower() in CLOSED_STATUSES,
                description=_text(_first(d, "description", "summary", "title", "details"), 2000),
                subject_level=_first(d, "subject_id", "subject_number", "subject") is not None,
                occurred_on=as_date(
                    _first(
                        d,
                        "date_deviated",
                        "deviation_date",
                        "occurred_on",
                        "occurrence_date",
                        "date_of_deviation",
                        "event_date",
                        "start_date",
                    ),
                ),  # fmt: skip
                identified_on=as_date(
                    _first(
                        d,
                        "date_discovered",
                        "identified_on",
                        "discovered_on",
                        "identified_date",
                        "awareness_date",
                        "opened_on",
                        "date_entered",
                        "created_at",
                    ),
                ),  # fmt: skip
                reported_on=as_date(
                    _first(
                        d,
                        "irbec_submission_date",
                        "reported_on",
                        "date_reported",
                        "reported_at",
                        "submitted_on",
                    )
                ),
                closed_on=closed_on,
                reportable=_flag(_first(d, "irb_reportable", "reportable", "report_to_irb", "ec_reportable"))
                if _first(d, "irb_reportable", "reportable", "report_to_irb", "ec_reportable") is not None
                else _irbec_reportable(d),
            )
        )
    return records
