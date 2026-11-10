"""Reports and Insights: the eTMF report (SimpleTrials document metadata only)."""

from __future__ import annotations

import asyncio
import io
from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth.rbac import Role
from app.connectors.simpletrials.mock import demo_studies, with_demo_documents
from app.connectors.simpletrials.models import (
    EtmfDocumentRecord,
    SiteRecord,
    StudyConnectorInfo,
    StudyRecord,
)
from app.reports.etmf import build_etmf, working_days
from app.studies.models import EtmfDocument, Study
from app.studies.sync import sync_studies

API = "/api/v1/reports/etmf"
TODAY = date(2026, 11, 9)  # a Monday


class ListConnector:
    def __init__(self, records: list[StudyRecord]) -> None:
        self.records = records

    def info(self) -> StudyConnectorInfo:
        return StudyConnectorInfo(mode="mock", mock_reason="test")

    async def fetch_studies(self) -> list[StudyRecord]:
        return self.records


def _doc(key: str, **kw: Any) -> EtmfDocumentRecord:
    base: dict[str, Any] = {
        "external_id": key,
        "level": "site",
        "section": "01. General",
        "name": key,
        "filed": True,
    }
    return EtmfDocumentRecord(**{**base, **kw})


def _record(documents: list[EtmfDocumentRecord] | None) -> StudyRecord:
    return StudyRecord(
        external_id="ST-1",
        protocol_number="P-1",
        title="Study one",
        sites=[
            SiteRecord(external_id="S-A", site_number="101", name="Alpha"),
            SiteRecord(external_id="S-B", site_number="102", name="Beta"),
        ],
        documents=documents,
    )


def _sync(db: Session, records: list[StudyRecord]) -> list[Study]:
    asyncio.run(sync_studies(db, ListConnector(records), tenant_id="avion", triggered_by="t"))
    return list(
        db.scalars(select(Study).options(selectinload(Study.sites), selectinload(Study.etmf_documents)))
    )


def test_working_days() -> None:
    friday = date(2026, 11, 6)
    assert working_days(friday, friday) == 0
    assert working_days(friday, date(2026, 11, 9)) == 1  # the weekend does not count
    assert working_days(friday, date(2026, 11, 13)) == 5
    assert working_days(friday, date(2026, 11, 16)) == 6
    assert working_days(date(2026, 11, 10), date(2026, 11, 3)) == 0  # filed before its date


class TestBuild:
    def test_completeness_heat_map_and_missing(self, db_session: Session) -> None:
        docs = [
            _doc("a1", site_external_id="S-A"),
            _doc("a2", site_external_id="S-A", filed=False, section="02. Personnel", folder="CVs"),
            _doc("b1", site_external_id="S-B", filed=False),
            _doc("b2", site_external_id="S-B", filed=False, section="02. Personnel"),
            _doc("s1", level="study", section="00. Study"),
        ]
        r = build_etmf(_sync(db_session, [_record(docs)]), TODAY)
        assert (r.overall.expected, r.overall.filed, r.overall.missing, r.overall.percent) == (5, 2, 3, 40.0)
        assert {t.key: t.value for t in r.tiles}["completeness"] == "40%"
        assert [(s.label, s.missing) for s in r.sites_missing] == [
            ("102 · Beta (P-1)", 2),
            ("101 · Alpha (P-1)", 1),
        ]
        assert r.sections == ["01. General", "02. Personnel"]  # site-level sections only
        alpha = next(h for h in r.heat_map if h.label == "101 · Alpha")
        assert [(c.filed, c.expected) for c in alpha.cells] == [(1, 1), (0, 1)]
        assert [(m.where, m.name) for m in r.missing_documents] == [
            ("101 · Alpha", "a2"),
            ("102 · Beta", "b1"),
            ("102 · Beta", "b2"),
        ]

    def test_site_filter(self, db_session: Session) -> None:
        studies = _sync(
            db_session, [_record([_doc("a1", site_external_id="S-A"), _doc("b1", site_external_id="S-B")])]
        )
        beta = next(s for s in studies[0].sites if s.site_number == "102")
        r = build_etmf(studies, TODAY, site_id=beta.id)
        assert r.overall.expected == 1 and [h.label for h in r.heat_map] == ["102 · Beta"]

    def test_qc_timeliness_and_expiry(self, db_session: Session) -> None:
        friday = date(2026, 10, 30)
        docs = [
            _doc(
                "on-time",
                site_external_id="S-A",
                document_date=friday,
                uploaded_on=friday + timedelta(days=7),
            ),
            _doc(
                "late", site_external_id="S-A", document_date=friday, uploaded_on=friday + timedelta(days=10)
            ),
            _doc("undated", site_external_id="S-A", uploaded_on=friday, qc_status="in_review"),
            _doc("qc-done", site_external_id="S-A", qc_ended_on=friday),
            _doc("expired", site_external_id="S-A", expires_on=TODAY - timedelta(days=3), expired=True),
            _doc("soon", site_external_id="S-B", expires_on=TODAY + timedelta(days=30)),
            _doc("later", site_external_id="S-B", expires_on=TODAY + timedelta(days=90)),
            _doc("placeholder-expiry", site_external_id="S-B", filed=False, expires_on=TODAY),
        ]
        r = build_etmf(_sync(db_session, [_record(docs)]), TODAY)
        timeliness = {b.key: b.count for b in r.timeliness}
        assert timeliness["on_time"] == 1 and timeliness["late_10"] == 1
        assert r.timeliness_measured == 2 and r.timeliness_on_time == 1
        assert timeliness["no_date"] == 5
        qc = {b.label: b.count for b in r.qc}
        assert qc == {"In review": 1, "QC complete": 1, "No QC recorded": 5}
        assert r.qc[-1].label == "No QC recorded"
        assert [(e.name, e.state, e.days) for e in r.expiring] == [
            ("expired", "expired", -3),
            ("soon", "expiring", 30),
        ]
        assert {t.key: t.note for t in r.tiles}["expiring"] == "1 already expired"


