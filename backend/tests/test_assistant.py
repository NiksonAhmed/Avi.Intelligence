from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.assistant.service import AssistantUnavailable, answer_question
from app.auth.rbac import CurrentUser, Role
from app.connectors.sharepoint.mock import MockSopConnector
from app.core.config import Settings

USER = CurrentUser(id="u1", name="Test User", email="t@example.com", role=Role.CRA)


def cite(doc: int, start: int, end: int, text: str = "cited") -> SimpleNamespace:
    return SimpleNamespace(
        type="content_block_location",
        document_index=doc,
        start_block_index=start,
        end_block_index=end,
        cited_text=text,
        document_title="x",
    )


def text_block(text: str, citations: list[SimpleNamespace] | None = None) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text, citations=citations)


class FakeClient:
    """Stands in for anthropic.AsyncAnthropic: records requests, returns a canned response."""

    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._response = response
        self._error = error
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return self._response


def make_response(content: list[Any], stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        model="claude-opus-5-5",
        usage=SimpleNamespace(input_tokens=1200, output_tokens=150),
    )


def ask(db: Session, client: Any, question: str = "What happens at the site initiation visit?") -> Any:
    return asyncio.run(
        answer_question(
            db=db,
            user=USER,
            question=question,
            connector=MockSopConnector("test"),
            client=client,
            settings=Settings(),
        )
    )


def test_search_only_mode_returns_passages_without_ai(db_session: Session) -> None:
    result = ask(db_session, None)
    assert result.mode == "search-only"
    assert result.segments == [] and result.excerpts
    assert result.excerpts[0].sop_number == "SOP-011"
    assert "not switched on" in (result.notice or "")
    assert result.demo is True


def test_no_matching_passages(db_session: Session) -> None:
    result = ask(db_session, FakeClient(), question="xylophone quasar")
    assert result.outcome == "no-sources" and result.notice


def test_ai_answer_with_numbered_citations(db_session: Session) -> None:
    response = make_response(
        [
            SimpleNamespace(type="thinking", thinking=""),
            text_block("The CRA conducts the SIV using the checklist", [cite(0, 0, 1, "The CRA conducts")]),
            text_block(". "),
            text_block("Staff must complete training", [cite(0, 0, 1), cite(0, 1, 2, "training")]),
        ]
    )
    client = FakeClient(response)
    result = ask(db_session, client)

    assert result.mode == "ai" and result.outcome == "answered"
    assert [s.citations for s in result.segments] == [[1], [], [1, 2]]
    assert [c.number for c in result.citations] == [1, 2]
    assert result.citations[0].sop_number == "SOP-011"
    assert result.citations[0].sop_id == "demo-sop-011"
    assert result.notice is None

    request = client.calls[0]
    assert request["model"] == "claude-opus-5-5"
    assert request["fallbacks"] == "default"
    assert request["betas"] == ["server-side-fallback-2026-07-01"]
    assert request["output_config"] == {"effort": "medium"}
    assert "Answer only from these passages" in request["system"]
    content = request["messages"][0]["content"]
    docs = [b for b in content if b["type"] == "document"]
    assert docs and all(d["citations"] == {"enabled": True} for d in docs)
    assert docs[0]["source"]["type"] == "content"
    assert content[-1] == {"type": "text", "text": "What happens at the site initiation visit?"}


def test_out_of_range_citations_are_ignored(db_session: Session) -> None:
    result = ask(db_session, FakeClient(make_response([text_block("x", [cite(99, 0, 1)])])))
    assert result.citations == [] and "no citations" in (result.notice or "")


def test_refusal_falls_back_to_passages(db_session: Session) -> None:
    result = ask(db_session, FakeClient(make_response([], stop_reason="refusal")))
    assert result.outcome == "refused" and result.excerpts and "declined" in (result.notice or "")


def test_api_errors_become_assistant_unavailable(db_session: Session) -> None:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    error = anthropic.AuthenticationError(
        "bad key", response=httpx2.Response(401, request=request), body=None
    )
    with pytest.raises(AssistantUnavailable, match="API key was rejected"):
        ask(db_session, FakeClient(error=error))


def test_interactions_are_recorded(db_session: Session) -> None:
    from app.knowledge.models import AssistantInteraction

    ask(db_session, None)
    rows = db_session.query(AssistantInteraction).all()
    assert len(rows) == 1 and rows[0].mode == "search-only" and rows[0].citations


# ---- API ---------------------------------------------------------------------------------------


def test_status_and_ask_endpoint_search_only(client: TestClient) -> None:
    status = client.get("/api/v1/assistant/status").json()
    assert status["ai_enabled"] is False and status["demo"] is True

    res = client.post("/api/v1/assistant/ask", json={"question": "How fast are SAEs reported?"})
    assert res.status_code == 200
    body = res.json()
    assert body["mode"] == "search-only"
    assert body["excerpts"][0]["sop_number"] == "SOP-030"

    status = client.get("/api/v1/assistant/status").json()
    assert status["documents"] == 11 and status["suggested_questions"]

    audit = client.get("/api/v1/audit-events").json()["items"]
    assert audit[0]["action"] == "assistant.asked"


def test_ask_validates_question(client: TestClient) -> None:
    assert client.post("/api/v1/assistant/ask", json={"question": "  "}).status_code == 422
    assert client.post("/api/v1/assistant/ask", json={"question": "x" * 2001}).status_code == 422


def test_ask_returns_503_when_ai_unavailable(make_client) -> None:  # type: ignore[no-untyped-def]
    from app.api.assistant import get_llm_client

    c = make_client()
    c.app.dependency_overrides[get_llm_client] = lambda: FakeClient(
        error=anthropic.APIConnectionError(
            request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
        )
    )
    res = c.post("/api/v1/assistant/ask", json={"question": "site initiation visit"})
    assert res.status_code == 503
    assert "Could not reach the AI service" in res.json()["detail"]


def test_viewer_can_ask_but_only_admin_reindexes(make_client) -> None:  # type: ignore[no-untyped-def]
    viewer = make_client(Role.VIEWER)
    assert viewer.post("/api/v1/assistant/ask", json={"question": "site activation"}).status_code == 200
    assert viewer.post("/api/v1/assistant/reindex").status_code == 403
    res = make_client(Role.ADMIN).post("/api/v1/assistant/reindex")
    assert res.status_code == 200
    assert len(res.json()["documents"]) == 11
