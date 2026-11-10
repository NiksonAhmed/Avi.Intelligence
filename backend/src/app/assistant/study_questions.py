"""Answers study questions without AI: recognise what is asked, run the matching look-up, write the answer.

`understand()` reads the question's key words (what is asked, which study, site, phase, time span and
milestone); `answer()` runs the look-ups in `study_tools` and writes fixed-wording sentences and tables
with links to the source records. Questions about procedures go to SOP search instead.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.studies.rules import MAJOR_SLIP_DAYS, MilestoneState, ScheduleState

from .study_tools import (
    PRIVACY_NOTE,
    PlanInput,
    PlanItem,
    SitesInput,
    StudiesInput,
    StudyData,
    StudyStatus,
    WorkInput,
    open_risks,
    open_tasks,
    plan_items,
    sites,
    studies_overview,
)

Intent = Literal["status", "due", "behind", "milestone", "enrolment", "activation", "tasks", "risks"]

DEFAULT_WINDOW_DAYS = 90
MAX_ROWS = 25
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Words that point at procedures (SOP search) rather than study data.
_STRONG_SOP = {
    "sop",
    "sops",
    "procedure",
    "procedures",
    "policy",
    "policies",
    "form",
    "forms",
    "template",
    "templates",
    "guideline",
    "guidelines",
    "guidance",
}
_WEAK_SOP = {
    "process",
    "requirement",
    "requirements",
    "responsible",
    "responsibility",
    "responsibilities",
    "steps",
    "define",
    "definition",
    "ich",
    "gcp",
    "sae",
    "rbqm",
    "train",
    "training",
    "checklist",
    "checklists",
}
_WEAK_SOP_PHRASES = ("how do", "how to", "how should", "what should", "risk-based", "risk based")
_STUDY_CONTEXT = {"study", "studies", "trial", "trials", "portfolio", "project", "projects", "protocol"}

_INTENT_WORDS: dict[Intent, tuple[str, ...]] = {
    "tasks": ("task", "tasks", "action", "actions", "to-do", "todo"),
    "risks": ("risk", "risks", "issue", "issues"),
    "enrolment": (
        "enrol",
        "enroll",
        "enrolment",
        "enrollment",
        "enrolled",
        "enrolling",
        "recruit",
        "recruitment",
        "recruiting",
        "recruited",
        "randomised",
        "randomized",
        "patients",
        "subjects",
        "participants",
    ),
    "activation": ("activated", "activation", "activate", "activations"),
    "behind": (
        "behind",
        "late",
        "overdue",
        "slipped",
        "slipping",
        "slip",
        "slips",
        "delay",
        "delayed",
        "delays",
        "falling",
        "lagging",
    ),
    "due": (
        "due",
        "upcoming",
        "coming",
        "deadline",
        "deadlines",
        "soon",
        "closing",
        "closeout",
        "close-out",
        "close",
        "closure",
        "next",
    ),
    "status": (
        "how",
        "going",
        "status",
        "update",
        "progress",
        "overview",
        "summary",
        "health",
        "doing",
        "track",
    ),
}

_PHASES: dict[str, tuple[tuple[str, ...], list[str], list[str]]] = {
    # name: (trigger words, phase words, name words)
    "close-out": (
        (
            "close",
            "closing",
            "closeout",
            "close-out",
            "closure",
            "lock",
            "lpo",
            "lplv",
            "csr",
            "archive",
            "archiving",
            "end",
        ),
        ["close"],
        [
            "last patient out",
            "lplv",
            "database lock",
            "soft lock",
            "hard lock",
            "clinical study report",
            "study end",
            "archiv",
        ],  # fmt: skip
    ),
    "start-up": (("startup", "start-up"), ["startup", "start-up", "start up"], []),
    "planning": (("planning",), ["planning"], []),
}

_ORDINALS = {"first", "last", "final"}
_TIMING_WORDS = {
    "date", "dates", "planned", "plan", "status", "progress", "due", "overdue", "late", "slipped", "delayed",
    "behind", "deadline", "scheduled", "schedule",
}  # fmt: skip
_ABBREVIATIONS = {
    "csr": "clinical study report",
    "dbl": "database lock",
    "siv": "site initiation visit",
    "irb": "ethics",
    "iec": "ethics",
    "fpfv": "fpfv",
}
_NAME_STOPWORDS = {"the", "of", "and", "a", "an", "complete", "completed", "all", "for", "to", "with", "at"}


@dataclass
class StudyQuestion:
    intent: Intent
    study_ids: list[str] = field(default_factory=list)
    """Empty: all studies."""
    site_numbers: list[str] = field(default_factory=list)
    phase: str | None = None
    window_days: int | None = None
    milestones: list[str] = field(default_factory=list)
    """Plan entry names the question refers to."""
    overdue_only: bool = False
    asked_name: str | None = None
    """For "when is ..." questions: what was asked about, when no plan entry matched."""


# ---- understanding -------------------------------------------------------------------------------


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.lower())


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _match_studies(q: str, words: set[str], data: StudyData) -> list[str]:
    compact = _compact(q)
    found = []
    for s in data.studies:
        number = s.protocol_number.lower()
        # The full number, or any ending of two or more parts ("onc-301" for "AV-ONC-301"); never a
        # bare number, which could be a site.
        parts = number.split("-")
        variants = {number, *("-".join(parts[i:]) for i in range(1, len(parts) - 1))}
        if any(v and (v in q or (len(_compact(v)) >= 4 and _compact(v) in compact)) for v in variants):
            found.append(s.id)
            continue
        area = (s.therapeutic_area or "").lower()
        if area and area in words:
            found.append(s.id)
        elif "sandbox" in words and s.sandbox:
            found.append(s.id)
    return found


def _match_sites(q: str, data: StudyData, study_ids: list[str]) -> list[str]:
    numbers = re.findall(r"\bsites?\s+(?:number\s+|no\.?\s*|#)?([a-z]?\d{2,6})\b", q)
    names = [
        site.site_number
        for s in data.pick(study_ids)
        for site in s.sites
        if len(site.name) > 5 and site.name.lower() in q
    ]
    return list(dict.fromkeys([*numbers, *names]))


def _significant(name: str) -> tuple[set[str], set[str]]:
    """A plan entry's significant words and abbreviations, e.g. "(FPI, FPFV)" -> {"fpi", "fpfv"}."""
    abbreviations = {
        a.strip().lower() for group in re.findall(r"\(([^)]*)\)", name) for a in group.split(",") if a.strip()
    }
    plain = re.sub(r"\([^)]*\)", " ", name)
    plain = re.sub(r"^\s*[\d.]+\s*", "", plain)
    words = {w for w in _tokens(plain) if w not in _NAME_STOPWORDS and not w.isdigit()}
    return words, abbreviations


