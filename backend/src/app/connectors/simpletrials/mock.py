"""Demo SimpleTrials data: fictional studies, labelled as demo everywhere they appear.

Dates are relative to today so the demo always shows a realistic mix of completed, due and overdue
milestones. None of these studies, sponsors, sites or people are real.
"""

from __future__ import annotations

from datetime import date, timedelta

from .models import MilestoneRecord, SiteRecord, StudyConnectorInfo, StudyRecord


def _d(today: date, days: int | None) -> date | None:
    return None if days is None else today + timedelta(days=days)


def _milestones(
    prefix: str, today: date, plan: list[tuple[str, int | None, int | None]]
) -> list[MilestoneRecord]:
    return [
        MilestoneRecord(
            external_id=f"{prefix}-M{i + 1}",
            name=name,
            planned_date=_d(today, planned),
            actual_date=_d(today, actual),
            is_key=True,
        )
        for i, (name, planned, actual) in enumerate(plan)
    ]


def demo_studies(today: date | None = None) -> list[StudyRecord]:
    t = today or date.today()
    return [
        StudyRecord(
            external_id="DEMO-ST-1001",
            protocol_number="DEMO-ONC-301",
            title="Phase III study of an investigational oral therapy in advanced solid tumours",
            sponsor="Demo Sponsor A",
            phase="Phase III",
            therapeutic_area="Oncology",
            status="Enrolling",
            countries=["Australia", "New Zealand"],
            project_manager="Demo PM One",
            enrolment_target=120,
            sites=[
                SiteRecord(
                    external_id="DEMO-S-101",
                    site_number="101",
                    name="Demo Hospital North",
                    country="Australia",
                    principal_investigator="Dr Demo Investigator A",
                    status="Enrolling",
                    activation_target=_d(t, -215),
                    activation_date=_d(t, -210),
                    enrolled=31,
                    enrolment_target=40,
                ),
                SiteRecord(
                    external_id="DEMO-S-102",
                    site_number="102",
                    name="Demo Cancer Centre",
                    country="Australia",
                    principal_investigator="Dr Demo Investigator B",
                    status="Enrolling",
                    activation_target=_d(t, -185),
                    activation_date=_d(t, -180),
                    enrolled=22,
                    enrolment_target=40,
                ),
                SiteRecord(
                    external_id="DEMO-S-201",
                    site_number="201",
                    name="Demo Clinic Auckland",
                    country="New Zealand",
                    principal_investigator="Dr Demo Investigator C",
                    status="Activated",
                    activation_target=_d(t, -30),
                    activation_date=_d(t, -20),
                    enrolled=0,
                    enrolment_target=40,
                ),
            ],
            milestones=_milestones(
                "DEMO-ST-1001",
                t,
                [
                    ("First site activated", -215, -210),
                    ("First patient in", -190, -186),
                    ("50% enrolled", -10, None),
                    ("Last patient in", 150, None),
                    ("Database lock", 330, None),
                ],
            ),
        ),
        StudyRecord(
            external_id="DEMO-ST-1002",
            protocol_number="DEMO-CV-201",
            title="Phase II dose-finding study in heart failure with reduced ejection fraction",
            sponsor="Demo Sponsor B",
            phase="Phase II",
            therapeutic_area="Cardiology",
            status="Start-up",
            countries=["Australia"],
            project_manager="Demo PM Two",
            enrolment_target=60,
            sites=[
                SiteRecord(
                    external_id="DEMO-S-301",
                    site_number="301",
                    name="Demo Heart Institute",
                    country="Australia",
                    principal_investigator="Dr Demo Investigator D",
                    status="Contracting",
                    activation_target=_d(t, 20),
                ),
                SiteRecord(
                    external_id="DEMO-S-302",
                    site_number="302",
                    name="Demo General Hospital",
                    country="Australia",
                    principal_investigator="Dr Demo Investigator E",
                    status="Ethics submitted",
                    activation_target=_d(t, -5),
                ),
            ],
            milestones=_milestones(
                "DEMO-ST-1002",
                t,
                [
                    ("Protocol final", -60, -58),
                    ("Ethics approval", 12, None),
                    ("First site activated", 45, None),
                    ("First patient in", 75, None),
                ],
            ),
        ),
        StudyRecord(
            external_id="DEMO-ST-1003",
            protocol_number="DEMO-NEU-101",
            title="Phase I first-in-human study of an investigational compound in healthy volunteers",
            sponsor="Demo Sponsor C",
            phase="Phase I",
            therapeutic_area="Neurology",
            status="Close-out",
            countries=["Australia"],
            project_manager="Demo PM One",
            enrolment_target=48,
            sites=[
                SiteRecord(
                    external_id="DEMO-S-401",
                    site_number="401",
                    name="Demo Phase I Unit",
                    country="Australia",
                    principal_investigator="Dr Demo Investigator F",
                    status="Closed",
                    activation_target=_d(t, -400),
                    activation_date=_d(t, -400),
                    enrolled=48,
                    enrolment_target=48,
                ),
            ],
            milestones=_milestones(
                "DEMO-ST-1003",
                t,
                [
                    ("First patient in", -380, -379),
                    ("Last patient in", -120, -125),
                    ("Last patient last visit", -60, -61),
                    ("Database lock", -5, None),
                    ("Clinical study report", 80, None),
                ],
            ),
        ),
        StudyRecord(
            external_id="DEMO-ST-1004",
            protocol_number="DEMO-RES-202",
            title="Phase II study of an inhaled investigational product in moderate asthma",
            sponsor="Demo Sponsor A",
            phase="Phase II",
            therapeutic_area="Respiratory",
            status="Enrolling",
            countries=["Australia"],
            project_manager="Demo PM Two",
            enrolment_target=None,  # deliberately missing: the UI must say so rather than guess
            sites=[
                SiteRecord(
                    external_id="DEMO-S-501",
                    site_number="501",
                    name="Demo Respiratory Clinic",
                    country="Australia",
                    principal_investigator="Dr Demo Investigator G",
                    status="Enrolling",
                    activation_target=_d(t, -95),
                    activation_date=_d(t, -90),
                    enrolled=9,
                ),
            ],
            milestones=_milestones(
                "DEMO-ST-1004",
                t,
                [
                    ("First site activated", -95, -90),
                    ("First patient in", -70, -64),
                    ("Last patient in", None, None),
                ],
            ),
        ),
    ]


class MockStudyConnector:
    def __init__(self, reason: str) -> None:
        self._reason = reason

    def info(self) -> StudyConnectorInfo:
        return StudyConnectorInfo(mode="mock", mock_reason=self._reason)

    async def fetch_studies(self) -> list[StudyRecord]:
        return demo_studies()
