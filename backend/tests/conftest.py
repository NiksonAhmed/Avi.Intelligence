from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

# Isolate tests from any developer .env before app modules read settings.
os.environ["APP_ENV"] = "test"
os.environ["SHAREPOINT_MODE"] = "mock"
os.environ["SIMPLETRIALS_MODE"] = "mock"  # tests never call the real SimpleTrials API
os.environ["VIEDOC_MODE"] = "mock"  # ... nor a real Viedoc study (the demo study is used)
os.environ["CONFERENCES_MODE"] = "mock"  # ... nor the BD SharePoint list (demo conferences)
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["USE_SYSTEM_TRUST_STORE"] = "false"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.api.assistant import get_llm_client  # noqa: E402
from app.audit import models as _audit_models  # noqa: E402,F401
from app.auth import rbac  # noqa: E402
from app.connectors.sharepoint import get_sop_connector  # noqa: E402
from app.connectors.sharepoint.mock import MockSopConnector  # noqa: E402
from app.connectors.simpletrials import get_study_connector  # noqa: E402
from app.connectors.simpletrials.mock import MockStudyConnector  # noqa: E402
from app.data_management import models as _dm_models  # noqa: E402,F401
from app.db.session import Base, get_db  # noqa: E402
from app.knowledge import models as _knowledge_models  # noqa: E402,F401
from app.main import create_app  # noqa: E402
from app.reports import models as _report_models  # noqa: E402,F401
from app.studies import models as _study_models  # noqa: E402,F401


@pytest.fixture
def db_session() -> Iterator[Session]:
    from sqlalchemy import create_engine

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def make_client(db_session: Session):  # type: ignore[no-untyped-def]
    def _make(role: rbac.Role = rbac.Role.ADMIN, user_id: str | None = None) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_db] = lambda: db_session
        connector = MockSopConnector("test")
        app.dependency_overrides[get_sop_connector] = lambda: connector
        studies = MockStudyConnector("test")
        app.dependency_overrides[get_study_connector] = lambda: studies
        app.dependency_overrides[get_llm_client] = lambda: None  # search-only unless a test overrides
        app.dependency_overrides[rbac.get_current_user] = lambda: rbac.CurrentUser(
            id=user_id or f"user-{role.value}", name=f"Test {role.value}", email="t@example.com", role=role
        )
        return TestClient(app)

    return _make


@pytest.fixture
def client(make_client) -> TestClient:  # type: ignore[no-untyped-def]
    return make_client()
