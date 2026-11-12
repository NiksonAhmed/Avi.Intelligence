"""Tasks, risks and issues (managed in Avi.Intelligence).

Access rules (agreed with Avion):
  * Everyone with study access can view all tasks and risks (read-only).
  * Tasks are assigned by category (`task.assign.<category>`): Admin all; Project Managers Study and
    General; QA Procedures and SOPs, Vendor, Computer system and General. Whoever may assign a
    category may also edit and cancel its tasks.
  * Everyone else (except viewers) may create tasks for themselves only, for their own tracking, in
    any category but Procedures and SOPs (`task.create_own`). They can edit and cancel those tasks.
  * A task can have several people; each updates their own status, and the task is Completed when
    everyone is done. The owner of a risk may update its status; risks are managed by administrators.

Task categories: Study (a study, optionally one plan entry), Procedures and SOPs (one or more SOPs or
forms from the live approved list), Vendor and Computer system (a name as typed), General.
Nothing is deleted: a task is cancelled and a risk is closed instead, and every change is audited.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.sops import _with_details
from app.audit.service import record_event
from app.auth.directory import Person, get_person, list_people
from app.auth.rbac import CurrentUser, Permission, require
from app.connectors.sharepoint import get_sop_connector
from app.connectors.sharepoint.models import DocumentKind, SopConnector, SopStatus
from app.db.session import get_db
from app.studies.clock import today
from app.studies.models import (
    Risk,
    Study,
    StudyActionItem,
    StudyMilestone,
    Task,
    TaskAssignee,
    TaskDocument,
)
from app.studies.rules import (
    TASK_CATEGORY_LABELS,
    TASK_CLOSED,
    RiskKind,
    RiskStatus,
    TaskCategory,
    TaskStatus,
    overall_task_status,
    risk_rating,
    risk_score,
    task_overdue,
)

router = APIRouter(tags=["Tasks and risks"])

ItemId = Annotated[str, Path(pattern=r"^[0-9a-f\-]{36}$")]
Db = Annotated[Session, Depends(get_db)]
Reader = Annotated[CurrentUser, Depends(require(Permission.STUDY_READ))]
Manager = Annotated[CurrentUser, Depends(require(Permission.WORK_MANAGE))]
SopSource = Annotated[SopConnector, Depends(get_sop_connector)]
MAX_TASK_DOCUMENTS = 20


def _clean(v: object) -> object:
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


# --- People ---------------------------------------------------------------------------------------


@router.get("/people", response_model=list[Person], tags=["Users"])
def people(_user: Reader) -> list[Person]:
    return list_people()


def _person_or_422(person_id: str) -> Person:
    person = get_person(person_id)
    if person is None:
        raise HTTPException(422, "Unknown person. Choose someone from the directory.")
    return person


def _study_or_422(db: Session, tenant_id: str, study_id: str) -> Study:
    study = db.scalars(select(Study).where(Study.tenant_id == tenant_id, Study.id == study_id)).first()
    if study is None:
        raise HTTPException(422, "Unknown study.")
    return study


def _next_reference(db: Session, model: type[Task] | type[Risk], tenant_id: str, prefix: str) -> str:
    count = db.scalar(select(func.count()).select_from(model).where(model.tenant_id == tenant_id)) or 0
    return f"{prefix}-{count + 1:04d}"


class StudyRef(BaseModel):
    id: str
    protocol_number: str
    title: str


# --- Tasks ----------------------------------------------------------------------------------------

ASSIGN_PERMISSION: dict[TaskCategory, Permission] = {
    TaskCategory.STUDY: Permission.TASK_ASSIGN_STUDY,
    TaskCategory.SOP: Permission.TASK_ASSIGN_SOP,
    TaskCategory.VENDOR: Permission.TASK_ASSIGN_VENDOR,
    TaskCategory.SYSTEM: Permission.TASK_ASSIGN_SYSTEM,
    TaskCategory.GENERAL: Permission.TASK_ASSIGN_GENERAL,
}
MAX_TASK_ASSIGNEES = 50


def can_assign(user: CurrentUser, category: TaskCategory) -> bool:
    """May create tasks of this category for anyone, and edit or cancel any of them."""
    return user.can(Permission.WORK_MANAGE) or user.can(ASSIGN_PERMISSION[category])


def can_create_own(user: CurrentUser, category: TaskCategory) -> bool:
    """May create a task assigned only to themselves (never a Procedures and SOPs task)."""
    return category != TaskCategory.SOP and user.can(Permission.TASK_CREATE_OWN)


def creatable_categories(user: CurrentUser) -> list[TaskCategory]:
    return [c for c in TaskCategory if can_assign(user, c) or can_create_own(user, c)]


def assignable_categories(user: CurrentUser) -> list[TaskCategory]:
    return [c for c in TaskCategory if can_assign(user, c)]


def _is_own_task(task: Task) -> bool:
    """Created by someone for themselves only."""
    return [a.person_id for a in task.assignees] == [task.created_by_id]


def can_edit_task(user: CurrentUser, task: Task) -> bool:
    category = TaskCategory(task.category)
    if can_assign(user, category):
        return True
    return task.created_by_id == user.id and _is_own_task(task) and can_create_own(user, category)


class PlanItemRef(BaseModel):
    """The study-plan entry (SimpleTrials milestone/task) a task was raised for."""

    external_id: str
    name: str


class TaskDocumentRef(BaseModel):
    """An approved SOP or form, as it was when the task was raised."""

    sop_id: str
    kind: str
    sop_number: str | None
    title: str
    version: str | None


class CategoryOption(BaseModel):
    value: TaskCategory
    label: str


class AssigneeOut(BaseModel):
    person_id: str
    name: str
    status: TaskStatus
    completed_at: datetime | None


class TaskProgress(BaseModel):
    completed: int
    total: int


class TaskOut(BaseModel):
    id: str
    reference: str
    category: TaskCategory
    category_label: str
    study: StudyRef | None
    plan_item: PlanItemRef | None
    subject_name: str | None
    """Vendor or computer system name (as typed)."""
    documents: list[TaskDocumentRef]
    """Procedures and SOPs tasks: the approved SOPs/forms the task is about."""
    title: str
    description: str | None
    assignees: list[AssigneeOut]
    """Everyone the task is assigned to, each with their own status."""
    progress: TaskProgress
    due_date: date | None
    status: TaskStatus
    """Overall: Completed when everyone is done; Cancelled when a manager cancelled the task."""
    my_status: TaskStatus | None
    """The current user's own status, when they are one of the assigned people."""
    own_task: bool
    """Created by someone for themselves."""
    overdue: bool
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    can_update_status: bool
    can_edit: bool


