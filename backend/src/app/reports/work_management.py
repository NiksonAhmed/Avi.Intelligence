"""Work management report: open tasks by category, study and person, overdue tasks, risk heat map.

Pure calculations over Avi.Intelligence's own tasks and risks. Every figure follows a rule listed in
`WORK_MANAGEMENT_RULES` (shown under each chart); nothing is estimated.
"""

from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel

from app.studies.models import Risk, Study, Task
from app.studies.rules import (
    RULES,
    TASK_CATEGORY_LABELS,
    TASK_CLOSED,
    RiskKind,
    RiskStatus,
    TaskCategory,
    TaskStatus,
    risk_rating,
    risk_score,
    task_overdue,
)

from .study_delivery import Option, Tile

DUE_SOON_DAYS = 14
COMPLETED_WINDOW_DAYS = 30
LEVELS = {1: "Low", 2: "Medium", 3: "High"}

WORK_MANAGEMENT_RULES = {
    "open": (
        "Open: not completed and not cancelled. A task with several people stays open until everyone "
        "has finished their part."
    ),
    "task_overdue": RULES["task_overdue"],
    "due_soon": f"Due soon: due today or within the next {DUE_SOON_DAYS} days, and still open.",
    "completed": (
        f"Completed in the last {COMPLETED_WINDOW_DAYS} days: the day the last person finished. "
        "On time: finished on or before the due date (tasks without a due date are not counted)."
    ),
    "by_person": (
        "Each person's open parts: tasks assigned to them that they have not finished yet. A task with "
        "three people counts once for each of them; someone who has finished their part is not counted."
    ),
    "heat_map": RULES["risk_score"]
    + " Open and Mitigating risks and issues are counted; closed ones are not.",
    "filters": (
        "The category filter applies to tasks only. Risks and issues always belong to a study, so the "
        "study filter applies to them as well."
    ),
}


class StatusCounts(BaseModel):
    key: str
    label: str
    not_started: int = 0
    in_progress: int = 0
    blocked: int = 0
    overdue: int = 0
    total: int = 0


class PersonLoad(BaseModel):
    person_id: str
    name: str
    open: int = 0
    overdue: int = 0
    due_soon: int = 0
    blocked: int = 0


class OverdueTask(BaseModel):
    task_id: str
    reference: str
    title: str
    category: TaskCategory
    category_label: str
    about: str | None
    due_date: date
    days_overdue: int
    status: str
    waiting_on: list[str]
    """People who have not finished their part yet."""


class HeatCell(BaseModel):
    likelihood: int
    impact: int
    score: int
    rating: str
    risks: int = 0
    issues: int = 0


class OpenRisk(BaseModel):
    risk_id: str
    reference: str
    kind: RiskKind
    title: str
    protocol_number: str
    likelihood: int
    impact: int
    score: int
    rating: str
    owner_name: str
    status: str


class OpenTask(BaseModel):
    """One row of the Excel export's open-task list."""

    reference: str
    category_label: str
    about: str | None
    title: str
    people: str
    status: str
    due_date: date | None
    days_overdue: int | None


class WorkManagement(BaseModel):
    tiles: list[Tile]
    by_category: list[StatusCounts]
    by_study: list[StatusCounts]
    by_person: list[PersonLoad]
    overdue: list[OverdueTask]
    heat_map: list[HeatCell]
    top_risks: list[OpenRisk]
    open_tasks: list[OpenTask]
    completed: dict[str, int]
    study_options: list[Option]
    category_options: list[Option]
    rules: dict[str, str]


def task_about(task: Task) -> str | None:
    """What the task is about, in a few words (study, SOP numbers or the vendor/system name)."""
    if task.category == TaskCategory.STUDY and task.study is not None:
        return task.study.protocol_number
    if task.category == TaskCategory.SOP:
        return ", ".join(d.sop_number or d.title for d in task.documents) or None
    return task.subject_name


def _count(row: StatusCounts, task: Task, overdue: bool) -> None:
    row.total += 1
    row.overdue += overdue
    if task.status == TaskStatus.BLOCKED:
        row.blocked += 1
    elif task.status == TaskStatus.IN_PROGRESS:
        row.in_progress += 1
    else:
        row.not_started += 1


