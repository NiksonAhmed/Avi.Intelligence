"""eTMF report: completeness, missing documents by site, site x section heat map, QC, filing timeliness
and expiring documents.

Pure calculations over the read-only copy of SimpleTrials eTMF document metadata (never the files).
"Expected" means SimpleTrials' placeholders (agreed with Avion): a placeholder is an expected document
not yet filed. Every figure follows a rule in `ETMF_RULES`.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel

from app.studies.models import EtmfDocument, Study, StudySite

from .study_delivery import Option, Tile

FILING_TARGET_DAYS = 5
EXPIRY_WINDOW_DAYS = 60
TOP_SITES = 10

ETMF_RULES = {
    "completeness": (
        "Completeness: filed documents out of expected documents. Expected = every document SimpleTrials "
        "expects, i.e. filed documents plus placeholders not yet filed. Superseded versions are not counted."
    ),
    "heat_map": "Each cell: the share of a site's expected documents in that TMF section that are filed.",
    "qc": (
        "QC status as recorded in SimpleTrials for filed documents. 'No QC recorded' means SimpleTrials "
        "holds no QC status or QC dates for the document."
    ),
    "timeliness": (
        f"Filing timeliness: working days (Monday to Friday) from the document's own date (signature "
        f"date, else version date) to the day it was filed. Target: within {FILING_TARGET_DAYS} working "
        "days. Documents without a date of their own cannot be measured and are shown separately."
    ),
    "expiring": (
        f"Expired, or expiring within {EXPIRY_WINDOW_DAYS} days: filed documents with an expiry date "
        "in SimpleTrials (e.g. licences, GCP certificates, lab accreditation)."
    ),
}


class Completeness(BaseModel):
    key: str
    label: str
    expected: int = 0
    filed: int = 0
    missing: int = 0
    percent: float | None = None


class HeatRow(BaseModel):
    site_id: str
    label: str
    protocol_number: str
    cells: list[Completeness]


class QcBucket(BaseModel):
    label: str
    count: int


class TimelinessBucket(BaseModel):
    key: str
    label: str
    count: int


class ExpiringDocument(BaseModel):
    id: str
    name: str
    protocol_number: str
    where: str
    """The site, or "Study level"."""
    expires_on: date
    days: int
    """Days until expiry (negative: expired that many days ago)."""
    state: Literal["expired", "expiring"]


class MissingDocument(BaseModel):
    protocol_number: str
    where: str
    section: str
    folder: str | None
    name: str


class Etmf(BaseModel):
    tiles: list[Tile]
    overall: Completeness
    by_study: list[Completeness]
    sites_missing: list[Completeness]
    sections: list[str]
    heat_map: list[HeatRow]
    qc: list[QcBucket]
    timeliness: list[TimelinessBucket]
    timeliness_measured: int
    timeliness_on_time: int
    expiring: list[ExpiringDocument]
    missing_documents: list[MissingDocument]
    has_documents: bool
    study_options: list[Option]
    site_options: list[Option]
    rules: dict[str, str]


def working_days(start: date, end: date) -> int:
    """Weekdays after `start` up to and including `end` (0 when filed on or before the document date)."""
    if end <= start:
        return 0
    days = (end - start).days
    weeks, extra = divmod(days, 7)
    count = weeks * 5
    for i in range(1, extra + 1):
        if (start + timedelta(days=weeks * 7 + i)).weekday() < 5:
            count += 1
    return count


def _tally(row: Completeness, docs: list[EtmfDocument]) -> Completeness:
    row.expected = len(docs)
    row.filed = sum(d.filed for d in docs)
    row.missing = row.expected - row.filed
    row.percent = round(row.filed / row.expected * 100, 1) if row.expected else None
    return row


def _qc_label(d: EtmfDocument) -> str:
    if d.qc_status:
        return d.qc_status.replace("_", " ").strip().capitalize()
    if d.qc_ended_on:
        return "QC complete"
    if d.qc_started_on:
        return "In QC"
    return "No QC recorded"


def _site_label(site: StudySite) -> str:
    return f"{site.site_number} · {site.name}"


def build_etmf(
    studies: list[Study], today: date, *, study_id: str | None = None, site_id: str | None = None
) -> Etmf:
    study_options = [Option(id=s.id, label=f"{s.protocol_number} · {s.title}") for s in studies]
    scoped = [s for s in studies if not study_id or s.id == study_id]
    site_options = [
        Option(id=site.id, label=f"{_site_label(site)} ({s.protocol_number})")
        for s in scoped
        for site in s.sites
    ]

    # Documents in scope, with their study and site.
    rows: list[tuple[Study, StudySite | None, EtmfDocument]] = []
    for s in scoped:
        sites = {site.external_id: site for site in s.sites}
        for d in s.etmf_documents:
            site = sites.get(d.site_external_id or "")
            if site_id and (site is None or site.id != site_id):
                continue
            rows.append((s, site, d))
    docs = [d for _s, _site, d in rows]
    overall = _tally(Completeness(key="all", label="All documents"), docs)

    by_study = [
        _tally(Completeness(key=s.id, label=s.protocol_number), [d for st, _site, d in rows if st.id == s.id])
        for s in scoped
    ]

    # ---- sites: most missing first, and the site x section heat map ----
    site_docs: dict[str, tuple[Study, StudySite, list[EtmfDocument]]] = {}
    for s, site, d in rows:
        if site is not None:
            site_docs.setdefault(site.id, (s, site, []))[2].append(d)
    sites_all = [
        _tally(Completeness(key=site.id, label=f"{_site_label(site)} ({s.protocol_number})"), ds)
        for s, site, ds in site_docs.values()
    ]
    sites_missing = sorted(
        (r for r in sites_all if r.missing), key=lambda r: (-r.missing, r.percent or 0, r.label)
    )[:TOP_SITES]
    sections = sorted({d.section for _s, site, d in rows if site is not None})
    heat_map = [
        HeatRow(
            site_id=site.id,
            label=_site_label(site),
            protocol_number=s.protocol_number,
            cells=[
                _tally(Completeness(key=sec, label=sec), [d for d in ds if d.section == sec])
                for sec in sections
            ],
        )
        for s, site, ds in sorted(site_docs.values(), key=lambda v: (v[0].protocol_number, v[1].site_number))
    ]

    # ---- QC pipeline (filed documents) ----
    filed = [(s, site, d) for s, site, d in rows if d.filed]
    qc_counts: dict[str, int] = {}
    for _s, _site, d in filed:
        label = _qc_label(d)
        qc_counts[label] = qc_counts.get(label, 0) + 1
    qc = sorted(
        (QcBucket(label=k, count=v) for k, v in qc_counts.items()),
        key=lambda b: (b.label == "No QC recorded", -b.count, b.label),
    )

    # ---- filing timeliness ----
    buckets = {
        "on_time": TimelinessBucket(
            key="on_time", label=f"Within {FILING_TARGET_DAYS} working days", count=0
        ),
        "late_10": TimelinessBucket(key="late_10", label="6–10 working days", count=0),
        "late_20": TimelinessBucket(key="late_20", label="11–20 working days", count=0),
        "late_more": TimelinessBucket(key="late_more", label="More than 20 working days", count=0),
        "no_date": TimelinessBucket(key="no_date", label="No document date", count=0),
    }
    for _s, _site, d in filed:
        if d.document_date is None or d.uploaded_on is None:
            buckets["no_date"].count += 1
            continue
        days = working_days(d.document_date, d.uploaded_on)
        key = (
            "on_time"
            if days <= FILING_TARGET_DAYS
            else "late_10"
            if days <= 10
            else "late_20"
            if days <= 20
            else "late_more"
        )
        buckets[key].count += 1
    measured = sum(b.count for k, b in buckets.items() if k != "no_date")
    on_time = buckets["on_time"].count

    # ---- expiring documents ----
    horizon = today + timedelta(days=EXPIRY_WINDOW_DAYS)
    expiring = sorted(
        (
            ExpiringDocument(
                id=d.id,
                name=d.name,
                protocol_number=s.protocol_number,
                where=_site_label(site) if site is not None else "Study level",
                expires_on=d.expires_on,
                days=(d.expires_on - today).days,
                state="expired" if d.expired or d.expires_on < today else "expiring",
            )
            for s, site, d in filed
            if d.expires_on is not None and (d.expired or d.expires_on <= horizon)
        ),
        key=lambda e: (e.expires_on, e.name),
    )

    missing_documents = sorted(
        (
            MissingDocument(
                protocol_number=s.protocol_number,
                where=_site_label(site) if site is not None else "Study level",
                section=d.section,
                folder=d.folder,
                name=d.name,
            )
            for s, site, d in rows
            if not d.filed
        ),
        key=lambda m: (m.protocol_number, m.where != "Study level", m.where, m.section, m.name),
    )

    # ---- headline tiles ----
    expired = sum(e.state == "expired" for e in expiring)
    tiles = [
        Tile(
            key="completeness",
            label="eTMF completeness",
            value=f"{overall.percent:g}%" if overall.percent is not None else "—",
            note=f"{overall.filed} of {overall.expected} expected documents filed",
            tone="info",
        ),
        Tile(
            key="missing",
            label="Missing documents",
            value=str(overall.missing),
            note="Expected (placeholder) but not yet filed",
            tone="warn" if overall.missing else "good",
        ),
        Tile(
            key="on_time",
            label=f"Filed within {FILING_TARGET_DAYS} working days",
            value=f"{on_time} of {measured}" if measured else "—",
            note=f"{buckets['no_date'].count} filed without a document date"
            if buckets["no_date"].count
            else "Of filed documents with a date",
            tone="neutral",
        ),
        Tile(
            key="expiring",
            label=f"Expired or expiring in {EXPIRY_WINDOW_DAYS} days",
            value=str(len(expiring)),
            note=f"{expired} already expired" if expired else "None expired",
            tone="bad" if expired else ("warn" if expiring else "good"),
        ),
    ]
    return Etmf(
        tiles=tiles,
        overall=overall,
        by_study=by_study,
        sites_missing=sites_missing,
        sections=sections,
        heat_map=heat_map,
        qc=qc,
        timeliness=list(buckets.values()),
        timeliness_measured=measured,
        timeliness_on_time=on_time,
        expiring=expiring,
        missing_documents=missing_documents,
        has_documents=any(s.etmf_documents for s in studies),
        study_options=study_options,
        site_options=site_options,
        rules=ETMF_RULES,
    )