def _match_milestones(words: list[str], data: StudyData, study_ids: list[str]) -> list[str]:
    names = sorted({m.name for s in data.pick(study_ids) for m in s.milestones if m.kind != "phase"})
    vocab = {w for n in names for w in _significant(n)[0] if len(w) >= 5}
    fixed = set(words)
    for w in words:  # tolerate spelling mistakes in longer words ("databse" -> "database")
        if len(w) >= 5 and w not in vocab:
            fixed.update(difflib.get_close_matches(w, vocab, n=1, cutoff=0.84))
    scored: list[tuple[float, str]] = []
    for name in names:
        sig, abbreviations = _significant(name)
        if sig & _ORDINALS and fixed & _ORDINALS and not sig & _ORDINALS & fixed:
            continue  # "last patient in" never matches "first patient in"
        if abbreviations & fixed:
            scored.append((2.0, name))
            continue
        hits = len(sig & fixed)
        if hits >= 2 and sig and hits / len(sig) >= 0.6:
            scored.append((hits / len(sig), name))
    if not scored:
        return []
    best = max(score for score, _n in scored)
    return [n for score, n in scored if score == best]


def _window(q: str) -> int | None:
    m = re.search(r"\b(?:next|coming|within|in)\s+(\d{1,3})\s+(day|week|month|year)s?\b", q)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        return n * {"day": 1, "week": 7, "month": 30, "year": 365}[unit]
    for phrase, days in (
        ("next week", 7),
        ("this week", 7),
        ("next month", 31),
        ("this month", 31),
        ("next quarter", 92),
        ("this quarter", 92),
        ("this year", 365),
        ("next year", 365),
        ("next six months", 182),
    ):
        if phrase in q:
            return days
    return None


def _phase(words: set[str], q: str) -> str | None:
    if any(p in q for p in ("study end", "close out", "database lock", "last patient out")):
        return "close-out"
    if words & (set(_PHASES["close-out"][0]) - {"end"}):
        return "close-out"
    if words & {"startup", "start-up"} or "start up" in q:
        return "start-up"
    if "planning" in words:
        return "planning"
    return None


