"""Demo SimpleTrials data: fictional studies, labelled as demo everywhere they appear.

Dates are relative to today so the demo always shows a realistic mix of completed, due and overdue
milestones. None of these studies, sponsors, sites or people are real.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.studies.clock import today as app_today

from .models import (
    ActionItemRecord,
    DeviationRecord,
    EtmfDocumentRecord,
    MilestoneRecord,
    SiteRecord,
    StudyConnectorInfo,
    StudyRecord,
)


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
    t = today or app_today()  # the app's clock (APP_TIME_ZONE), not the computer's
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
        return with_demo_deviations(with_demo_action_items(with_demo_documents(demo_studies())))


# Demo eTMF structure: (section, folder, document name, expires).
_STUDY_DOCS: list[tuple[str, str, str, bool]] = [
    ("01. Trial Management", "Protocol", "Final Protocol", False),
    ("01. Trial Management", "Protocol", "Protocol Amendment 1", False),
    ("02. Central Trial Documents", "Investigator's Brochure", "Investigator's Brochure", False),
    ("03. Regulatory", "Regulatory Approval", "Regulatory Authority Approval", False),
    ("04. Ethics", "Ethics Approval", "Ethics Committee Approval", False),
    ("05. Safety Reporting", "Safety Plan", "Safety Management Plan", False),
]
_SITE_DOCS: list[tuple[str, str, str, bool]] = [
    ("01. General Site Documents", "Protocol", "Signed Protocol Signature Page", False),
    ("01. General Site Documents", "Logs", "Delegation of Duties Log", False),
    ("02. Site Personnel", "Investigator", "Principal Investigator CV", False),
    ("02. Site Personnel", "Investigator", "Principal Investigator GCP Certificate", True),
    ("02. Site Personnel", "Investigator", "Medical Licence", True),
    ("03. Site Ethics", "Approval", "Site Ethics Approval", False),
    ("03. Site Ethics", "Consent", "Approved Informed Consent Form", False),
    ("04. Site Agreements", "Contracts", "Clinical Trial Agreement", False),
    ("04. Site Agreements", "Contracts", "Site Budget", False),
    ("05. Monitoring", "Visit Reports", "Site Initiation Visit Report", False),
    ("05. Monitoring", "Visit Reports", "Monitoring Visit Report", False),
    ("06. Laboratory", "Laboratory", "Laboratory Normal Ranges", False),
    ("06. Laboratory", "Laboratory", "Laboratory Accreditation Certificate", True),
]
# Demo QC statuses (SimpleTrials' own values are shown as recorded when connected).
_QC = [None, "Approved", "Approved", "In review", "Pending", "Approved", "Rejected", None]
_EXPIRY_DAYS = [-12, 18, 40, 150, 400, 25, 260]


def _demo_doc(
    t: date, key: str, n: int, spec: tuple[str, str, str, bool], filed: bool, site: str | None
) -> EtmfDocumentRecord:
    section, folder, name, expires = spec
    if not filed:
        return EtmfDocumentRecord(
            external_id=key,
            level="site" if site else "study",
            site_external_id=site,
            section=section,
            folder=folder,
            name=name,
            filed=False,
            created_on=t - timedelta(days=300),
        )
    doc_day = t - timedelta(days=20 + (n * 37) % 260)
    delay = (n * 5) % 37  # calendar days from the document's date to filing
    qc = _QC[n % len(_QC)]
    expiry = t + timedelta(days=_EXPIRY_DAYS[n % len(_EXPIRY_DAYS)]) if expires else None
    return EtmfDocumentRecord(
        external_id=key,
        level="site" if site else "study",
        site_external_id=site,
        section=section,
        folder=folder,
        name=name,
        filed=True,
        doc_status="Final",
        qc_status=qc,
        qc_started_on=doc_day + timedelta(days=delay + 1) if qc else None,
        qc_ended_on=doc_day + timedelta(days=delay + 3) if qc in ("Approved", "Rejected") else None,
        created_on=t - timedelta(days=300),
        uploaded_on=doc_day + timedelta(days=delay),
        document_date=None if n % 11 == 0 else doc_day,
        expires_on=expiry,
        expired=expiry is not None and expiry < t,
        version="1.0",
    )


def with_demo_documents(studies: list[StudyRecord], today: date | None = None) -> list[StudyRecord]:
    """Adds demo eTMF metadata: expected documents per study and site, most filed at active sites."""
    t = today or app_today()  # the app's clock (APP_TIME_ZONE), not the computer's
    for si, study in enumerate(studies):
        docs: list[EtmfDocumentRecord] = []
        for j, spec in enumerate(_STUDY_DOCS):
            n = si * 31 + j
            docs.append(_demo_doc(t, f"{study.external_id}-D{j}", n, spec, filed=(n * 7) % 10 < 8, site=None))
        for k, site in enumerate(study.sites):
            share = 9 if site.activation_date else 3  # filed out of every 10 expected
            for j, spec in enumerate(_SITE_DOCS):
                n = si * 31 + k * 17 + j
                docs.append(
                    _demo_doc(
                        t,
                        f"{site.external_id}-D{j}",
                        n,
                        spec,
                        filed=(n * 7 + k) % 10 < share,
                        site=site.external_id,
                    )
                )
        study.documents = docs
    return studies


# Demo action items per study: (site index, category, subcategory, priority, description, opened days ago,
# due in days (negative = overdue), closed days ago or None).
_ACTIONS: list[tuple[int, str, str, str, str, int, int, int | None]] = [
    (0, "Site", "Site Visit", "High", "Demo: chase missing ISF delegation log signatures", 20, -6, None),
    (0, "Site", "Site Visit", "Normal", "Demo: confirm temperature log for IP storage", 9, 5, None),
    (1, "Site", "Site Visit", "Normal", "Demo: retrain staff on eCRF completion", 40, -20, 12),
]


def with_demo_action_items(studies: list[StudyRecord], today: date | None = None) -> list[StudyRecord]:
    """Adds demo SimpleTrials action items (read-only issues) to the first study."""
    t = today or app_today()
    if not studies:
        return studies
    first = studies[0]
    items: list[ActionItemRecord] = []
    for n, (site, category, sub, priority, text, opened, due, closed) in enumerate(_ACTIONS, start=1):
        s = first.sites[site] if site < len(first.sites) else None
        items.append(
            ActionItemRecord(
                external_id=f"{first.external_id}-A{n}",
                number=str(n),
                category=category,
                subcategory=sub,
                priority=priority,
                status="Closed" if closed is not None else "New",
                closed=closed is not None,
                site_number=s.site_number if s else None,
                site_name=s.name if s else None,
                description=text,
                assignee="Demo CRA",
                opened_on=_d(t, -opened),
                due_on=_d(t, due),
                closed_on=_d(t, -closed) if closed is not None else None,
            )
        )
    first.action_items = items
    for other in studies[1:]:
        other.action_items = []
    return studies


# Demo protocol deviations: (study index, site index, category, severity, description, occurred days ago,
# identified days after, closed days ago or None, subject level).
_DEVIATIONS: list[tuple[int, int, str, str, str, int, int, int | None, bool]] = [
    (0, 0, "Visit schedule", "Minor", "Demo: Day 7 visit outside the window", 150, 3, 120, True),
    (0, 0, "Informed consent", "Major", "Demo: re-consent to amendment 1 not obtained", 95, 10, None, True),
    (0, 0, "Procedures", "Minor", "Demo: ECG not done at screening", 60, 2, 40, True),
    (0, 1, "Eligibility", "Major", "Demo: enrolled with an exclusion lab value", 45, 20, None, True),
    (0, 1, "Visit schedule", "Minor", "Demo: Day 1 visit one day late", 30, 1, None, True),
    (0, 1, "Investigational product", "Critical", "Demo: IP stored too warm", 12, 1, None, False),
    (1, 0, "Procedures", "Minor", "Demo: vital signs taken after dosing", 70, 5, 50, True),
    (1, 0, "Visit schedule", "Minor", "Demo: unscheduled visit not recorded", 20, 4, None, True),
]  # fmt: skip


def with_demo_deviations(studies: list[StudyRecord], today: date | None = None) -> list[StudyRecord]:
    """Adds demo protocol deviations to the first two studies."""
    t = today or app_today()
    for study in studies:
        study.deviations = []
    for n, (si, site_i, category, severity, text, ago, found, closed, subject) in enumerate(_DEVIATIONS, 1):
        if si >= len(studies):
            continue
        study = studies[si]
        site = study.sites[site_i] if site_i < len(study.sites) else None
        assert study.deviations is not None
        study.deviations.append(
            DeviationRecord(
                external_id=f"{study.external_id}-PD{n}",
                number=f"PD-{n:03d}",
                site_external_id=site.external_id if site else None,
                site_number=site.site_number if site else None,
                site_name=site.name if site else None,
                category=category,
                severity=severity,
                status="Closed" if closed is not None else "Open",
                closed=closed is not None,
                description=text,
                subject_level=subject,
                occurred_on=_d(t, -ago),
                identified_on=_d(t, -ago + found),
                reported_on=_d(t, -ago + found + 2),
                closed_on=_d(t, -closed) if closed is not None else None,
                reportable=severity in ("Major", "Critical"),
            )
        )
    return studies
