"""Ask Avi.Intelligence about Data Management (queries, missing data, SDV, labs), by fixed rules.

Answered from the module's own views for the default study scope: counts and per-site figures only. No
subject IDs are shown here (open Data Management for the detail) and no EDC data is ever sent to AI.
Answers only while the module is switched on and to people who may view it.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.assistant import topics
from app.assistant.study_questions import AnswerTable, SourceLink, StudyAnswer
from app.auth.rbac import CurrentUser, Permission
from app.core.config import get_settings

from .api import overview as dm_overview
from .checks_api import labs_view, missing_view

WORDS = frozenset(
    {"query", "queries", "sdv", "lab", "labs", "edc", "viedoc", "crf", "crfs", "ecrf", "ecrfs", "verified",
     "verification"}
)  # fmt: skip
PHRASES = (
    "data management", "missing data", "missing fields", "missing pages", "missing forms", "pending forms",
    "source data", "out of range", "clinically significant", "lab results", "data cleaning",
)  # fmt: skip
LINK = "/data-management"
NOTE = (
    "Worked out by Avi.Intelligence from its read-only copy of Viedoc, by the same rules as the Data "
    "Management tab. Counts and sites only: open Data Management for subject-level detail. No EDC data is "
    "sent to AI."
)


def _sub(q: str, words: set[str]) -> str:
    if words & {"sdv", "verified", "verification"} or "source data" in q:
        return "sdv"
    if words & {"lab", "labs"} or "out of range" in q or "clinically significant" in q:
        return "labs"
    if "missing" in words or "pending forms" in q:
        return "missing"
    if words & {"query", "queries"}:
        return "queries"
    return "summary"


async def answer(db: Session, user: CurrentUser, question: str) -> StudyAnswer | None:
    settings = get_settings()
    if not settings.data_management_enabled or not user.can(Permission.DM_VIEW):
        return None
    q = " ".join(question.lower().split())
    words = topics.words_of(q)
    sub = _sub(q, words)
    ov = await dm_overview(db, user, settings, scope=None)
    tiles = {t.key: t for t in ov.tiles}
    opened, awaiting = tiles["open_at_site"].value, tiles["awaiting_approval"].value
    sdv_pct = round(ov.sdv.percent or 0)
    tables: list[AnswerTable] = []
    lines: list[str] = []

    def site_table(title: str, columns: list[str], rows: list[list[str]], tab: str) -> AnswerTable:
        return AnswerTable(
            title=title, columns=columns, rows=rows[:25], links=[f"{LINK}?tab={tab}"] * min(len(rows), 25),
            more=max(0, len(rows) - 25),
        )  # fmt: skip

    if sub == "queries":
        head = (
            f"{opened} queries open at sites, {awaiting} answered and awaiting review, "
            f"{tiles['closed_30'].value} closed in the last 30 days."
        )
        tables.append(
            site_table(
                "Queries by site (most overdue first)",
                ["Site", "Open at site", "Awaiting review", "Overdue", "Oldest (days)"],
                [[f"{s.site_code} · {s.site_name}", str(s.open_at_site), str(s.awaiting_approval),
                  str(s.overdue), "—" if s.oldest_days is None else str(s.oldest_days)]
                 for s in ov.sites],
                "queries",
            )
        )  # fmt: skip
        understood = "Data Management · queries"
    elif sub == "missing":
        m = await missing_view(
            db, user, settings, scope=None, study=None, view="fields", site=None, form=None, visit=None,
            since_from=None, since_to=None, search=None, limit=1, offset=0,
        )  # fmt: skip
        mt = {t.key: t for t in m.tiles}
        head = (
            f"{mt['fields'].value:,} missing fields ({mt['overdue'].value:,} overdue), "
            f"{mt['pending'].value:,} pending forms and {mt['upgrades'].value:,} forms awaiting upgrade."
        )
        tables.append(
            site_table(
                "Missing data and pending forms by site",
                ["Site", "Missing", "Pending forms"],
                [
                    [f"{s.site_code} · {s.site_name}", str(s.missing_items), str(s.pending_forms)]
                    for s in ov.sites
                ],
                "missing",
            )
        )
        understood = "Data Management · missing data"
    elif sub == "sdv":
        pct = f"{round(ov.sdv.percent or 0)}%"
        head = (
            f"SDV {pct} complete: {ov.sdv.done:,} of {ov.sdv.required:,} fields verified; "
            f"{ov.sdv.forms_complete:,} of {ov.sdv.forms_total:,} forms fully verified."
        )
        tables.append(
            site_table(
                "SDV by site",
                ["Site", "Fields verified", "Fields needing SDV"],
                [[f"{s.site_code} · {s.site_name}", str(s.sdv_done), str(s.sdv_required)] for s in ov.sites],
                "sdv",
            )
        )
        understood = "Data Management · SDV"
    elif sub == "labs":
        labs = await labs_view(
            db, user, settings, scope=None, study=None, view="flagged", site=None, form=None, visit=None,
            analyte=None, visit_from=None, visit_to=None, search=None, limit=1, offset=0,
        )  # fmt: skip
        lt = {t.key: t for t in labs.tiles}
        head = (
            f"{lt['out_of_range'].value} lab results out of range, "
            f"{lt['clin_sig'].value} clinically significant, {lt['checks'].value} to check with the site; "
            f"{lt['reported'].value}% of results reported."
        )
        lines.append("Flags only: Avi.Intelligence does not copy lab values.")
        understood = "Data Management · labs"
    else:
        head = (
            f"{opened} open queries, {awaiting} awaiting review, "
            f"{tiles['missing_items'].value:,} unconfirmed missing data, SDV {sdv_pct}% complete."
        )
        understood = "Data Management · overview"
    scope = ov.study_code or ("all studies" if ov.multi else ov.scope)
    lines.append(f"Study: {scope} ({ov.environment}).")
    return StudyAnswer(
        intent=f"dm_{sub}",
        understood=f"{understood} · {scope}",
        headline=head,
        lines=lines,
        tables=tables,
        sources=[SourceLink(label="Data Management", url=LINK if sub == "summary" else f"{LINK}?tab={sub}")],
        as_of=ov.as_of,
        sandbox_only=ov.environment != "live",
        follow_ups=[
            "How many queries are open?",
            "What is our SDV progress?",
            "Any clinically significant labs?",
        ],
        note=NOTE,
    )


topics.register(topics.Topic("data_management", WORDS, PHRASES, answer))