def understand(question: str, data: StudyData) -> StudyQuestion | None:
    """The study question being asked, or None when it is about procedures (SOP search)."""
    q = " ".join(question.lower().split())
    words = set(_tokens(q))
    if words & _STRONG_SOP:
        return None
    # Common abbreviations that plan entries spell out ("CSR" -> "Clinical Study Report Finalized").
    expanded = " ".join(_ABBREVIATIONS.get(w, w) for w in _tokens(q))
    token_list = _tokens(expanded)
    study_ids = _match_studies(q, words, data)
    site_numbers = _match_sites(q, data, study_ids)
    asked = re.search(r"\bwhen (?:is|are|will|was|does|do|did)\s+(?:the\s+)?(.+?)\??$", q)
    # A plan entry's name only counts when the question is about timing or names a study or site:
    # "site initiation visit" on its own is an SOP topic, "When is the site initiation visit?" is not.
    milestones = (
        _match_milestones(token_list, data, study_ids)
        if asked or study_ids or site_numbers or words & _TIMING_WORDS
        else []
    )
    entity = bool(study_ids or site_numbers or milestones)
    weak_sop = bool(words & _WEAK_SOP) or any(p in q for p in _WEAK_SOP_PHRASES)
    if weak_sop and not entity:
        return None

    keyword_intent: Intent | None = None
    order: tuple[Intent, ...] = ("tasks", "risks", "enrolment", "activation", "behind", "due")
    for candidate in order:
        if words & set(_INTENT_WORDS[candidate]):
            keyword_intent = candidate
            break
    # A plan entry's name wins for "when is ..." questions, or when nothing else is asked
    # ("Which sites aren't activated?" is about sites, not the "All Sites Activated" milestone).
    intent: Intent | None = "milestone" if milestones and (asked or keyword_intent is None) else None
    if intent is None:
        intent = keyword_intent
    if intent is None and asked:
        intent = "milestone"
    if intent is None:
        status_words = bool(words & set(_INTENT_WORDS["status"]))
        if entity or (status_words and words & _STUDY_CONTEXT) or words & {"portfolio"}:
            intent = "status"
    if intent is None:
        return None
    phase = _phase(words, q)
    if intent == "due" and phase is None and words & {"close", "closing", "closeout", "close-out", "closure"}:
        phase = "close-out"
    return StudyQuestion(
        intent=intent,
        study_ids=study_ids,
        site_numbers=site_numbers,
        phase=phase,
        window_days=_window(q),
        milestones=milestones,
        overdue_only=bool(words & {"overdue", "late", "behind"}),
        asked_name=re.sub(r"\s+(?:for|on|at)\s+.*$", "", asked.group(1))
        if asked and not milestones
        else None,
    )


# ---- answers ------------------------------------------------------------------------------------


class AnswerTable(BaseModel):
    title: str
    columns: list[str]
    rows: list[list[str]]
    links: list[str | None]
    """Per row: where the record is shown in Avi.Intelligence."""
    more: int = 0
    """Rows not shown (the table is capped)."""


class SourceLink(BaseModel):
    label: str
    url: str


class StudyAnswer(BaseModel):
    intent: Intent
    understood: str
    """How the question was read, e.g. "Close-out items due in the next 90 days · all studies"."""
    headline: str
    lines: list[str]
    tables: list[AnswerTable]
    sources: list[SourceLink]
    as_of: datetime | None
    sandbox_only: bool
    follow_ups: list[str]
    note: str


def day(d: date | None) -> str:
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year}" if d else "—"


def relative(days: int | None) -> str:
    if days is None:
        return "no date"
    if days == 0:
        return "today"
    if days > 0:
        return f"in {days} day{'s' if days != 1 else ''}"
    return f"{-days} day{'s' if days != -1 else ''} ago"


def slip(days: int | None) -> str:
    if days is None:
        return "no original date"
    if days == 0:
        return "on original date"
    return f"{'+' if days > 0 else '−'}{abs(days)} days"


_STATE = {
    MilestoneState.COMPLETED: "Completed",
    MilestoneState.OVERDUE: "Overdue",
    MilestoneState.DUE_SOON: "Due soon",
    MilestoneState.IN_PROGRESS: "In progress",
    MilestoneState.NOT_STARTED: "Not started",
    MilestoneState.UPCOMING: "Upcoming",
    MilestoneState.NOT_PLANNED: "No end date",
}


