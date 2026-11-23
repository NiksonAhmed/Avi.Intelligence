"""The site validation lists in SharePoint, read-only through Microsoft Graph.

Three lists (see docs/site-validation-setup.md): Sites (one row per site: details, equipment, phantoms and
QA/QC, image transfer), Validations (one row per equipment and isotope) and Phantom scans. Set
SITE_VALIDATION_SITES_LIST (and the other two list names), SITE_VALIDATION_SHAREPOINT_SITE_URL if the lists
are not on the SOP site; the Entra app needs read access to that site. Each field accepts several likely
column names; SITE_VALIDATION_FIELD_MAP (JSON, e.g. {"sites.city": "Suburb"}) names the real ones.
"""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import quote

from app.connectors.sharepoint.graph_client import GraphClient, site_lookup_path

from .geo import locate, short_state
from .models import (
    Equipment,
    EquipmentKind,
    ImageTransfer,
    PhantomScan,
    QaQc,
    ScanStatus,
    SiteRecord,
    SiteSourceInfo,
    Validation,
)

_KIT = {"pet": EquipmentKind.PET_CT, "spect": EquipmentKind.SPECT_CT, "dc": EquipmentKind.DOSE_CALIBRATOR,
        "gc": EquipmentKind.GAMMA_COUNTER}  # fmt: skip
_KIT_COLUMN = {"pet": "PET", "spect": "SPECT", "dc": "DoseCalibrator", "gc": "GammaCounter"}


def _defaults() -> dict[str, list[str]]:
    f: dict[str, list[str]] = {
        "sites.name": ["Title", "SiteName", "NameofSite", "Name_x0020_of_x0020_Site"],
        "sites.department": ["Department"],
        "sites.city": ["City", "Suburb", "Town"],
        "sites.state": ["State"],
        "sites.latitude": ["Latitude", "Lat"],
        "sites.longitude": ["Longitude", "Lon", "Long"],
        "sites.last_survey": [
            "LastSurveyReturnDate",
            "LastSurvey",
            "Last_x0020_Survey_x0020_Return_x0020_Date",
        ],
        "sites.artnet": ["ARTnetAccreditation", "ARTnet", "ARTNetAccreditation"],
        "sites.physicist": ["SitePhysicist", "Physicist", "PhysName"],
        "sites.radiopharmacy": ["Radiopharmacy", "HotLab", "RadiopharmacyHotLab"],
        "sites.licensed": ["LicensedFor", "LicensedIsotopes", "Licences"],
        "sites.phantoms": ["Phantoms", "PhantomAvailability", "Phantom_x0020_Availability"],
        "sites.used_for_study_scans": ["PhantomUsedForStudyScans", "UsedForStudyScans"],
        "sites.records_access": ["QAQCRecordsAccess", "AccessToQAQCRecords"],
        "sites.monthly_submission": ["QAQCMonthly", "SubmitQAQCMonthly"],
        "sites.daily_qc_storage": ["DailyQCStorage", "DailyQCData"],
        "sites.routine_pet": ["QAQCRoutinePETCT", "QAQCRoutinePET"],
        "sites.routine_spect": ["QAQCRoutineSPECTCT", "QAQCRoutineSPECT"],
        "sites.routine_ct": ["QAQCRoutineCT"],
        "sites.routine_mri": ["QAQCRoutineMRI"],
        "sites.pacs": ["PACS", "PACSSystem"],
        "sites.dicom_export": ["DICOMExport", "ExportDICOM"],
        "sites.transfer_methods": ["TransferMethods", "DataTransfer"],
        "validations.site": ["Site", "SiteName", "Title"],
        "validations.equipment": ["Equipment"],
        "validations.isotope": ["Isotope", "Radioisotope"],
        "validations.validated_by": ["ValidatedBy", "CertifiedBy"],
        "validations.validated_on": ["ValidatedOn", "CertificationDate", "DateOfCertification"],
        "validations.files_available": ["FilesAvailable", "CertificateOnFile", "FilesOnFile"],
        "validations.next_review": ["NextReview", "NextReviewDate"],
        "scans.site": ["Site", "SiteName", "Title"],
        "scans.study": ["Study", "Protocol"],
        "scans.equipment": ["Equipment"],
        "scans.isotope": ["Isotope", "Radioisotope"],
        "scans.status": ["Status", "ScanStatus"],
        "scans.on": ["ScanDate", "Date", "StatusDate"],
    }
    for key, col in _KIT_COLUMN.items():
        for field, suffix in (("has", "OnSite"), ("manufacturer", "Manufacturer"), ("model", "Model"),
                              ("installed", "Installed"), ("last_calibration", "LastCalibration"),
                              ("maintenance", "Maintenance"), ("replacement", "Replacement")):  # fmt: skip
            f[f"sites.{key}_{field}"] = [f"{col}{suffix}", f"{key.upper()}{suffix}"]
    return f


DEFAULT_FIELDS = _defaults()


