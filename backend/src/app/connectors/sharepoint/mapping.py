"""Pure mapping logic from Microsoft Graph list items to SOP documents (no I/O)."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any
from urllib.parse import unquote

from .models import SopDocument, SopStatus, StatusSource

SOP_FIELDS = (
    "sop_number",
    "title",
    "version",
    "status",
    "effective_date",
    "review_date",
    "owner",
    "department",
)

FieldMap = dict[str, list[str]]

# Candidate SharePoint column *internal* names, tried in order.
# Override any field with SHAREPOINT_SOP_FIELD_MAP, e.g. {"sop_number": "DocNo", "status": "ApprovalState"}.
DEFAULT_FIELD_MAP: FieldMap = {
    "sop_number": ["SOPNumber", "SOP_x0020_Number", "DocumentNumber", "Document_x0020_Number", "DocNumber"],
    "title": ["DocumentTitle", "Title"],
    "version": ["DocumentVersion", "Document_x0020_Version", "SOPVersion", "_UIVersionString"],
    "status": ["DocumentStatus", "Document_x0020_Status", "SOPStatus", "Status"],
    "effective_date": ["EffectiveDate", "Effective_x0020_Date", "Effective"],
    "review_date": ["ReviewDate", "Review_x0020_Date", "NextReviewDate", "Next_x0020_Review_x0020_Date"],
    "owner": ["DocumentOwner", "Document_x0020_Owner", "SOPOwner", "Owner"],
    "department": ["Department", "Category", "Function", "BusinessFunction"],
}


def parse_field_map(raw_json: str | None) -> FieldMap:
    field_map = {k: list(v) for k, v in DEFAULT_FIELD_MAP.items()}
    if not raw_json:
        return field_map
    try:
        raw = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError("SHAREPOINT_SOP_FIELD_MAP is not valid JSON.") from exc
    if not isinstance(raw, dict):
        raise ValueError("SHAREPOINT_SOP_FIELD_MAP must be a JSON object.")
    for key, value in raw.items():
        if key not in DEFAULT_FIELD_MAP:
            raise ValueError(f'SHAREPOINT_SOP_FIELD_MAP has unknown field "{key}".')
        names = value if isinstance(value, list) else [value]
        if not names or not all(isinstance(n, str) and n for n in names):
            raise ValueError(f"SHAREPOINT_SOP_FIELD_MAP.{key} must be a column name or list of names.")
        field_map[key] = names
    return field_map


def pick_field(fields: dict[str, Any], candidates: Iterable[str]) -> Any:
    """Returns the first non-empty value among candidate columns."""
    for name in candidates:
        value = fields.get(name)
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        return value
    return None


def field_to_text(value: Any) -> str | None:
    """Converts SharePoint column values (text, number, choice, lookup, multi-value) to display text."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        parts = [p for p in (field_to_text(v) for v in value) if p]
        return ", ".join(parts) or None
    if isinstance(value, dict):
        for key in ("LookupValue", "Label", "displayName", "Title", "Email"):
            if isinstance(value.get(key), str) and value[key]:
                return str(value[key])
    return None


_STATUS_RULES: list[tuple[re.Pattern[str], SopStatus]] = [
    (re.compile(r"supersed|obsolete|replaced"), SopStatus.SUPERSEDED),
    (re.compile(r"retire|withdrawn|archiv|inactive"), SopStatus.RETIRED),
    (re.compile(r"review|pending|approval|submitted"), SopStatus.IN_REVIEW),
    (re.compile(r"draft|rejected|in progress|wip"), SopStatus.DRAFT),
    (re.compile(r"effective|approved|current|published|active|released|final"), SopStatus.EFFECTIVE),
]


def normalise_status(text: str) -> SopStatus:
    lowered = text.lower()
    for pattern, status in _STATUS_RULES:
        if pattern.search(lowered):
            return status
    return SopStatus.UNKNOWN


_MODERATION = {
    0: SopStatus.EFFECTIVE,
    1: SopStatus.DRAFT,
    2: SopStatus.IN_REVIEW,
    3: SopStatus.DRAFT,
    4: SopStatus.DRAFT,
}


def derive_status(fields: dict[str, Any], field_map: FieldMap) -> tuple[SopStatus, StatusSource]:
    """Status precedence:

    1. A status column (e.g. "Document Status") if the library has one.
    2. SharePoint content approval (_ModerationStatus: 0 approved, 1 rejected, 2 pending, 3 draft).
    3. Version numbering: major versions (x.0) are published, minor versions are drafts.
    """
    text = field_to_text(pick_field(fields, field_map["status"]))
    if text:
        return normalise_status(text), StatusSource.COLUMN

    moderation = fields.get("_ModerationStatus")
    if moderation not in (None, ""):
        try:
            code = int(moderation)
        except (TypeError, ValueError):
            code = -1
        if code in _MODERATION:
            return _MODERATION[code], StatusSource.CONTENT_APPROVAL

    ui_version = field_to_text(fields.get("_UIVersionString"))
    if ui_version and re.fullmatch(r"\d+\.\d+", ui_version):
        status = SopStatus.EFFECTIVE if ui_version.endswith(".0") else SopStatus.DRAFT
        return status, StatusSource.VERSION_NUMBER
    return SopStatus.UNKNOWN, StatusSource.NONE