def _study_url(study_id: str, tab: str | None = None) -> str:
    return f"/command-centre/{study_id}" + (f"?tab={tab}" if tab else "")


def _plan_table(title: str, items: list[PlanItem], multi: bool) -> AnswerTable:
    shown = items[:MAX_ROWS]
    columns = (["Study"] if multi else []) + ["Plan entry", "Original end", "Current end", "Slip", "Status"]
    return AnswerTable(
        title=title,
        columns=columns,
        rows=[
            ([p.protocol_number] if multi else [])
            + [
                p.name,
                day(p.original_end),
                f"{day(p.current_end)} ({relative(p.days_from_today)})" if p.current_end else "—",
                slip(p.slip_days),
                _STATE[p.state]
                + (f" · {p.percent_complete}%" if p.percent_complete not in (None, 0, 100) else ""),
            ]
            for p in shown
        ],
        links=[_study_url(p.study_id, "milestones") for p in shown],
        more=len(items) - len(shown),
    )


def _entries(n: int) -> str:
    return "entry" if n == 1 else "entries"


def _scope(data: StudyData, q: StudyQuestion) -> str:
    if not q.study_ids:
        return "all studies" if len(data.studies) != 1 else data.studies[0].protocol_number
    return ", ".join(data.by_id[i].protocol_number for i in q.study_ids)


def _sources(data: StudyData, q: StudyQuestion, tab: str | None) -> list[SourceLink]:
    return [
        SourceLink(label=f"{s.protocol_number} · Study Command Centre", url=_study_url(s.id, tab))
        for s in data.pick(q.study_ids)
    ][:8]


def _status_lines(st: StudyStatus) -> list[str]:
    lines = []
    if st.on_plan:
        lines.append(f"On plan: no key milestone is overdue or has slipped more than {MAJOR_SLIP_DAYS} days.")
    else:
        parts = []
        if st.key_overdue:
            parts.append(f"{st.key_overdue} key milestone{'s' if st.key_overdue != 1 else ''} overdue")
        if st.key_slipped_major:
            parts.append(f"{st.key_slipped_major} slipped more than {MAJOR_SLIP_DAYS} days")
        lines.append("Not on plan: " + " and ".join(parts) + ".")
    n = st.next_key_milestone
    if n:
        lines.append(
            f"Next key milestone: {n.name}, {day(n.current_end)} ({relative(n.days_from_today)}"
            + (f", {slip(n.slip_days)} against the original date" if n.slip_days else "")
            + ")."
        )
    else:
        lines.append(
            "No key milestones left to complete."
            if st.key_milestones
            else "No key milestones in SimpleTrials."
        )
    if st.enrolment_target:
        lines.append(
            f"Enrolment: {st.enrolled or 0} of {st.enrolment_target} ({st.enrolment_percent or 0:g}%)."
        )
    elif st.enrolled is not None:
        lines.append(f"Enrolment: {st.enrolled} enrolled (no target recorded in SimpleTrials).")
    lines.append(f"Sites: {st.sites_activated} of {st.sites_total} activated.")
    work = f"Open tasks: {st.open_tasks}" + (f" ({st.overdue_tasks} overdue)" if st.overdue_tasks else "")
    work += (
        f"; open risks and issues: {st.open_risks}"
        + (f" ({st.high_risks} high)" if st.high_risks else "")
        + "."
    )
    lines.append(work)
    return lines


def _cap(text: str) -> str:
    text = text.strip()
    return text[:1].upper() + text[1:]


def _answer_sites(data: StudyData, q: StudyQuestion) -> tuple[str, list[str], list[AnswerTable]]:
    rows = sites(data, SitesInput(study_ids=q.study_ids or None, site_numbers=q.site_numbers))
    if not rows:
        return f"No site {', '.join(q.site_numbers)} in SimpleTrials for this selection.", [], []
    lines = []
    for s in rows:
        if s.activated_on:
            activation = f"activated on {day(s.activated_on)}"
        elif s.planned_activation:
            activation = f"not activated (planned {day(s.planned_activation)}" + (
                f", {s.days_late} days late)" if s.days_late else ")"
            )
        else:
            activation = "not activated (no planned date)"
        enrolment = (
            f"{s.enrolled or 0} of {s.target} enrolled ({s.percent or 0:g}%)"
            if s.target
            else f"{s.enrolled or 0} enrolled (no target)"
        )
        lines.append(
            f"Site {s.site_number} · {s.name} ({s.protocol_number}): {s.status or 'status not recorded'}; "
            f"{activation}; {enrolment}."
        )
    head = lines[0] if len(lines) == 1 else f"{len(rows)} matching sites."
    table = AnswerTable(
        title="Sites",
        columns=["Study", "Site", "Status", "Activated", "Planned activation", "Enrolled", "Target"],
        rows=[
            [
                s.protocol_number,
                f"{s.site_number} · {s.name}",
                s.status or "—",
                day(s.activated_on),
                day(s.planned_activation),
                str(s.enrolled or 0),
                str(s.target) if s.target else "No target",
            ]
            for s in rows
        ],
        links=[_study_url(s.study_id, "sites") for s in rows],
    )
    return head, lines if len(lines) > 1 else [], [table]


