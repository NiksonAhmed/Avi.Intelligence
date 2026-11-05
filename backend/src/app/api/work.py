"""Tasks, risks and issues (managed in Avi.Intelligence).

Access rules (agreed with Avion):
  * Everyone with study access can view all tasks and risks (read-only).
  * Only administrators (`work.manage`) can create, assign or edit them.
  * The person a task is assigned to, or the owner of a risk, may update its status.
Nothing is deleted: a task is cancelled and a risk is closed instead, and every change is audited.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.audit.service import record_event
from app.auth.directory import Person, get_person, list_people
from app.auth.rbac import CurrentUser, Permission, require
from app.db.session import get_db
from app.studies.clock import today
from app.studies.models import Risk, Study, Task
from app.studies.rules import (
    TASK_CLOSED,
    RiskKind,
    RiskStatus,
    TaskStatus,
    risk_rating,
    risk_score,
    task_overdue,
)

router = APIRouter(tags=["Tasks and risks"])

ItemId = Annotated[str, Path(pattern=r"^[0-9a-f\-]{36}$")]
Db = Annotated[Session, Depends(get_db)]
Reader = Annotated[CurrentUser, Depends(require(Permission.STUDY_READ))]
Manager = Annotated[CurrentUser, Depends(require(Permission.WORK_MANAGE))]


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


class TaskOut(BaseModel):
    id: str
    reference: str
    study: StudyRef
    title: str
    description: str | None
    assignee_id: str
    assignee_name: str
    due_date: date | None
    status: TaskStatus
    overdue: bool
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    can_update_status: bool


class TaskListResponse(BaseModel):
    tasks: list[TaskOut]
    can_manage: bool
    statuses: list[str]


class TaskCreate(BaseModel):
    study_id: str
    title: str = Field(min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    assignee_id: str
    due_date: date | None = None

    _strip = field_validator("title", "description", mode="before")(_clean)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    assignee_id: str | None = None
    due_date: date | None = None
    status: TaskStatus | None = None

    _strip = field_validator("title", "description", mode="before")(_clean)


class StatusChange(BaseModel):
    status: str


def _task_out(task: Task, user: CurrentUser, now: date) -> TaskOut:
    return TaskOut(
        id=task.id,
        reference=task.reference,
        study=StudyRef(id=task.study.id, protocol_number=task.study.protocol_number, title=task.study.title),
        title=task.title,
        description=task.description,
        assignee_id=task.assignee_id,
        assignee_name=task.assignee_name,
        due_date=task.due_date,
        status=TaskStatus(task.status),
        overdue=task_overdue(task.due_date, task.status, now),
        created_by_name=task.created_by_name,
        created_at=task.created_at,
        updated_at=task.updated_at,
        completed_at=task.completed_at,
        can_update_status=user.can(Permission.WORK_MANAGE) or task.assignee_id == user.id,
    )


def _get_task(db: Session, tenant_id: str, task_id: str) -> Task:
    task = db.scalars(
        select(Task).where(Task.tenant_id == tenant_id, Task.id == task_id).options(joinedload(Task.study))
    ).first()
    if task is None:
        raise HTTPException(404, "Task not found.")
    return task


def _apply_task_status(task: Task, status: TaskStatus) -> None:
    task.status = status.value
    task.completed_at = datetime.now(UTC) if status == TaskStatus.COMPLETED else None


@router.get("/tasks", response_model=TaskListResponse)
def list_tasks(
    db: Db,
    user: Reader,
    study_id: Annotated[str | None, Query(max_length=36)] = None,
    assignee: Annotated[str | None, Query(max_length=255, description='"me" or a person id')] = None,
    include_closed: bool = False,
) -> TaskListResponse:
    query = select(Task).where(Task.tenant_id == user.tenant_id).options(joinedload(Task.study))
    if study_id:
        query = query.where(Task.study_id == study_id)
    if assignee:
        query = query.where(Task.assignee_id == (user.id if assignee == "me" else assignee))
    if not include_closed:
        query = query.where(Task.status.not_in([s.value for s in TASK_CLOSED]))
    tasks = db.scalars(query.order_by(Task.due_date.is_(None), Task.due_date, Task.created_at)).all()
    now = today()
    return TaskListResponse(
        tasks=[_task_out(t, user, now) for t in tasks],
        can_manage=user.can(Permission.WORK_MANAGE),
        statuses=[s.value for s in TaskStatus],
    )


@router.post("/tasks", response_model=TaskOut, status_code=201)
def create_task(body: TaskCreate, request: Request, db: Db, user: Manager) -> TaskOut:
    study = _study_or_422(db, user.tenant_id, body.study_id)
    assignee = _person_or_422(body.assignee_id)
    task = Task(
        tenant_id=user.tenant_id,
        reference=_next_reference(db, Task, user.tenant_id, "TSK"),
        study_id=study.id,
        title=body.title,
        description=body.description,
        assignee_id=assignee.id,
        assignee_name=assignee.name,
        due_date=body.due_date,
        status=TaskStatus.NOT_STARTED.value,
        created_by_id=user.id,
        created_by_name=user.name,
    )
    db.add(task)
    db.commit()
    record_event(
        db,
        user,
        action="task.created",
        entity_type="task",
        entity_id=task.id,
        summary=f'Created {task.reference} "{task.title}" for {assignee.name} ({study.protocol_number})',
        details={"study": study.protocol_number, "assignee": assignee.name, "due_date": str(body.due_date)},
        request=request,
    )
    return _task_out(_get_task(db, user.tenant_id, task.id), user, today())


def _changes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {k: {"from": before[k], "to": after[k]} for k in after if before.get(k) != after[k]}


def _task_snapshot(task: Task) -> dict[str, Any]:
    return {
        "title": task.title,
        "description": task.description,
        "assignee": task.assignee_name,
        "due_date": str(task.due_date) if task.due_date else None,
        "status": task.status,
    }


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: ItemId, body: TaskUpdate, request: Request, db: Db, user: Manager) -> TaskOut:
    task = _get_task(db, user.tenant_id, task_id)
    before = _task_snapshot(task)
    fields = body.model_fields_set
    if "title" in fields and body.title:
        task.title = body.title
    if "description" in fields:
        task.description = body.description
    if "assignee_id" in fields and body.assignee_id:
        person = _person_or_422(body.assignee_id)
        task.assignee_id, task.assignee_name = person.id, person.name
    if "due_date" in fields:
        task.due_date = body.due_date
    if "status" in fields and body.status:
        _apply_task_status(task, body.status)
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
    return _task_out(task, user, today())


@router.post("/tasks/{task_id}/status", response_model=TaskOut)
def change_task_status(
    task_id: ItemId, body: StatusChange, request: Request, db: Db, user: Reader
) -> TaskOut:
    task = _get_task(db, user.tenant_id, task_id)
    if not (user.can(Permission.WORK_MANAGE) or task.assignee_id == user.id):
        raise HTTPException(403, "Only the person this task is assigned to can update its status.")
    try:
        status = TaskStatus(body.status)
    except ValueError:
        raise HTTPException(
            422, f"Status must be one of: {', '.join(s.value for s in TaskStatus)}."
        ) from None
    if status == TaskStatus.CANCELLED and not user.can(Permission.WORK_MANAGE):
        raise HTTPException(403, "Only an administrator can cancel a task.")
    previous = task.status
    if previous != status.value:
        _apply_task_status(task, status)
        task.updated_at = datetime.now(UTC)
        db.commit()
        record_event(
            db,
            user,
            action="task.status_changed",
            entity_type="task",
            entity_id=task.id,
            summary=f"{task.reference} status changed from {previous} to {status.value}",
            details={"from": previous, "to": status.value},
            request=request,
        )
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


class RiskListResponse(BaseModel):
    risks: list[RiskOut]
    can_manage: bool
    statuses: list[str]


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