class TaskListResponse(BaseModel):
    tasks: list[TaskOut]
    can_manage: bool
    """Administrator: manages every task."""
    can_create: list[TaskCategory]
    """Categories the current user may create tasks in (empty = read-only)."""
    can_assign: list[TaskCategory]
    """Categories the current user may assign to other people; others are for themselves only."""
    categories: list[CategoryOption]
    statuses: list[str]


class TaskCreate(BaseModel):
    category: TaskCategory = TaskCategory.STUDY
    study_id: str | None = Field(default=None, max_length=36)
    """Study tasks: the study."""
    plan_item_id: str | None = Field(default=None, max_length=255)
    """Optional, study tasks: the study-plan entry this task is for (its SimpleTrials id)."""
    subject_name: str | None = Field(default=None, max_length=200)
    """Vendor / computer system tasks: its name."""
    document_ids: list[str] = Field(default_factory=list, max_length=MAX_TASK_DOCUMENTS)
    """Procedures and SOPs tasks: approved SOP/form ids from the SOP library."""
    title: str = Field(min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    assignee_ids: list[str] = Field(default_factory=list, max_length=MAX_TASK_ASSIGNEES)
    """Everyone the task is assigned to."""
    assignee_id: str | None = None
    """Single assignee (older clients); combined with assignee_ids."""
    due_date: date | None = None

    _strip = field_validator("title", "description", "subject_name", mode="before")(_clean)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    subject_name: str | None = Field(default=None, max_length=200)
    document_ids: list[str] | None = Field(default=None, max_length=MAX_TASK_DOCUMENTS)
    assignee_ids: list[str] | None = Field(default=None, max_length=MAX_TASK_ASSIGNEES)
    """Replaces the assigned people; people who stay keep their own status."""
    assignee_id: str | None = None
    """Single assignee (older clients): replaces the assigned people with this one person."""
    due_date: date | None = None
    status: TaskStatus | None = None
    """Cancelled cancels the task; any other status sets it for everyone (and reopens a cancelled task)."""

    _strip = field_validator("title", "description", "subject_name", mode="before")(_clean)


class StatusChange(BaseModel):
    status: str
    person_id: str | None = Field(default=None, max_length=255)
    """Whose part to update; defaults to the current user. Only a manager updates someone else's."""


def _document_ref(d: TaskDocument) -> TaskDocumentRef:
    return TaskDocumentRef(
        sop_id=d.sop_id, kind=d.kind, sop_number=d.sop_number, title=d.title, version=d.version
    )


def _task_out(task: Task, user: CurrentUser, now: date) -> TaskOut:
    category = TaskCategory(task.category)
    editor = can_edit_task(user, task)
    mine = next((a for a in task.assignees if a.person_id == user.id), None)
    return TaskOut(
        id=task.id,
        reference=task.reference,
        category=category,
        category_label=TASK_CATEGORY_LABELS[category],
        study=StudyRef(id=task.study.id, protocol_number=task.study.protocol_number, title=task.study.title)
        if task.study
        else None,
        plan_item=PlanItemRef(external_id=task.plan_item_external_id, name=task.plan_item_name or "")
        if task.plan_item_external_id
        else None,
        subject_name=task.subject_name,
        documents=[_document_ref(d) for d in task.documents],
        title=task.title,
        description=task.description,
        assignees=[
            AssigneeOut(
                person_id=a.person_id,
                name=a.person_name,
                status=TaskStatus(a.status),
                completed_at=a.completed_at,
            )
            for a in task.assignees
        ],
        progress=TaskProgress(
            completed=sum(a.status == TaskStatus.COMPLETED.value for a in task.assignees),
            total=len(task.assignees),
        ),
        due_date=task.due_date,
        status=TaskStatus(task.status),
        my_status=TaskStatus(mine.status) if mine else None,
        own_task=_is_own_task(task),
        overdue=task_overdue(task.due_date, task.status, now),
        created_by_name=task.created_by_name,
        created_at=task.created_at,
        updated_at=task.updated_at,
        completed_at=task.completed_at,
        can_update_status=editor or mine is not None,
        can_edit=editor,
    )


def _about(task: Task) -> str:
    """Short description of what the task is about, for audit summaries."""
    category = TaskCategory(task.category)
    if category == TaskCategory.STUDY and task.study:
        return task.study.protocol_number
    if category == TaskCategory.SOP:
        return ", ".join(d.sop_number or d.title for d in task.documents)
    if category in (TaskCategory.VENDOR, TaskCategory.SYSTEM):
        return f"{TASK_CATEGORY_LABELS[category]}: {task.subject_name}"
    return TASK_CATEGORY_LABELS[category]


def _names(task: Task) -> str:
    return ", ".join(a.person_name for a in task.assignees)


def _get_task(db: Session, tenant_id: str, task_id: str) -> Task:
    task = db.scalars(
        select(Task)
        .where(Task.tenant_id == tenant_id, Task.id == task_id)
        .options(joinedload(Task.study), selectinload(Task.documents), selectinload(Task.assignees))
    ).first()
    if task is None:
        raise HTTPException(404, "Task not found.")
    return task


def _set_person_status(assignee: TaskAssignee, status: TaskStatus) -> None:
    assignee.status = status.value
    assignee.completed_at = datetime.now(UTC) if status == TaskStatus.COMPLETED else None


def _recompute(task: Task) -> None:
    """Overall status from everyone's status (a cancelled task stays cancelled)."""
    if task.status == TaskStatus.CANCELLED.value:
        return
    overall = overall_task_status([a.status for a in task.assignees])
    task.status = overall.value
    if overall == TaskStatus.COMPLETED:
        task.completed_at = task.completed_at or datetime.now(UTC)
    else:
        task.completed_at = None


def _people_or_422(ids: list[str]) -> list[Person]:
    unique = list(dict.fromkeys(i for i in ids if i))
    if not unique:
        raise HTTPException(422, "Choose at least one person.")
    if len(unique) > MAX_TASK_ASSIGNEES:
        raise HTTPException(422, f"A task can have at most {MAX_TASK_ASSIGNEES} people.")
    return [_person_or_422(i) for i in unique]


def _check_may_assign(user: CurrentUser, category: TaskCategory, people: list[Person]) -> None:
    """Managers of the category assign anyone; everyone else only themselves (never SOP tasks)."""
    if can_assign(user, category):
        return
    if category == TaskCategory.SOP:
        raise HTTPException(403, "Only QA and administrators create Procedures and SOPs tasks.")
    if not can_create_own(user, category):
        raise HTTPException(403, f"You cannot create {TASK_CATEGORY_LABELS[category]} tasks.")
    if [p.id for p in people] != [user.id]:
        raise HTTPException(403, f"You can create {TASK_CATEGORY_LABELS[category]} tasks for yourself only.")


def _set_assignees(task: Task, people: list[Person]) -> None:
    """People who stay keep their own status; new people start at Not started."""
    kept = {a.person_id: a for a in task.assignees}
    chosen = []
    for position, person in enumerate(people):
        assignee = kept.get(person.id) or TaskAssignee(
            person_id=person.id, person_name=person.name, status=TaskStatus.NOT_STARTED.value
        )
        assignee.position = position
        chosen.append(assignee)
    task.assignees = chosen


async def _approved_documents(
    ids: list[str], connector: SopConnector, db: Session, user: CurrentUser
) -> list[TaskDocument]:
    """Snapshots of the chosen SOPs/forms. Each must be in the live approved (Effective) list."""
    unique = list(dict.fromkeys(i.strip() for i in ids if i.strip()))
    if not unique:
        raise HTTPException(422, "Choose at least one approved SOP or form.")
    listed = (await connector.list_sops()).documents
    docs = {d.id: d for d in _with_details(listed, db, user, connector.info())}
    result = []
    for position, sop_id in enumerate(unique):
        doc = docs.get(sop_id)
        if doc is None or doc.status != SopStatus.EFFECTIVE or doc.kind == DocumentKind.OTHER:
            raise HTTPException(
                422,
                "Only approved SOPs and forms from the SOP library can be chosen. Refresh and try again.",
            )
        result.append(
            TaskDocument(
                position=position,
                sop_id=doc.id,
                kind=doc.kind.value,
                sop_number=doc.sop_number,
                title=doc.title,
                version=doc.version,
            )
        )
    return result


def _require_subject(category: TaskCategory, name: str | None) -> str:
    if not name:
        what = "vendor" if category == TaskCategory.VENDOR else "computer system"
        raise HTTPException(422, f"Enter the {what} name.")
    return name


@router.get("/tasks", response_model=TaskListResponse)
def list_tasks(
    db: Db,
    user: Reader,
    study_id: Annotated[str | None, Query(max_length=36)] = None,
    assignee: Annotated[str | None, Query(max_length=255, description='"me" or a person id')] = None,
    category: TaskCategory | None = None,
    sop_id: Annotated[str | None, Query(max_length=200, description="Tasks about this SOP/form")] = None,
    include_closed: bool = False,
) -> TaskListResponse:
    query = (
        select(Task)
        .where(Task.tenant_id == user.tenant_id)
        .options(joinedload(Task.study), selectinload(Task.documents), selectinload(Task.assignees))
    )
    if study_id:
        query = query.where(Task.study_id == study_id)
    if assignee:
        person = user.id if assignee == "me" else assignee
        query = query.where(Task.assignees.any(TaskAssignee.person_id == person))
    if category:
        query = query.where(Task.category == category.value)
    if sop_id:
        query = query.where(Task.documents.any(TaskDocument.sop_id == sop_id))
    if not include_closed:
        query = query.where(Task.status.not_in([s.value for s in TASK_CLOSED]))
    tasks = db.scalars(query.order_by(Task.due_date.is_(None), Task.due_date, Task.created_at)).all()
    now = today()
    return TaskListResponse(
        tasks=[_task_out(t, user, now) for t in tasks],
        can_manage=user.can(Permission.WORK_MANAGE),
        can_create=creatable_categories(user),
        can_assign=assignable_categories(user),
        categories=[CategoryOption(value=c, label=TASK_CATEGORY_LABELS[c]) for c in TaskCategory],
        statuses=[s.value for s in TaskStatus],
    )


@router.post("/tasks", response_model=TaskOut, status_code=201)
async def create_task(
    body: TaskCreate, request: Request, db: Db, user: Reader, connector: SopSource
) -> TaskOut:
    category = body.category
    if not (can_assign(user, category) or can_create_own(user, category)):
        if category == TaskCategory.SOP:
            raise HTTPException(403, "Only QA and administrators create Procedures and SOPs tasks.")
        raise HTTPException(403, f"You cannot create {TASK_CATEGORY_LABELS[category]} tasks.")
    people = _people_or_422([*body.assignee_ids, *([body.assignee_id] if body.assignee_id else [])])
    _check_may_assign(user, category, people)
    if category != TaskCategory.STUDY and (body.study_id or body.plan_item_id):
        raise HTTPException(422, "Only Study tasks are linked to a study.")
    if category != TaskCategory.SOP and body.document_ids:
        raise HTTPException(422, "Only Procedures and SOPs tasks are linked to SOPs.")
    if category not in (TaskCategory.VENDOR, TaskCategory.SYSTEM) and body.subject_name:
        raise HTTPException(422, "Only Vendor and Computer system tasks have a name.")

    study = None
    plan_item = None
    subject_name = None
    documents: list[TaskDocument] = []
    if category == TaskCategory.STUDY:
        if not body.study_id:
            raise HTTPException(422, "Choose a study.")
        study = _study_or_422(db, user.tenant_id, body.study_id)
        if body.plan_item_id:
            plan_item = db.scalars(
                select(StudyMilestone).where(
                    StudyMilestone.study_id == study.id, StudyMilestone.external_id == body.plan_item_id
                )
            ).first()
            if plan_item is None:
                raise HTTPException(422, "That milestone or task is not in this study's plan.")
            if plan_item.kind == "phase":
                raise HTTPException(
                    422, "Assign tasks to a milestone or task within the phase, not the phase heading."
                )
    elif category == TaskCategory.SOP:
        documents = await _approved_documents(body.document_ids, connector, db, user)
    elif category in (TaskCategory.VENDOR, TaskCategory.SYSTEM):
        subject_name = _require_subject(category, body.subject_name)

    task = Task(
        tenant_id=user.tenant_id,
        reference=_next_reference(db, Task, user.tenant_id, "TSK"),
        category=category.value,
        study_id=study.id if study else None,
        subject_name=subject_name,
        plan_item_external_id=plan_item.external_id if plan_item else None,
        plan_item_name=plan_item.name if plan_item else None,
        title=body.title,
        description=body.description,
        due_date=body.due_date,
        status=TaskStatus.NOT_STARTED.value,
        created_by_id=user.id,
        created_by_name=user.name,
        documents=documents,
    )
    _set_assignees(task, people)
    db.add(task)
    db.commit()
    task = _get_task(db, user.tenant_id, task.id)
    record_event(
        db,
        user,
        action="task.created",
        entity_type="task",
        entity_id=task.id,
        summary=f'Created {task.reference} "{task.title}" for {_names(task)} ({_about(task)})',
        details={
            "category": category.value,
            "study": study.protocol_number if study else None,
            "plan_item": plan_item.name if plan_item else None,
            "subject_name": subject_name,
            "documents": [f"{d.sop_number or d.title} v{d.version or '?'}" for d in task.documents],
            "assignees": [a.person_name for a in task.assignees],
            "own_task": _is_own_task(task),
            "due_date": str(body.due_date),
        },
        request=request,
    )
    return _task_out(task, user, today())


def _changes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {k: {"from": before[k], "to": after[k]} for k in after if before.get(k) != after[k]}


def _task_snapshot(task: Task) -> dict[str, Any]:
    return {
        "title": task.title,
        "description": task.description,
        "subject_name": task.subject_name,
        "documents": [d.sop_number or d.title for d in task.documents],
        "assignees": [a.person_name for a in task.assignees],
        "due_date": str(task.due_date) if task.due_date else None,
        "status": task.status,
    }


async def _replace_documents(
    task: Task, ids: list[str], connector: SopConnector, db: Session, user: CurrentUser
) -> None:
    """Keeps the original snapshot of SOPs already on the task; snapshots newly added ones."""
    wanted = list(dict.fromkeys(i.strip() for i in ids if i.strip()))
    if not wanted:
        raise HTTPException(422, "Choose at least one approved SOP or form.")
    kept = {d.sop_id: d for d in task.documents}
    if wanted == list(kept):
        return
    new_ids = [i for i in wanted if i not in kept]
    fresh = {d.sop_id: d for d in await _approved_documents(new_ids, connector, db, user)} if new_ids else {}
    chosen = [kept.get(i) or fresh[i] for i in wanted]
    for position, doc in enumerate(chosen):
        doc.position = position
    task.documents = chosen


def _set_overall(task: Task, status: TaskStatus) -> None:
    """Manager action: Cancelled cancels the task; any other status applies to everyone."""
    if status == TaskStatus.CANCELLED:
        task.status = TaskStatus.CANCELLED.value
        task.completed_at = None
        return
    task.status = TaskStatus.NOT_STARTED.value  # reopen if cancelled, then derive
    for assignee in task.assignees:
        _set_person_status(assignee, status)
    _recompute(task)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: ItemId, body: TaskUpdate, request: Request, db: Db, user: Reader, connector: SopSource
) -> TaskOut:
    task = _get_task(db, user.tenant_id, task_id)
    category = TaskCategory(task.category)
    if not can_edit_task(user, task):
        raise HTTPException(403, "Only the person who assigned this task, or an administrator, can edit it.")
    before = _task_snapshot(task)
    fields = body.model_fields_set
    if "title" in fields and body.title:
        task.title = body.title
    if "description" in fields:
        task.description = body.description
    if "subject_name" in fields:
        if category not in (TaskCategory.VENDOR, TaskCategory.SYSTEM):
            raise HTTPException(422, "Only Vendor and Computer system tasks have a name.")
        task.subject_name = _require_subject(category, body.subject_name)
    if "document_ids" in fields and body.document_ids is not None:
        if category != TaskCategory.SOP:
            raise HTTPException(422, "Only Procedures and SOPs tasks are linked to SOPs.")
        await _replace_documents(task, body.document_ids, connector, db, user)
    ids = body.assignee_ids if "assignee_ids" in fields else None
    if "assignee_id" in fields and body.assignee_id:
        ids = [body.assignee_id]
    if ids is not None:
        people = _people_or_422(ids)
        _check_may_assign(user, category, people)
        _set_assignees(task, people)
        _recompute(task)
    if "due_date" in fields:
        task.due_date = body.due_date
    if "status" in fields and body.status:
        _set_overall(task, body.status)
    changes = _changes(before, _task_snapshot(task))
    if changes:
        task.updated_at = datetime.now(UTC)
        db.commit()
        record_event(
            db,
            user,
            action="task.updated",
            entity_type="task",
            entity_id=task.id,
            summary=f"Updated {task.reference}: {', '.join(changes)}",
            details={"changes": changes},
            request=request,
        )
        task = _get_task(db, user.tenant_id, task.id)
    return _task_out(task, user, today())