def parse_field_map(raw_json: str | None) -> dict[str, list[str]]:
    fields = {k: list(v) for k, v in DEFAULT_FIELDS.items()}
    if not raw_json:
        return fields
    raw = json.loads(raw_json)
    if not isinstance(raw, dict):
        raise ValueError("SITE_VALIDATION_FIELD_MAP must be a JSON object.")
    for key, value in raw.items():
        if key not in DEFAULT_FIELDS:
            raise ValueError(f'SITE_VALIDATION_FIELD_MAP has unknown field "{key}".')
        names = value if isinstance(value, list) else [value]
        fields[key] = [str(n) for n in names] + fields[key]
    return fields


# ---- reading SharePoint values -----------------------------------------------------------------------------


def _text(value: Any, limit: int = 500) -> str | None:
    if isinstance(value, dict):  # hyperlink / lookup columns
        value = value.get("LookupValue") or value.get("Description") or value.get("Url")
    if isinstance(value, list):  # multi-choice / multi-lookup columns
        value = ", ".join(str(v.get("LookupValue", v)) if isinstance(v, dict) else str(v) for v in value)
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text[:limit] or None


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        items = [_text(v) for v in value]
    else:
        items = [s.strip() for s in re.split(r"[;,\n]", _text(value, 2000) or "")]
    return [i for i in items if i]