def _answer_status(data: StudyData, q: StudyQuestion) -> tuple[str, list[str], list[AnswerTable]]:
    if q.site_numbers:
        return _answer_sites(data, q)
    rows = studies_overview(data, StudiesInput(study_ids=q.study_ids or None))
    if len(rows) == 1:
        st = rows[0]
        return (
            f"{st.protocol_number} is {'on plan' if st.on_plan else 'not on plan'}.",
            _status_lines(st),
            [_plan_table("Key milestones", st.key_milestones, multi=False)] if st.key_milestones else [],
        )
    off = [r for r in rows if not r.on_plan]
    table = AnswerTable(
        title="Studies",
        columns=[
            "Study",
            "On plan",
            "Key overdue",
            f"Slipped >{MAJOR_SLIP_DAYS}d",
            "Next key milestone",
            "Enrolment",
            "Sites activated",
        ],
        rows=[
            [
                r.protocol_number,
                "Yes" if r.on_plan else "No",
                str(r.key_overdue),
                str(r.key_slipped_major),
                f"{r.next_key_milestone.name} · {day(r.next_key_milestone.current_end)}"
                if r.next_key_milestone
                else "—",
                f"{r.enrolled or 0} of {r.enrolment_target} ({r.enrolment_percent or 0:g}%)"
                if r.enrolment_target
                else (f"{r.enrolled} (no target)" if r.enrolled is not None else "—"),
                f"{r.sites_activated} of {r.sites_total}",
            ]
            for r in rows
        ],
        links=[_study_url(r.study_id) for r in rows],
    )
    lines = []
    for r in off:
        lines.append(
            f"{r.protocol_number}: {r.key_overdue} key milestone{'s' if r.key_overdue != 1 else ''} overdue, "
            f"{r.key_slipped_major} slipped more than {MAJOR_SLIP_DAYS} days."
        )
    head = "All studies are on plan." if not off else f"{len(off)} of {len(rows)} studies are not on plan."
    return head, lines, [table]


def _phase_filter(q: StudyQuestion) -> tuple[list[str] | None, list[str] | None]:
    if q.phase is None:
        return None, None
    _t, phase_words, name_words = _PHASES[q.phase]
    return phase_words, name_words or None


def _answer_due(data: StudyData, q: StudyQuestion) -> tuple[str, list[str], list[AnswerTable]]:
    window = q.window_days or DEFAULT_WINDOW_DAYS
    phase_words, name_words = _phase_filter(q)
    items = plan_items(
        data,
        PlanInput(
            study_ids=q.study_ids or None,
            phase_words=phase_words,
            name_words=name_words,
            due_within_days=window,
        ),
    )
    what = f"{q.phase} " if q.phase else ""
    overdue = [p for p in items if p.state == MilestoneState.OVERDUE]
    upcoming = [p for p in items if p.state != MilestoneState.OVERDUE]
    lines = [
        f"{len(upcoming)} {what}plan {_entries(len(upcoming))} due in the next {window} days.",
        f"{len(overdue)} already overdue." if overdue else "Nothing overdue.",
    ]
    tables = []
    if items:
        tables.append(
            _plan_table(
                _cap(f"{what}due and overdue entries"),
                items,
                multi=len(data.pick(q.study_ids)) > 1,
            )
        )
    else:
        later = plan_items(
            data, PlanInput(study_ids=q.study_ids or None, phase_words=phase_words, name_words=name_words)
        )
        later = [p for p in later if p.current_end]
        if later:
            first = later[0]
            lines.append(
                f"The next {what}entry is {first.name} ({first.protocol_number}), {day(first.current_end)} "
                f"({relative(first.days_from_today)})."
            )
            tables.append(
                _plan_table(_cap(f"next {what}entries"), later[:10], multi=len(data.pick(q.study_ids)) > 1)
            )
        else:
            lines.append(f"No open {what}entries with an end date in SimpleTrials.")
    head = (
        f"{len(items)} {what}{_entries(len(items))} {'needs' if len(items) == 1 else 'need'} attention "
        f"in the next {window} days."
        if items
        else f"Nothing {what}is due in the next {window} days."
    )
    return head, lines, tables