def build_work_management(
    tasks: list[Task],
    risks: list[Risk],
    studies: list[Study],
    today: date,
    *,
    study_id: str | None = None,
    category: TaskCategory | None = None,
) -> WorkManagement:
    study_options = [Option(id=s.id, label=f"{s.protocol_number} · {s.title}") for s in studies]
    category_options = [Option(id=c.value, label=TASK_CATEGORY_LABELS[c]) for c in TaskCategory]
    scoped = [
        t
        for t in tasks
        if (not study_id or t.study_id == study_id) and (not category or t.category == category)
    ]
    open_tasks = [t for t in scoped if t.status not in TASK_CLOSED]
    soon = today + timedelta(days=DUE_SOON_DAYS)

    # ---- by category and by study ----
    by_category = {
        c: StatusCounts(key=c.value, label=TASK_CATEGORY_LABELS[c])
        for c in TaskCategory
        if not category or c == category
    }
    by_study: dict[str, StatusCounts] = {}
    for s in studies:
        if not study_id or s.id == study_id:
            by_study[s.id] = StatusCounts(key=s.id, label=s.protocol_number)
    if category and category != TaskCategory.STUDY:
        by_study = {}

    overdue_rows: list[OverdueTask] = []
    open_rows: list[OpenTask] = []
    people: dict[str, PersonLoad] = {}
    for t in open_tasks:
        late = task_overdue(t.due_date, t.status, today)
        due_soon = t.due_date is not None and today <= t.due_date <= soon
        _count(by_category[TaskCategory(t.category)], t, late)
        if t.study_id and t.study is not None:
            row = by_study.get(t.study_id)
            if row is None and not study_id:
                row = by_study[t.study_id] = StatusCounts(key=t.study_id, label=t.study.protocol_number)
            if row is not None:
                _count(row, t, late)
        waiting = [a for a in t.assignees if a.status != TaskStatus.COMPLETED]
        for a in waiting:
            load = people.setdefault(a.person_id, PersonLoad(person_id=a.person_id, name=a.person_name))
            load.open += 1
            load.overdue += late
            load.due_soon += due_soon
            load.blocked += a.status == TaskStatus.BLOCKED
        days_late = (today - t.due_date).days if late and t.due_date else None
        if late and t.due_date and days_late is not None:
            overdue_rows.append(
                OverdueTask(
                    task_id=t.id,
                    reference=t.reference,
                    title=t.title,
                    category=TaskCategory(t.category),
                    category_label=TASK_CATEGORY_LABELS[TaskCategory(t.category)],
                    about=task_about(t),
                    due_date=t.due_date,
                    days_overdue=days_late,
                    status=t.status,
                    waiting_on=[a.person_name for a in waiting],
                )
            )
        open_rows.append(
            OpenTask(
                reference=t.reference,
                category_label=TASK_CATEGORY_LABELS[TaskCategory(t.category)],
                about=task_about(t),
                title=t.title,
                people=", ".join(f"{a.person_name} ({a.status})" for a in t.assignees),
                status=t.status,
                due_date=t.due_date,
                days_overdue=days_late,
            )
        )
    overdue_rows.sort(key=lambda r: (-r.days_overdue, r.reference))
    open_rows.sort(key=lambda r: (r.due_date is None, r.due_date or date.max, r.reference))
    by_person = sorted(people.values(), key=lambda p: (-p.overdue, -p.open, p.name))
    study_rows = sorted(by_study.values(), key=lambda r: (-r.overdue, -r.total, r.label))

    # ---- completed recently ----
    since = today - timedelta(days=COMPLETED_WINDOW_DAYS)
    finished = [
        t
        for t in scoped
        if t.status == TaskStatus.COMPLETED and t.completed_at and t.completed_at.date() >= since
    ]
    with_due = [t for t in finished if t.due_date]
    on_time = sum(
        1 for t in with_due if t.completed_at and t.due_date and t.completed_at.date() <= t.due_date
    )
    completed = {"total": len(finished), "with_due_date": len(with_due), "on_time": on_time}

    # ---- risks and issues ----
    open_risks = [
        r for r in risks if r.status != RiskStatus.CLOSED and (not study_id or r.study_id == study_id)
    ]
    cells = {
        (lk, im): HeatCell(
            likelihood=lk, impact=im, score=risk_score(lk, im), rating=risk_rating(risk_score(lk, im))
        )
        for lk in (3, 2, 1)
        for im in (1, 2, 3)
    }
    top: list[OpenRisk] = []
    for r in open_risks:
        cell = cells.get((r.likelihood, r.impact))
        if cell is not None:
            if r.kind == RiskKind.ISSUE:
                cell.issues += 1
            else:
                cell.risks += 1
        score = risk_score(r.likelihood, r.impact)
        top.append(
            OpenRisk(
                risk_id=r.id,
                reference=r.reference,
                kind=RiskKind(r.kind),
                title=r.title,
                protocol_number=r.study.protocol_number if r.study is not None else "",
                likelihood=r.likelihood,
                impact=r.impact,
                score=score,
                rating=risk_rating(score),
                owner_name=r.owner_name,
                status=r.status,
            )
        )
    top.sort(key=lambda r: (-r.score, r.reference))
    high = sum(r.rating == "High" for r in top)

    # ---- headline tiles ----
    blocked = sum(t.status == TaskStatus.BLOCKED for t in open_tasks)
    overdue_count = len(overdue_rows)
    due_soon_count = sum(1 for t in open_tasks if t.due_date is not None and today <= t.due_date <= soon)
    tiles = [
        Tile(
            key="open",
            label="Open tasks",
            value=str(len(open_tasks)),
            note=f"{blocked} blocked" if blocked else "None blocked",
            tone="neutral",
        ),
        Tile(
            key="overdue",
            label="Overdue tasks",
            value=str(overdue_count),
            note="Past the due date, not completed",
            tone="bad" if overdue_count else "good",
        ),
        Tile(
            key="due_soon",
            label=f"Due in the next {DUE_SOON_DAYS} days",
            value=str(due_soon_count),
            note="Still open",
            tone="warn" if due_soon_count else "neutral",
        ),
        Tile(
            key="completed",
            label=f"Completed in the last {COMPLETED_WINDOW_DAYS} days",
            value=str(len(finished)),
            note=f"{on_time} of {len(with_due)} on time" if with_due else "None with a due date",
            tone="info",
        ),
        Tile(
            key="high_risks",
            label="Open high risks and issues",
            value=str(high),
            note=f"{len(top)} open in all",
            tone="bad" if high else "good",
        ),
    ]

    return WorkManagement(
        tiles=tiles,
        by_category=list(by_category.values()),
        by_study=study_rows,
        by_person=by_person,
        overdue=overdue_rows,
        heat_map=list(cells.values()),
        top_risks=top,
        open_tasks=open_rows,
        completed=completed,
        study_options=study_options,
        category_options=category_options,
        rules=WORK_MANAGEMENT_RULES,
    )


def level(value: int) -> str:
    return LEVELS.get(value, str(value))