@router.post("/tasks/{task_id}/status", response_model=TaskOut)
def change_task_status(
    task_id: ItemId, body: StatusChange, request: Request, db: Db, user: Reader
) -> TaskOut:
    """Each assigned person updates their own part. A manager may update anyone's, set everyone's
    (no person given and not assigned themselves) or cancel the task."""
    task = _get_task(db, user.tenant_id, task_id)
    editor = can_edit_task(user, task)
    try:
        status = TaskStatus(body.status)
    except ValueError:
        raise HTTPException(
            422, f"Status must be one of: {', '.join(s.value for s in TaskStatus)}."
        ) from None
    by_person = {a.person_id: a for a in task.assignees}
    target_id = body.person_id or (user.id if user.id in by_person else None)
    if not editor and (target_id != user.id or target_id not in by_person):
        raise HTTPException(403, "Only the people this task is assigned to can update its status.")
    if status == TaskStatus.CANCELLED and not editor:
        raise HTTPException(
            403, "Only the person who assigned this task, or an administrator, can cancel it."
        )
    if task.status == TaskStatus.CANCELLED.value and not editor:
        raise HTTPException(409, "This task was cancelled.")
    if target_id is not None and target_id not in by_person:
        raise HTTPException(422, "That person is not assigned to this task.")

    previous = task.status
    before = {a.person_id: a.status for a in task.assignees}
    if status == TaskStatus.CANCELLED or target_id is None:
        _set_overall(task, status)
        whose = "everyone"
    else:
        if task.status == TaskStatus.CANCELLED.value:
            task.status = TaskStatus.NOT_STARTED.value  # an editor reopens by updating someone
        _set_person_status(by_person[target_id], status)
        _recompute(task)
        whose = by_person[target_id].person_name
    changed = previous != task.status or before != {a.person_id: a.status for a in task.assignees}
    if changed:
        task.updated_at = datetime.now(UTC)
        db.commit()
        record_event(
            db,
            user,
            action="task.status_changed",
            entity_type="task",
            entity_id=task.id,
            summary=f"{task.reference} status changed from {previous} to {task.status}"
            + (f" ({whose}: {status.value})" if len(task.assignees) > 1 else ""),
            details={"from": previous, "to": task.status, "person": whose, "person_status": status.value},
            request=request,
        )
        task = _get_task(db, user.tenant_id, task.id)
    return _task_out(task, user, today())