def _answer_behind(data: StudyData, q: StudyQuestion) -> tuple[str, list[str], list[AnswerTable]]:
    phase_words, name_words = _phase_filter(q)
    ids = q.study_ids or None
    overdue = plan_items(
        data,
        PlanInput(
            study_ids=ids, phase_words=phase_words, name_words=name_words, states=[MilestoneState.OVERDUE]
        ),
    )
    pending = plan_items(data, PlanInput(study_ids=ids, phase_words=phase_words, name_words=name_words))
    slipped = [
        p for p in pending if p.schedule == ScheduleState.SLIPPED_MAJOR and p.state != MilestoneState.OVERDUE
    ]
    late_sites = [s for s in sites(data, SitesInput(study_ids=ids)) if s.days_late]
    late_tasks = open_tasks(data, WorkInput(study_ids=ids, overdue_only=True))
    multi = len(data.pick(q.study_ids)) > 1
    lines = [
        f"Overdue plan entries: {len(overdue)}.",
        f"Still to complete and slipped more than {MAJOR_SLIP_DAYS} days against the original date: "
        f"{len(slipped)}.",
    ]
    if q.phase is None:
        lines.append(f"Sites past their planned activation date: {len(late_sites)}.")
        lines.append(f"Overdue Avi.Intelligence tasks: {len(late_tasks)}.")
        lines.append(
            "Enrolment pace is not judged here: SimpleTrials gives today's figures only. "
            'Ask "Which sites are behind on enrolment?" for enrolment against target.'
        )
    tables = []
    if overdue:
        tables.append(_plan_table("Overdue", overdue, multi))
    if slipped:
        tables.append(_plan_table(f"Slipped more than {MAJOR_SLIP_DAYS} days", slipped, multi))
    if late_sites and q.phase is None:
        tables.append(
            AnswerTable(
                title="Sites not activated by their planned date",
                columns=["Study", "Site", "Planned activation", "Days late"],
                rows=[
                    [
                        s.protocol_number,
                        f"{s.site_number} · {s.name}",
                        day(s.planned_activation),
                        str(s.days_late),
                    ]
                    for s in late_sites
                ],
                links=[_study_url(s.study_id, "sites") for s in late_sites],
            )
        )
    if late_tasks and q.phase is None:
        tables.append(
            AnswerTable(
                title="Overdue tasks",
                columns=["Task", "Study", "Due", "Waiting on"],
                rows=[
                    [
                        f"{t.reference} · {t.title}",
                        t.protocol_number,
                        day(t.due_date),
                        ", ".join(t.people) or "—",
                    ]
                    for t in late_tasks[:MAX_ROWS]
                ],
                links=["/tasks?scope=all"] * min(len(late_tasks), MAX_ROWS),
                more=max(0, len(late_tasks) - MAX_ROWS),
            )
        )
    behind = len(overdue) + len(slipped) + (len(late_sites) + len(late_tasks) if q.phase is None else 0)
    head = (
        "Yes, some work is behind." if behind else "Nothing is behind: no overdue or badly slipped entries."
    )
    return head, lines, tables