class TestSync:
    def test_documents_are_replaced_and_kept_when_unreadable(self, db_session: Session) -> None:
        _sync(db_session, [_record([_doc("a1"), _doc("a2")])])
        assert len(db_session.scalars(select(EtmfDocument)).all()) == 2
        _sync(db_session, [_record([_doc("a1")])])
        assert [d.external_id for d in db_session.scalars(select(EtmfDocument))] == ["a1"]
        # documents=None: SimpleTrials did not return eTMF data this time; keep the last copy.
        _sync(db_session, [_record(None)])
        assert [d.external_id for d in db_session.scalars(select(EtmfDocument))] == ["a1"]

    def test_demo_documents(self) -> None:
        studies = with_demo_documents(demo_studies(TODAY), TODAY)
        docs = [d for s in studies for d in (s.documents or [])]
        assert docs and any(not d.filed for d in docs) and any(d.expires_on for d in docs)
        assert {d.level for d in docs} == {"study", "site"}


class TestApi:
    def test_demo_report(self, client: TestClient) -> None:
        r = client.get(API).json()
        assert r["has_documents"] is True and r["source"]["mode"] == "mock"
        assert r["overall"]["expected"] > r["overall"]["filed"] > 0
        assert len(r["heat_map"]) == sum(len(s["cells"]) > 0 for s in r["heat_map"])
        assert {b["key"] for b in r["timeliness"]} == {
            "on_time",
            "late_10",
            "late_20",
            "late_more",
            "no_date",
        }

    def test_filters_and_access(self, make_client: Any) -> None:
        viewer = make_client(Role.VIEWER)
        all_ = viewer.get(API).json()
        study = all_["by_study"][0]
        one = viewer.get(API, params={"study_id": study["key"]}).json()
        assert [s["label"] for s in one["by_study"]] == [study["label"]]
        assert one["overall"]["expected"] == study["expected"]
        assert viewer.get(API, params={"site_id": "bad"}).status_code == 422

    def test_excel_export_lists_missing_documents_and_is_audited(self, client: TestClient) -> None:
        r = client.get(API).json()
        res = client.get(f"{API}/export.xlsx")
        assert res.status_code == 200
        assert res.headers["content-disposition"].startswith('attachment; filename="eTMF ')
        book = load_workbook(io.BytesIO(res.content))
        assert book.sheetnames[:5] == [
            "Missing documents",
            "Completeness by study",
            "By site and section",
            "Expiring documents",
            "QC and timeliness",
        ]
        assert book["Missing documents"].max_row == 1 + r["overall"]["missing"]
        events = client.get("/api/v1/audit-events").json()["items"]
        assert any(e["action"] == "report.exported" and e["entity_id"] == "etmf" for e in events)