_SOP_NUMBER = re.compile(r"\b(?:SOP|WI|POL|QMS|FRM|TMP)[-_ .]?(?:[A-Z]{1,5}[-_ .]?)?\d{1,5}\b", re.IGNORECASE)


def extract_sop_number(text: str) -> str | None:
    """Extracts an SOP number such as "SOP-0042" or "SOP-CO-012" from text (usually the file name)."""
    match = _SOP_NUMBER.search(text)
    if not match:
        return None
    return re.sub(r"[_ .]", "-", match.group(0).upper())


def strip_extension(file_name: str) -> str:
    return re.sub(r"\.[A-Za-z0-9]{1,5}$", "", file_name)


def title_from_file_name(file_name: str, sop_number: str | None) -> str:
    """Builds a readable title from a file name like "SOP-0042 Site Activation v3.2.docx"."""
    base = strip_extension(file_name)
    title = base
    if sop_number:
        pattern = "[-_ .]?".join(re.escape(part) for part in sop_number.split("-"))
        title = re.sub(pattern, "", title, count=1, flags=re.IGNORECASE)
    title = title.replace("_", " ")
    title = re.sub(r"\bv(?:ersion)?\s?\d+(?:\.\d+)*\b", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s{2,}", " ", title).strip(" -–:")
    return title or base


def folder_from_parent_path(path: str | None) -> str:
    """Converts parentReference.path ("/drives/b!x/root:/SOPs/Clinical") to "SOPs/Clinical"."""
    if not path or "root:" not in path:
        return ""
    rest = path.split("root:", 1)[1].lstrip("/")
    return unquote(rest)


def is_within_folder(folder_path: str, scope: str | None) -> bool:
    """True if folder_path is the configured folder or a subfolder of it (case-insensitive)."""
    if not scope:
        return True
    a = folder_path.lower().rstrip("/")
    b = scope.lower().strip("/")
    return a == b or a.startswith(f"{b}/")


def _to_datetime(value: Any) -> datetime | None:
    text = field_to_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _display_name(identity: Any) -> str | None:
    if isinstance(identity, dict):
        user = identity.get("user")
        if isinstance(user, dict) and isinstance(user.get("displayName"), str):
            return str(user["displayName"])
    return None


def map_list_item_to_sop(
    item: dict[str, Any],
    field_map: FieldMap,
    resolve_person: Callable[[str], str | None] = lambda _id: None,
) -> SopDocument | None:
    """Maps a Graph list item (expanded with fields and driveItem). Returns None for folders/non-files."""
    drive = item.get("driveItem")
    if not isinstance(drive, dict) or "folder" in drive or "file" not in drive:
        return None
    fields: dict[str, Any] = item.get("fields") or {}

    file_name = str(drive.get("name", ""))
    sop_number = field_to_text(pick_field(fields, field_map["sop_number"])) or extract_sop_number(file_name)

    explicit_title = field_to_text(pick_field(fields, field_map["title"]))
    # SharePoint's Title column is often blank or just repeats the file name.
    if explicit_title and explicit_title != strip_extension(file_name):
        title = explicit_title
    else:
        title = title_from_file_name(file_name, sop_number)

    status, source = derive_status(fields, field_map)

    owner = field_to_text(pick_field(fields, field_map["owner"]))
    if not owner:
        # Person columns arrive as "<Column>LookupId" holding only a numeric id.
        for name in field_map["owner"]:
            lookup = fields.get(f"{name}LookupId")
            if lookup not in (None, ""):
                owner = resolve_person(str(lookup))
                if owner:
                    break

    file_info = drive.get("file") or {}
    size = drive.get("size")
    return SopDocument(
        id=str(drive["id"]),
        title=title,
        file_name=file_name,
        sop_number=sop_number,
        version=field_to_text(pick_field(fields, field_map["version"])),
        status=status,
        status_source=source,
        effective_date=_to_datetime(pick_field(fields, field_map["effective_date"])),
        review_date=_to_datetime(pick_field(fields, field_map["review_date"])),
        owner=owner,
        department=field_to_text(pick_field(fields, field_map["department"])),
        folder_path=folder_from_parent_path((drive.get("parentReference") or {}).get("path")),
        modified_at=_to_datetime(drive.get("lastModifiedDateTime") or item.get("lastModifiedDateTime")),
        modified_by=_display_name(drive.get("lastModifiedBy")) or _display_name(item.get("lastModifiedBy")),
        web_url=drive.get("webUrl") or item.get("webUrl"),
        size_bytes=size if isinstance(size, int) else None,
        mime_type=file_info.get("mimeType") if isinstance(file_info, dict) else None,
    )


def collect_person_lookup_ids(items: Iterable[dict[str, Any]], field_map: FieldMap) -> set[str]:
    ids: set[str] = set()
    for item in items:
        fields = item.get("fields") or {}
        for name in field_map["owner"]:
            lookup = fields.get(f"{name}LookupId")
            if lookup not in (None, ""):
                ids.add(str(lookup))
    return ids


def _natural_key(text: str) -> list[Any]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def sort_sops(docs: list[SopDocument]) -> list[SopDocument]:
    """Natural sort by SOP number (SOP-2 before SOP-10); documents without a number go last."""
    return sorted(
        docs,
        key=lambda d: (d.sop_number is None, _natural_key(d.sop_number or ""), d.title.lower()),
    )