def _answer_milestone(data: StudyData, q: StudyQuestion) -> tuple[str, list[str], list[AnswerTable]]:
    items = plan_items(data, PlanInput(study_ids=q.study_ids or None, include_completed=True))
    items = [p for p in items if p.name in set(q.milestones)]
    if not items:
        key = plan_items(data, PlanInput(study_ids=q.study_ids or None, key_only=True))
        what = f'"{q.asked_name}"' if q.asked_name else "that"
        return (
            f"No plan entry matches {what} in SimpleTrials.",
            ["Try the milestone's name as it appears in the plan, or one of the open key milestones below."],
            [_plan_table("Open key milestones", key, multi=len(data.pick(q.study_ids)) > 1)] if key else [],
        )
    multi = len({p.study_id for p in items}) > 1
    lines = []
    for p in items[:6]:
        where = f"{p.protocol_number}: " if multi else ""
        if p.state == MilestoneState.COMPLETED:
            lines.append(f"{where}{p.name} is completed (planned end {day(p.current_end)}).")
        else:
            lines.append(
                f"{where}{p.name}: current end {day(p.current_end)} ({relative(p.days_from_today)}), "
                f"original {day(p.original_end)} ({slip(p.slip_days)}). Status: {_STATE[p.state]}."
            )
    head = lines[0] if len(lines) == 1 else f"{len(items)} matching plan entries."
    return (
        head,
        lines if len(lines) > 1 else [],
        [_plan_table("Matching plan entries", items, multi=multi)],
    )


def _answer_enrolment(data: StudyData, q: StudyQuestion) -> tuple[str, list[str], list[AnswerTable]]:
    rows = sites(data, SitesInput(study_ids=q.study_ids or None, site_numbers=q.site_numbers or None))
    rows.sort(key=lambda s: (s.percent is None, s.percent if s.percent is not None else 0, s.site_number))
    with_target = [s for s in rows if s.target]
    zero = [s for s in with_target if not s.enrolled]
    below_half = [s for s in with_target if s.percent is not None and s.percent < 50]
    statuses = studies_overview(data, StudiesInput(study_ids=q.study_ids or None))
    lines = [
        f"{st.protocol_number}: {st.enrolled or 0} of {st.enrolment_target} enrolled "
        f"({st.enrolment_percent or 0:g}%)."
        if st.enrolment_target
        else f"{st.protocol_number}: {st.enrolled or 0} enrolled (no target recorded)."
        for st in statuses
    ][:8]
    lines.append(f"Sites below half of their target: {len(below_half)}; with none enrolled: {len(zero)}.")
    lines.append("Behind here means against the site's target; SimpleTrials gives no enrolment plan by date.")
    table = AnswerTable(
        title="Enrolment by site (furthest behind first)",
        columns=["Study", "Site", "Enrolled", "Target", "% of target"],
        rows=[
            [
                s.protocol_number,
                f"{s.site_number} · {s.name}",
                str(s.enrolled or 0),
                str(s.target) if s.target else "No target",
                f"{s.percent:g}%" if s.percent is not None else "—",
            ]
            for s in rows[:MAX_ROWS]
        ],
        links=[_study_url(s.study_id, "sites") for s in rows[:MAX_ROWS]],
        more=max(0, len(rows) - MAX_ROWS),
    )
    head = (
        f"{len(below_half)} site{'s are' if len(below_half) != 1 else ' is'} below half of their "
        "enrolment target."
        if with_target
        else "No site has an enrolment target in SimpleTrials."
    )
    return head, lines, [table] if rows else []


def _answer_activation(data: StudyData, q: StudyQuestion) -> tuple[str, list[str], list[AnswerTable]]:
    rows = sites(data, SitesInput(study_ids=q.study_ids or None, site_numbers=q.site_numbers or None))
    pending = [s for s in rows if not s.activated_on]
    pending.sort(key=lambda s: (-(s.days_late or 0), s.planned_activation or date.max))
    late = [s for s in pending if s.days_late]
    lines = [
        f"{len(rows) - len(pending)} of {len(rows)} sites are activated.",
        f"{len(late)} not activated by their planned date."
        if late
        else "None is past its planned activation date.",
    ]
    table = AnswerTable(
        title="Sites not yet activated",
        columns=["Study", "Site", "Status", "Planned activation", "Days late"],
        rows=[
            [
                s.protocol_number,
                f"{s.site_number} · {s.name}",
                s.status or "—",
                day(s.planned_activation),
                str(s.days_late) if s.days_late else "—",
            ]
            for s in pending
        ],
        links=[_study_url(s.study_id, "sites") for s in pending],
    )
    head = (
        "All sites are activated."
        if not pending
        else f"{len(pending)} site{'s' if len(pending) != 1 else ''} not yet activated."
    )
    return head, lines, [table] if pending else []