# --- Risks and issues -------------------------------------------------------------------------


class RiskOut(BaseModel):
    id: str
    reference: str
    kind: RiskKind
    study: StudyRef
    title: str
    description: str | None
    likelihood: int
    impact: int
    score: int
    rating: str
    mitigation: str | None
    owner_id: str
    owner_name: str
    status: RiskStatus
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    can_update_status: bool


class SimpleTrialsIssueOut(BaseModel):
    """A SimpleTrials action item shown as a read-only issue (managed in SimpleTrials, not here)."""

    id: str
    number: str | None
    study: StudyRef
    site_number: str | None
    site_name: str | None
    category: str | None
    subcategory: str | None
    priority: str | None
    status: str | None
    closed: bool
    description: str | None
    response: str | None
    assignee: str | None
    opened_on: date | None
    due_on: date | None
    closed_on: date | None
    days_overdue: int | None
    """Calendar days past the due date, for open items (None when not overdue)."""


class RiskListResponse(BaseModel):
    risks: list[RiskOut]
    can_manage: bool
    statuses: list[str]
    simpletrials_issues: list[SimpleTrialsIssueOut] = []
    """Read-only issues from SimpleTrials (action items); empty when filtering by owner or by risks."""


class RiskCreate(BaseModel):
    study_id: str
    kind: RiskKind = RiskKind.RISK
    title: str = Field(min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    likelihood: int = Field(ge=1, le=3)
    impact: int = Field(ge=1, le=3)
    mitigation: str | None = Field(default=None, max_length=5000)
    owner_id: str

    _strip = field_validator("title", "description", "mitigation", mode="before")(_clean)


class RiskUpdate(BaseModel):
    kind: RiskKind | None = None
    title: str | None = Field(default=None, min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    likelihood: int | None = Field(default=None, ge=1, le=3)
    impact: int | None = Field(default=None, ge=1, le=3)
    mitigation: str | None = Field(default=None, max_length=5000)
    owner_id: str | None = None
    status: RiskStatus | None = None

    _strip = field_validator("title", "description", "mitigation", mode="before")(_clean)


def _risk_out(risk: Risk, user: CurrentUser) -> RiskOut:
    score = risk_score(risk.likelihood, risk.impact)
    return RiskOut(
        id=risk.id,
        reference=risk.reference,
        kind=RiskKind(risk.kind),
        study=StudyRef(id=risk.study.id, protocol_number=risk.study.protocol_number, title=risk.study.title),
        title=risk.title,
        description=risk.description,
        likelihood=risk.likelihood,
        impact=risk.impact,
        score=score,
        rating=risk_rating(score),
        mitigation=risk.mitigation,
        owner_id=risk.owner_id,
        owner_name=risk.owner_name,
        status=RiskStatus(risk.status),
        created_by_name=risk.created_by_name,
        created_at=risk.created_at,
        updated_at=risk.updated_at,
        closed_at=risk.closed_at,
        can_update_status=user.can(Permission.WORK_MANAGE) or risk.owner_id == user.id,
    )


def _get_risk(db: Session, tenant_id: str, risk_id: str) -> Risk:
    risk = db.scalars(
        select(Risk).where(Risk.tenant_id == tenant_id, Risk.id == risk_id).options(joinedload(Risk.study))
    ).first()
    if risk is None:
        raise HTTPException(404, "Risk or issue not found.")
    return risk


def _apply_risk_status(risk: Risk, status: RiskStatus) -> None:
    risk.status = status.value
    risk.closed_at = datetime.now(UTC) if status == RiskStatus.CLOSED else None


@router.get("/risks", response_model=RiskListResponse)
def list_risks(
    db: Db,
    user: Reader,
    study_id: Annotated[str | None, Query(max_length=36)] = None,
    kind: RiskKind | None = None,
    owner: Annotated[str | None, Query(max_length=255, description='"me" or a person id')] = None,
    include_closed: bool = False,
) -> RiskListResponse:
    query = select(Risk).where(Risk.tenant_id == user.tenant_id).options(joinedload(Risk.study))
    if study_id:
        query = query.where(Risk.study_id == study_id)
    if kind:
        query = query.where(Risk.kind == kind.value)
    if owner:
        query = query.where(Risk.owner_id == (user.id if owner == "me" else owner))
    if not include_closed:
        query = query.where(Risk.status != RiskStatus.CLOSED.value)
    risks = sorted(
        db.scalars(query).all(),
        key=lambda r: (-risk_score(r.likelihood, r.impact), r.created_at),
    )
    return RiskListResponse(
        risks=[_risk_out(r, user) for r in risks],
        can_manage=user.can(Permission.WORK_MANAGE),
        statuses=[s.value for s in RiskStatus],
        simpletrials_issues=(
            []
            if owner or kind == RiskKind.RISK
            else _simpletrials_issues(db, user.tenant_id, study_id, include_closed)
        ),
    )


def _simpletrials_issues(
    db: Session, tenant_id: str, study_id: str | None, include_closed: bool
) -> list[SimpleTrialsIssueOut]:
    """SimpleTrials action items as read-only issues: overdue first, then by due date."""
    query = (
        select(StudyActionItem)
        .join(Study)
        .where(Study.tenant_id == tenant_id, Study.in_source.is_(True))
        .options(joinedload(StudyActionItem.study))
    )
    if study_id:
        query = query.where(StudyActionItem.study_id == study_id)
    if not include_closed:
        query = query.where(StudyActionItem.closed.is_(False))
    now = today()
    out = [
        SimpleTrialsIssueOut(
            id=a.id,
            number=a.number,
            study=StudyRef(id=a.study.id, protocol_number=a.study.protocol_number, title=a.study.title),
            site_number=a.site_number,
            site_name=a.site_name,
            category=a.category,
            subcategory=a.subcategory,
            priority=a.priority,
            status=a.status,
            closed=a.closed,
            description=a.description,
            response=a.response,
            assignee=a.assignee,
            opened_on=a.opened_on,
            due_on=a.due_on,
            closed_on=a.closed_on,
            days_overdue=(now - a.due_on).days if a.due_on and not a.closed and a.due_on < now else None,
        )
        for a in db.scalars(query)
    ]
    return sorted(
        out,
        key=lambda i: (i.closed, -(i.days_overdue or 0), i.due_on or date.max, i.study.protocol_number),
    )


@router.post("/risks", response_model=RiskOut, status_code=201)
def create_risk(body: RiskCreate, request: Request, db: Db, user: Manager) -> RiskOut:
    study = _study_or_422(db, user.tenant_id, body.study_id)
    owner = _person_or_422(body.owner_id)
    risk = Risk(
        tenant_id=user.tenant_id,
        reference=_next_reference(db, Risk, user.tenant_id, "RSK" if body.kind == RiskKind.RISK else "ISS"),
        study_id=study.id,
        kind=body.kind.value,
        title=body.title,
        description=body.description,
        likelihood=body.likelihood,
        impact=body.impact,
        mitigation=body.mitigation,
        owner_id=owner.id,
        owner_name=owner.name,
        status=RiskStatus.OPEN.value,
        created_by_id=user.id,
        created_by_name=user.name,
    )
    db.add(risk)
    db.commit()
    record_event(
        db,
        user,
        action="risk.created",
        entity_type="risk",
        entity_id=risk.id,
        summary=f'Raised {risk.reference} "{risk.title}" owned by {owner.name} ({study.protocol_number})',
        details={
            "kind": body.kind.value,
            "study": study.protocol_number,
            "likelihood": body.likelihood,
            "impact": body.impact,
            "owner": owner.name,
        },
        request=request,
    )
    return _risk_out(_get_risk(db, user.tenant_id, risk.id), user)


def _risk_snapshot(risk: Risk) -> dict[str, Any]:
    return {
        "kind": risk.kind,
        "title": risk.title,
        "description": risk.description,
        "likelihood": risk.likelihood,
        "impact": risk.impact,
        "mitigation": risk.mitigation,
        "owner": risk.owner_name,
        "status": risk.status,
    }


@router.patch("/risks/{risk_id}", response_model=RiskOut)
def update_risk(risk_id: ItemId, body: RiskUpdate, request: Request, db: Db, user: Manager) -> RiskOut:
    risk = _get_risk(db, user.tenant_id, risk_id)
    before = _risk_snapshot(risk)
    fields = body.model_fields_set
    if "kind" in fields and body.kind:
        risk.kind = body.kind.value
    if "title" in fields and body.title:
        risk.title = body.title
    for name in ("description", "mitigation"):
        if name in fields:
            setattr(risk, name, getattr(body, name))
    if "likelihood" in fields and body.likelihood:
        risk.likelihood = body.likelihood
    if "impact" in fields and body.impact:
        risk.impact = body.impact
    if "owner_id" in fields and body.owner_id:
        person = _person_or_422(body.owner_id)
        risk.owner_id, risk.owner_name = person.id, person.name
    if "status" in fields and body.status:
        _apply_risk_status(risk, body.status)
    changes = _changes(before, _risk_snapshot(risk))
    if changes:
        risk.updated_at = datetime.now(UTC)
        db.commit()
        record_event(
            db,
            user,
            action="risk.updated",
            entity_type="risk",
            entity_id=risk.id,
            summary=f"Updated {risk.reference}: {', '.join(changes)}",
            details={"changes": changes},
            request=request,
        )
    return _risk_out(risk, user)


@router.post("/risks/{risk_id}/status", response_model=RiskOut)
def change_risk_status(
    risk_id: ItemId, body: StatusChange, request: Request, db: Db, user: Reader
) -> RiskOut:
    risk = _get_risk(db, user.tenant_id, risk_id)
    if not (user.can(Permission.WORK_MANAGE) or risk.owner_id == user.id):
        raise HTTPException(403, "Only the owner of this risk or issue can update its status.")
    try:
        status = RiskStatus(body.status)
    except ValueError:
        raise HTTPException(
            422, f"Status must be one of: {', '.join(s.value for s in RiskStatus)}."
        ) from None
    previous = risk.status
    if previous != status.value:
        _apply_risk_status(risk, status)
        risk.updated_at = datetime.now(UTC)
        db.commit()
        record_event(
            db,
            user,
            action="risk.status_changed",
            entity_type="risk",
            entity_id=risk.id,
            summary=f"{risk.reference} status changed from {previous} to {status.value}",
            details={"from": previous, "to": status.value},
            request=request,
        )
    return _risk_out(risk, user)
