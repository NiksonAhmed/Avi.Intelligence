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
Nothing is inferred beyond this; missing values stay empty.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from .models import MilestoneRecord, SiteRecord, StudyRecord


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