def _answer_tasks(data: StudyData, q: StudyQuestion) -> tuple[str, list[str], list[AnswerTable]]:
    rows = open_tasks(data, WorkInput(study_ids=q.study_ids or None, overdue_only=q.overdue_only))
    overdue = [t for t in rows if t.overdue]
    table = AnswerTable(
        title="Open study tasks (overdue first)",
        columns=["Task", "Study", "Status", "Due", "Waiting on"],
        rows=[
            [
                f"{t.reference} · {t.title}",
                t.protocol_number,
                t.status,
                day(t.due_date) + (" (overdue)" if t.overdue else ""),
                ", ".join(t.people) or "—",
            ]
            for t in rows[:MAX_ROWS]
        ],
        links=["/tasks?scope=all"] * min(len(rows), MAX_ROWS),
        more=max(0, len(rows) - MAX_ROWS),
    )
    head = f"{len(rows)} open study task{'s' if len(rows) != 1 else ''}, {len(overdue)} overdue."
    return head, [], [table] if rows else []


def _answer_risks(data: StudyData, q: StudyQuestion) -> tuple[str, list[str], list[AnswerTable]]:
    rows = open_risks(data, WorkInput(study_ids=q.study_ids or None))
    high = [r for r in rows if r.rating == "High"]
    table = AnswerTable(
        title="Open risks and issues (highest score first)",
        columns=["Reference", "Study", "Type", "Title", "Rating", "Owner", "Status"],
        rows=[
            [
                r.reference,
                r.protocol_number,
                "Issue" if r.kind == "issue" else "Risk",
                r.title,
                f"{r.rating} · {r.score}",
                r.owner,
                r.status,
            ]
            for r in rows[:MAX_ROWS]
        ],
        links=["/risks"] * min(len(rows), MAX_ROWS),
        more=max(0, len(rows) - MAX_ROWS),
    )
    head = f"{len(rows)} open risk{'s' if len(rows) != 1 else ''} and issues, {len(high)} rated High."
    return head, [], [table] if rows else []


_ANSWERERS = {
    "status": (_answer_status, None),
    "due": (_answer_due, "milestones"),
    "behind": (_answer_behind, "milestones"),
    "milestone": (_answer_milestone, "milestones"),
    "enrolment": (_answer_enrolment, "sites"),
    "activation": (_answer_activation, "sites"),
    "tasks": (_answer_tasks, "tasks"),
    "risks": (_answer_risks, "risks"),
}

_UNDERSTOOD = {
    "status": "How the studies are going",
    "due": "What is due",
    "behind": "What is behind",
    "milestone": "Milestone dates",
    "enrolment": "Enrolment against target",
    "activation": "Site activation",
    "tasks": "Open study tasks",
    "risks": "Open risks and issues",
}

FOLLOW_UPS = {
    "status": [
        "Are we falling behind?",
        "Is anything due for study close-out?",
        "Which sites are behind on enrolment?",
    ],
    "due": ["Are we falling behind?", "How are my studies going?", "What is due in the next 30 days?"],
    "behind": ["What is due in the next 30 days?", "Which sites are not activated?", "Open risks?"],
    "milestone": ["Is anything due for study close-out?", "Are we falling behind?"],
    "enrolment": ["Which sites are not activated?", "How are my studies going?"],
    "activation": ["Which sites are behind on enrolment?", "Are we falling behind?"],
    "tasks": ["Open risks?", "Are we falling behind?"],
    "risks": ["Overdue tasks?", "How are my studies going?"],
}


def answer(data: StudyData, q: StudyQuestion) -> StudyAnswer:
    build, tab = _ANSWERERS[q.intent]
    headline, lines, tables = build(data, q)
    understood = _UNDERSTOOD[q.intent]
    if q.phase:
        understood += f" · {q.phase}"
    if q.intent == "due":
        understood += f" · next {q.window_days or DEFAULT_WINDOW_DAYS} days"
    if q.site_numbers:
        understood += " · site " + ", ".join(q.site_numbers)
    understood += f" · {_scope(data, q)}"
    return StudyAnswer(
        intent=q.intent,
        understood=understood,
        headline=headline,
        lines=lines,
        tables=tables,
        sources=_sources(data, q, tab),
        as_of=data.as_of,
        sandbox_only=data.sandbox_only,
        follow_ups=FOLLOW_UPS[q.intent],
        note=(
            "Worked out by Avi.Intelligence from its read-only copy of SimpleTrials and its own tasks and "
            "risks, "
            "using the same rules as the Study Command Centre and Reports. " + PRIVACY_NOTE
        ),
    )


STUDY_QUESTIONS = [
    "How are my studies going?",
    "Is anything due for study close-out?",
    "Are we falling behind?",
    "Which sites are behind on enrolment?",
]