def _date(value: Any) -> date | None:
    if isinstance(value, str) and len(value) >= 10:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _yes(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = (_text(value) or "").lower()
    if text.startswith(("y", "true", "1")):
        return True
    if text.startswith(("n", "false", "0")):
        return False
    return None


def _float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def equipment_of(value: Any) -> EquipmentKind | None:
    text = (_text(value) or "").lower()
    if "spect" in text:
        return EquipmentKind.SPECT_CT
    if "pet" in text:
        return EquipmentKind.PET_CT
    if "dose" in text or "calibrator" in text or text == "dc":
        return EquipmentKind.DOSE_CALIBRATOR
    if "gamma" in text or text == "gc":
        return EquipmentKind.GAMMA_COUNTER
    return None


def isotope_of(value: Any) -> str | None:
    """'Cu-64', '64Cu', '[64Cu]', 'Cu64' -> '64Cu'. The tracker's '117Lu' is 177Lu."""
    text = re.sub(r"[\s\[\]\-()]", "", _text(value) or "")
    m = re.fullmatch(r"(\d+)([A-Za-z]{1,2})|([A-Za-z]{1,2})(\d+)", text)
    if not m:
        return None
    mass, element = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
    iso = f"{mass}{element.capitalize()}"
    return "177Lu" if iso == "117Lu" else iso


_SCAN_WORDS = [
    ("fail", ScanStatus.FAILED),
    ("pass", ScanStatus.PASSED),
    ("submit", ScanStatus.SUBMITTED),
    ("scanned", ScanStatus.SCANNED),
    ("acquired", ScanStatus.SCANNED),
    ("book", ScanStatus.BOOKED),
    ("schedul", ScanStatus.BOOKED),
]


def scan_status_of(value: Any) -> ScanStatus | None:
    text = (_text(value) or "").lower()
    for word, status in _SCAN_WORDS:
        if word in text:
            return status
    return None


def _picker(item: dict[str, Any], fields: dict[str, list[str]]):  # type: ignore[no-untyped-def]
    values: dict[str, Any] = item.get("fields") or {}

    def pick(key: str) -> Any:
        for name in fields[key]:
            if values.get(name) not in (None, "", []):
                return values[name]
        return None

    return pick


def map_site(item: dict[str, Any], fields: dict[str, list[str]]) -> SiteRecord | None:
    pick = _picker(item, fields)
    name = _text(pick("sites.name"), 200)
    city, state = _text(pick("sites.city"), 120), _text(pick("sites.state"), 60)
    lat, lon = _float(pick("sites.latitude")), _float(pick("sites.longitude"))
    place = (lat, lon) if lat is not None and lon is not None else locate(city, state)
    if not name or place is None:
        return None  # not a usable site row (no name, or nowhere to put it on the map)
    equipment = []
    for key, kind in _KIT.items():
        maker = _text(pick(f"sites.{key}_manufacturer"), 120)
        if not (_yes(pick(f"sites.{key}_has")) or maker):
            continue
        equipment.append(
            Equipment(
                kind=kind,
                manufacturer=maker,
                model=_text(pick(f"sites.{key}_model"), 200),
                installed=_date(pick(f"sites.{key}_installed")),
                last_calibration=_date(pick(f"sites.{key}_last_calibration")),
                maintenance=_text(pick(f"sites.{key}_maintenance"), 200),
                replacement=_text(pick(f"sites.{key}_replacement"), 300),
            )
        )
    scanners = (("PET/CT", "pet"), ("SPECT/CT", "spect"), ("CT", "ct"), ("MRI", "mri"))
    routines = {label: r for label, key in scanners if (r := _text(pick(f"sites.routine_{key}"), 1000))}
    return SiteRecord(
        id=str(item.get("id")),
        name=name,
        department=_text(pick("sites.department"), 120),
        city=city or "",
        state=short_state(state),
        lat=place[0],
        lon=place[1],
        last_survey=_date(pick("sites.last_survey")),
        artnet_accreditation=_text(pick("sites.artnet"), 200),
        physicist=_text(pick("sites.physicist"), 200),
        radiopharmacy=_yes(pick("sites.radiopharmacy")),
        licensed=[i for i in (isotope_of(x) for x in _list(pick("sites.licensed"))) if i],
        equipment=equipment,
        qa=QaQc(
            phantoms=_list(pick("sites.phantoms")),
            used_for_study_scans=_text(pick("sites.used_for_study_scans"), 200),
            records_access=_text(pick("sites.records_access"), 200),
            monthly_submission=_text(pick("sites.monthly_submission"), 200),
            daily_qc_storage=_text(pick("sites.daily_qc_storage"), 300),
            routines=routines,
        ),
        transfer=ImageTransfer(
            pacs=_text(pick("sites.pacs"), 200),
            dicom_export=_text(pick("sites.dicom_export"), 120),
            methods=_list(pick("sites.transfer_methods")),
        ),
        source_url=_text(item.get("webUrl"), 1000),
    )


def _site_key(value: Any) -> str:
    return (_text(value) or "").strip().lower()


def map_validation(item: dict[str, Any], fields: dict[str, list[str]]) -> tuple[str, Validation] | None:
    pick = _picker(item, fields)
    kind, iso = equipment_of(pick("validations.equipment")), isotope_of(pick("validations.isotope"))
    on = _date(pick("validations.validated_on"))
    site = _site_key(pick("validations.site"))
    if not (site and kind and iso and on):
        return None
    return site, Validation(
        equipment=kind,
        isotope=iso,
        validated_by=_text(pick("validations.validated_by"), 120) or "Not recorded",
        validated_on=on,
        files_available=bool(_yes(pick("validations.files_available"))),
        next_review=_date(pick("validations.next_review")),
    )


def map_scan(item: dict[str, Any], fields: dict[str, list[str]]) -> tuple[str, PhantomScan] | None:
    pick = _picker(item, fields)
    kind, iso = equipment_of(pick("scans.equipment")), isotope_of(pick("scans.isotope"))
    status, on = scan_status_of(pick("scans.status")), _date(pick("scans.on"))
    site = _site_key(pick("scans.site"))
    if not (site and kind and iso and status and on):
        return None
    return site, PhantomScan(
        study=_text(pick("scans.study"), 120) or "Not recorded",
        equipment=kind,
        isotope=iso,
        status=status,
        on=on,
    )


class SharePointSiteSource:
    def __init__(
        self,
        client: GraphClient,
        *,
        site_url: str,
        sites_list: str,
        validations_list: str | None,
        scans_list: str | None,
        fields: dict[str, list[str]],
        cache_seconds: int,
    ) -> None:
        self._client, self._site_url = client, site_url
        self._lists = (sites_list, validations_list, scans_list)
        self._fields, self._cache_seconds = fields, cache_seconds
        self._cache: list[SiteRecord] | None = None
        self._expires = 0.0
        self._fetched_at: datetime | None = None
        self.skipped: dict[str, int] = {}
        """Rows that could not be used, per list (shown in Administration)."""

    def info(self) -> SiteSourceInfo:
        return SiteSourceInfo(mode="sharepoint", fetched_at=self._fetched_at)

    def lists(self) -> tuple[str, str | None, str | None]:
        return self._lists

    async def _items(self, site_id: str, name: str | None) -> list[dict[str, Any]]:
        if not name:
            return []
        return await self._client.get_all(
            f"/sites/{site_id}/lists/{quote(name)}/items?$expand=fields&$top=200"
        )

    async def list_sites(self, *, force_refresh: bool = False) -> list[SiteRecord]:
        if self._cache is not None and not force_refresh and time.monotonic() < self._expires:
            return self._cache
        site = await self._client.get(site_lookup_path(self._site_url))
        sites_list, validations_list, scans_list = self._lists
        raw_sites = await self._items(site["id"], sites_list)
        raw_vals = await self._items(site["id"], validations_list)
        raw_scans = await self._items(site["id"], scans_list)
        sites = [s for s in (map_site(i, self._fields) for i in raw_sites) if s is not None]
        by_name = {s.name.strip().lower(): s for s in sites}
        vals = [v for v in (map_validation(i, self._fields) for i in raw_vals) if v is not None]
        scans = [s for s in (map_scan(i, self._fields) for i in raw_scans) if s is not None]
        unmatched = 0
        for key, v in vals:
            if key in by_name:
                by_name[key].validations.append(v)
            else:
                unmatched += 1
        for key, sc in scans:
            if key in by_name:
                by_name[key].scans.append(sc)
            else:
                unmatched += 1
        self.skipped = {
            "sites": len(raw_sites) - len(sites),
            "validations": len(raw_vals) - len(vals),
            "scans": len(raw_scans) - len(scans),
            "not_matched_to_a_site": unmatched,
        }
        self._cache, self._expires = sites, time.monotonic() + self._cache_seconds
        self._fetched_at = datetime.now(UTC)
        return sites
