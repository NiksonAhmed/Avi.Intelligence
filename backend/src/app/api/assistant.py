"""Ask Avi.Intelligence endpoints."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.studies import current_source_label, study_source
from app.assistant import topics
from app.assistant.service import (
    AskResponse,
    AssistantUnavailable,
    answer_question,
    answer_study_question,
    build_client,
    record_lookup_answer,
)
from app.assistant.study_questions import STUDY_QUESTIONS, about_procedures, understand
from app.assistant.study_tools import load_study_data
from app.audit.service import record_event
from app.auth.rbac import CurrentUser, Permission, require
from app.connectors.sharepoint import get_sop_connector
from app.connectors.sharepoint.models import SopConnector
from app.connectors.simpletrials import get_study_connector
from app.connectors.simpletrials.models import StudyConnector
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.knowledge.indexer import index_stats, refresh_index
from app.knowledge.models import KnowledgeDocument
from app.studies.clock import today
from app.studies.sync import ensure_synced

router = APIRouter(prefix="/assistant", tags=["Assistant"])

Connector = Annotated[SopConnector, Depends(get_sop_connector)]
Studies = Annotated[StudyConnector, Depends(get_study_connector)]
Db = Annotated[Session, Depends(get_db)]


@lru_cache
def _cached_client() -> Any | None:
    return build_client(get_settings())


def get_llm_client() -> Any | None:
    """Anthropic client, or None when no API key is configured (search-only mode)."""
    return _cached_client()


LlmClient = Annotated[Any | None, Depends(get_llm_client)]


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)

    @field_validator("question")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Question is too short.")
        return v


class IndexedDocument(BaseModel):
    sop_number: str | None
    title: str
    version: str | None
    passages: int
    error: str | None


class AssistantStatus(BaseModel):
    ai_enabled: bool
    model: str | None
    demo: bool
    documents: int
    passages: int
    failed: int
    last_indexed_at: datetime | None
    suggested_questions: list[str]
    study_questions: list[str]
    """Example study questions (empty when the user cannot see studies)."""


class ReindexResponse(BaseModel):
    indexed: int
    unchanged: int
    removed: int
    failed: list[dict[str, str]]
    documents: list[IndexedDocument]


def _suggestions(db: Session, tenant_id: str) -> list[str]:
    docs = db.scalars(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.tenant_id == tenant_id, KnowledgeDocument.chunk_count > 0)
        .order_by(KnowledgeDocument.chunk_count.desc(), KnowledgeDocument.sop_number)
        .limit(4)
    ).all()
    return [f"What are the key steps in {d.sop_number + ' ' if d.sop_number else ''}{d.title}?" for d in docs]


@router.get("/status", response_model=AssistantStatus)
def status(
    db: Db,
    connector: Connector,
    client: LlmClient,
    user: Annotated[CurrentUser, Depends(require(Permission.ASSISTANT_USE))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssistantStatus:
    stats = index_stats(db, user.tenant_id)
    return AssistantStatus(
        ai_enabled=client is not None,
        model=settings.assistant_model if client is not None else None,
        demo=connector.info().mode == "mock",
        documents=stats.documents,
        passages=stats.passages,
        failed=stats.failed,
        last_indexed_at=stats.last_indexed_at,
        suggested_questions=_suggestions(db, user.tenant_id),
        study_questions=_work_questions(user, settings),
    )


def _work_questions(user: CurrentUser, settings: Settings) -> list[str]:
    """Example questions about the person's work, for the areas they can see."""
    out = list(STUDY_QUESTIONS) if user.can(Permission.STUDY_READ) else []
    if settings.conferences_enabled and user.can(Permission.CONFERENCE_VIEW):
        out.append("When is the next conference?")
    if settings.data_management_enabled and user.can(Permission.DM_VIEW):
        out += ["How many queries are open?", "What is our SDV progress?"]
    return out


async def _study_answer(
    db: Session, studies: StudyConnector, user: CurrentUser, question: str
) -> AskResponse | None:
    """A study answer when the question is about studies and the user may see them; else None (SOPs)."""
    if not user.can(Permission.STUDY_READ):
        return None
    await ensure_synced(db, studies, user.tenant_id)
    info = study_source(db, studies, user.tenant_id)
    data = load_study_data(
        db, user.tenant_id, current_source_label(studies), today(), info.last_successful_sync_at, user.id
    )
    parsed = understand(question, data)
    if parsed is None:
        return None
    return answer_study_question(
        db=db, user=user, question=question, parsed=parsed, data=data, demo=studies.info().mode == "mock"
    )


async def _topic_answer(db: Session, user: CurrentUser, question: str, demo: bool) -> AskResponse | None:
    """A module's answer (Conferences, Data Management...) when the question is about its area."""
    if about_procedures(question):
        return None
    for topic in topics.matching(question):
        result = await topic.answer(db, user, question)
        if result is not None:
            return record_lookup_answer(db=db, user=user, question=question, result=result, demo=demo)
    return None


@router.post("/ask", response_model=AskResponse)
async def ask(
    body: AskRequest,
    request: Request,
    db: Db,
    connector: Connector,
    studies: Studies,
    client: LlmClient,
    user: Annotated[CurrentUser, Depends(require(Permission.ASSISTANT_USE))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AskResponse:
    result = await _topic_answer(db, user, body.question, demo=studies.info().mode == "mock")
    if result is None:
        result = await _study_answer(db, studies, user, body.question)
    if result is None:
        try:
            result = await answer_question(
                db=db,
                user=user,
                question=body.question,
                connector=connector,
                client=client,
                settings=settings,
            )
        except AssistantUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
    if result.study is not None:
        record_event(
            db,
            user,
            action="assistant.asked",
            entity_type="assistant_interaction",
            entity_id=result.interaction_id,
            summary=f"Asked: {body.question[:200]}",
            details={
                "kind": "study",
                "mode": result.mode,
                "intent": result.study.intent,
                "understood": result.study.understood,
            },
            request=request,
        )
        return result
    record_event(
        db,
        user,
        action="assistant.asked",
        entity_type="assistant_interaction",
        entity_id=result.interaction_id,
        summary=f"Asked: {body.question[:200]}",
        details={
            "mode": result.mode,
            "outcome": result.outcome,
            "model": result.model,
            "cited_sops": sorted({c.sop_number or c.title for c in result.citations}),
        },
        request=request,
    )
    return result


@router.post("/reindex", response_model=ReindexResponse)
async def reindex(
    request: Request,
    db: Db,
    connector: Connector,
    user: Annotated[CurrentUser, Depends(require(Permission.CONNECTOR_MANAGE))],
) -> ReindexResponse:
    result = await refresh_index(db, connector, user.tenant_id)
    record_event(
        db,
        user,
        action="assistant.reindexed",
        entity_type="knowledge_index",
        entity_id=None,
        summary=f"Re-indexed SOPs for the assistant ({result.indexed} updated, {len(result.failed)} failed)",
        details={
            "indexed": result.indexed,
            "unchanged": result.unchanged,
            "removed": result.removed,
            "failed": result.failed,
        },
        request=request,
    )
    docs = db.scalars(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.tenant_id == user.tenant_id)
        .order_by(KnowledgeDocument.sop_number)
    ).all()
    return ReindexResponse(
        indexed=result.indexed,
        unchanged=result.unchanged,
        removed=result.removed,
        failed=result.failed,
        documents=[
            IndexedDocument(
                sop_number=d.sop_number,
                title=d.title,
                version=d.version,
                passages=d.chunk_count,
                error=d.error,
            )
            for d in docs
        ],
    )
