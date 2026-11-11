"""Pure mapping logic from Microsoft Graph list items to SOP documents (no I/O)."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any
from urllib.parse import unquote

from .models import DocumentKind, EditableCopy, SopDocument, SopStatus, StatusSource

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
    # Not _UIVersionString: SharePoint's own version counts saves (e.g. 18.0), not the document version.
    # Without a version column, the version is read from the file name ("..._2.0.docx", "v1.1").
    "version": ["DocumentVersion", "Document_x0020_Version", "SOPVersion"],
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


# Folder names that say where a document is in its life cycle, in priority order (any folder level).
_FOLDER_STAGES: list[tuple[re.Pattern[str], SopStatus]] = [
    (
        re.compile(r"supers|superced|obsolete|\barchived?\b|retired|withdrawn", re.IGNORECASE),
        SopStatus.SUPERSEDED,
    ),
    (re.compile(r"draft|unapproved", re.IGNORECASE), SopStatus.DRAFT),
    (re.compile(r"review|revision", re.IGNORECASE), SopStatus.IN_REVIEW),
    (re.compile(r"\b(?:approved|effective|released)\b", re.IGNORECASE), SopStatus.EFFECTIVE),
]
# Completed records (e.g. "Executed Forms") are not controlled documents.
_RECORD_FOLDER = re.compile(r"\bexecuted\b", re.IGNORECASE)


def status_from_folder(relative_path: str) -> SopStatus | None:
    """Life-cycle stage from folder names.

    "Approved/Superseded" -> Superseded, "Draft Unapproved" -> Draft, "Approved" -> Effective.
    """
    segments = [s for s in relative_path.split("/") if s.strip()]
    for pattern, status in _FOLDER_STAGES:
        if any(pattern.search(s) for s in segments):
            return status
    return None


def is_record_folder(relative_path: str) -> bool:
    return any(_RECORD_FOLDER.search(s) for s in relative_path.split("/"))


def derive_status(
    fields: dict[str, Any], field_map: FieldMap, folder_status: SopStatus | None = None
) -> tuple[SopStatus, StatusSource]:
    """Status precedence:

    1. The folder, when its name says Superseded / Draft / Review. An "Approved" folder counts only
       if the status column does not say otherwise (a document is never shown as Effective when either
       source says it is not).
    2. A status column (e.g. "Document Status") if the library has one.
    3. SharePoint content approval (_ModerationStatus: 0 approved, 1 rejected, 2 pending, 3 draft).
    4. Version numbering: major versions (x.0) are published, minor versions are drafts.
    """
    text = field_to_text(pick_field(fields, field_map["status"]))
    column = normalise_status(text) if text else None
    if folder_status is not None and folder_status != SopStatus.EFFECTIVE:
        return folder_status, StatusSource.FOLDER
    if folder_status == SopStatus.EFFECTIVE:
        if column is not None and column not in (SopStatus.EFFECTIVE, SopStatus.UNKNOWN):
            return column, StatusSource.COLUMN
        return SopStatus.EFFECTIVE, StatusSource.FOLDER
    if column is not None:
        return column, StatusSource.COLUMN

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


# Numbers are read from the START of the file name only (after a "Complete_with_Docusign_" prefix),
# so a change control such as "CC-012_GA-001-D_PM-SOP-009" is not mistaken for the SOP it mentions.
# Department-prefixed SOP: "CO-SOP-001 Trial Master File", "DM-SOP-002_Data Management_v1.1".
_DEPT_SOP = re.compile(r"^\s*(?P<dept>[A-Z]{2,4})[-_ ]SOP[-_ ]?(?P<num>\d{1,4})(?!\d)")
# Form/template belonging to an SOP: "CO-005-A Site Qualification Visit Report" -> SOP CO-SOP-005.
_DEPT_FORM = re.compile(r"^\s*(?P<dept>[A-Z]{2,4})[-_ ](?P<num>\d{3})[-_ ]?(?P<letter>[A-Z])(?![A-Za-z0-9])")
# Stand-alone template/form: "SM-TEM-001 Safety Database Tracker", "MP-FRM-001_CHECKLIST".
_DEPT_TEMPLATE = re.compile(r"^\s*(?P<dept>[A-Z]{2,4})[-_ ](?P<type>TEM|FRM)[-_ ]?(?P<num>\d{1,4})(?!\d)")
# Generic numbering: "SOP-0042", "sop_013", "SOP CO 012", "WI-101".
_SOP_NUMBER = re.compile(
    r"^\s*(?:SOP|WI|POL|QMS|FRM|TMP)[-_ .]?(?:[A-Z]{1,5}[-_ .]?)?\d{1,5}\b", re.IGNORECASE
)


# DocuSign's download of a completed envelope: the signed document itself, named after it
# ("Complete_with_Docusign_PM-SOP-002_Quality_Ri.pdf", name shortened by DocuSign).
_DOCUSIGN_PREFIX = re.compile(r"^\s*Complete[_ ]with[_ ]Docu[Ss]ign[_ ]", re.IGNORECASE)


def is_docusign_copy(file_name: str) -> bool:
    return bool(_DOCUSIGN_PREFIX.match(file_name))


def strip_docusign_prefix(file_name: str) -> str:
    return _DOCUSIGN_PREFIX.sub("", file_name, count=1)


def classify_file_name(file_name: str) -> tuple[DocumentKind, str | None, str | None]:
    """Returns (kind, document number, parent SOP number) from a file name's leading number."""
    file_name = strip_docusign_prefix(file_name)
    if m := _DEPT_SOP.match(file_name):
        return DocumentKind.SOP, f"{m['dept']}-SOP-{int(m['num']):03d}", None
    if m := _DEPT_FORM.match(file_name):
        number = f"{m['dept']}-{m['num']}-{m['letter']}"
        return DocumentKind.FORM, number, f"{m['dept']}-SOP-{m['num']}"
    if m := _DEPT_TEMPLATE.match(file_name):
        return DocumentKind.FORM, f"{m['dept']}-{m['type']}-{int(m['num']):03d}", None
    if m := _SOP_NUMBER.match(file_name):
        number = re.sub(r"[_ .]", "-", m.group(0).strip().upper())
        kind = DocumentKind.FORM if number.startswith(("FRM", "TMP")) else DocumentKind.SOP
        return kind, number, None
    return DocumentKind.OTHER, None, None


def extract_sop_number(text: str) -> str | None:
    """Extracts a document number such as "SOP-0042", "CO-SOP-001" or "CO-005-A" from a file name."""
    return classify_file_name(text)[1]


def strip_extension(file_name: str) -> str:
    return re.sub(r"\.[A-Za-z0-9]{1,5}$", "", file_name)


_VERSION_IN_NAME = re.compile(r"(?:\bv(?:ersion)?\s?|\s)(\d+(?:\.\d+)+)(?![\d.])", re.IGNORECASE)
_DATE_IN_NAME = re.compile(
    r"\b\d{1,2}[-\s]?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-\s]?\d{2,4}\b", re.IGNORECASE
)
_PLACEHOLDER_TITLE = re.compile(r"\s*(?:sop|document|form|word)?\s*template\s*", re.IGNORECASE)


def _strip_number(stem: str, sop_number: str | None) -> str:
    if not sop_number:
        return stem
    parts = []
    for part in sop_number.split("-"):
        parts.append(f"0*{int(part)}" if part.isdigit() else re.escape(part))
    return re.sub(r"^\s*" + "[-_ .]?".join(parts), "", stem, count=1, flags=re.IGNORECASE)


def _clean_stem(file_name: str, sop_number: str | None) -> str:
    """File name without extension, number, "- Copy" suffix or a glued extension (DocuSign exports)."""
    text = _strip_number(strip_extension(strip_docusign_prefix(file_name)), sop_number).replace("_", " ")
    text = re.sub(r"\s*-\s*copy(?:\s*\(\d+\))?\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<=\d)(?:docx?|pdf)\s*$", "", text, flags=re.IGNORECASE)  # "17Feb2026docx"
    return re.sub(r"\s{2,}", " ", text).strip()


# DocuSign drops the dot from versions in exported names: "Deviation_Log_20.pdf", "v10" -> 2.0, 1.0.
_DOTLESS_VERSION = re.compile(r"(?:\bv(\d)(\d)\b|\s(\d)0$)", re.IGNORECASE)


def version_from_file_name(file_name: str, sop_number: str | None = None) -> str | None:
    """Document version written in the file name: "..._2.0.docx", "v1.1", "v_1.0", "V1.0", "_20.pdf"."""
    text = _clean_stem(file_name, sop_number)
    found = _VERSION_IN_NAME.findall(text)
    if found:
        return str(found[-1])
    m = _DOTLESS_VERSION.search(_DATE_IN_NAME.sub("", text).strip())
    if m:
        return f"{m[1]}.{m[2]}" if m[1] else f"{m[3]}.0"
    return None


def title_from_file_name(file_name: str, sop_number: str | None) -> str:
    """Builds a readable title from a file name like "CO-SOP-014 Monitoring Visit_2.0_08Oct2025.docx"."""
    base = strip_extension(file_name)
    title = _clean_stem(file_name, sop_number)
    title = re.sub(r"\bv(?:ersion)?\s?\d+(?:\.\d+)*\b", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\b\d+\.\d+(?:\.\d+)*\b", "", title)  # bare versions such as "2.0"
    title = _DATE_IN_NAME.sub("", title)
    title = re.sub(r"\b(?:FINAL|DRAFT)\b", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s{2,}", " ", title).strip(" -–:,")
    title = re.sub(r"\s+\d{1,2}$", "", title)  # dot-less version left by DocuSign ("Deviation Log 20")
    return title.strip(" -–:,") or base


def is_placeholder_title(title: str) -> bool:
    """SharePoint "Title" values that come from the document template, e.g. "SOP Template"."""
    return bool(_PLACEHOLDER_TITLE.fullmatch(title))


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


def relative_folder(folder_path: str, scope: str | None) -> str:
    """Folder path relative to the configured SOP folder ("01. Clinical Operations/Monitoring")."""
    path = folder_path.strip("/")
    if not scope:
        return path
    prefix = scope.strip("/")
    if path.lower() == prefix.lower():
        return ""
    if path.lower().startswith(prefix.lower() + "/"):
        return path[len(prefix) + 1 :]
    return path


def department_from_folder(folder_path: str, scope: str | None) -> str | None:
    """First subfolder under the SOP folder without its number.

    "01. Clinical Operations" -> "Clinical Operations".
    """
    first = relative_folder(folder_path, scope).split("/", 1)[0].strip()
    if not first:
        return None
    return re.sub(r"^\d+[.)\-\s]+\s*", "", first).strip() or first


def parse_list_setting(raw: str | None, separator: str) -> list[str]:
    return [p.strip().strip("/") for p in (raw or "").split(separator) if p.strip().strip("/")]


def is_excluded_folder(folder_path: str, scope: str | None, excluded: list[str]) -> bool:
    rel = relative_folder(folder_path, scope).lower()
    return any(rel == e.lower() or rel.startswith(e.lower() + "/") for e in excluded)


def has_allowed_extension(file_name: str, extensions: list[str]) -> bool:
    if not extensions:
        return True
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    return ext in {e.lower().lstrip(".") for e in extensions}


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
    scope: str | None = None,
) -> SopDocument | None:
    """Maps a Graph list item (expanded with fields and driveItem). Returns None for folders/non-files.

    `scope` is the configured SOP folder; folder names below it give the life-cycle stage.
    """
    drive = item.get("driveItem")
    if not isinstance(drive, dict) or "folder" in drive or "file" not in drive:
        return None
    fields: dict[str, Any] = item.get("fields") or {}

    file_name = str(drive.get("name", ""))
    folder_path = folder_from_parent_path((drive.get("parentReference") or {}).get("path"))
    relative = relative_folder(folder_path, scope)
    kind, file_number, parent = classify_file_name(file_name)
    if is_record_folder(relative):
        kind, parent = DocumentKind.OTHER, None
    sop_number = field_to_text(pick_field(fields, field_map["sop_number"])) or file_number

    explicit_title = field_to_text(pick_field(fields, field_map["title"]))
    # SharePoint's Title column is often blank, repeats the file name or holds the template's title.
    if (
        explicit_title
        and explicit_title != strip_extension(file_name)
        and not is_placeholder_title(explicit_title)
    ):
        title = explicit_title
    else:
        title = title_from_file_name(file_name, file_number or sop_number)

    status, source = derive_status(fields, field_map, status_from_folder(relative))
    column_version = field_to_text(pick_field(fields, field_map["version"]))
    file_version = version_from_file_name(file_name, file_number)

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
        kind=kind,
        parent_sop_number=parent,
        version=column_version or file_version,
        version_source="column" if column_version else ("file-name" if file_version else None),
        status=status,
        status_source=source,
        effective_date=_to_datetime(pick_field(fields, field_map["effective_date"])),
        review_date=_to_datetime(pick_field(fields, field_map["review_date"])),
        owner=owner,
        department=field_to_text(pick_field(fields, field_map["department"])),
        folder_path=folder_path,
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


_EXTENSION_RANK = {"pdf": 0, "docx": 1, "doc": 2}
_WORD_EXTENSIONS = {"docx", "doc"}


def _extension(file_name: str) -> str:
    return file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""


_EDITABLE_COPY_FOLDER = re.compile(r"word|do\s*not\s*edit", re.IGNORECASE)


def _copy_preference(doc: SopDocument) -> tuple[int, int, int, float]:
    ext = doc.file_name.rsplit(".", 1)[-1].lower() if "." in doc.file_name else ""
    docusign = 1 if is_docusign_copy(doc.file_name) else 0  # signed too, but its name is shortened
    editable_copy = 1 if _EDITABLE_COPY_FOLDER.search(doc.folder_path) else 0
    modified = -doc.modified_at.timestamp() if doc.modified_at else 0.0
    return (_EXTENSION_RANK.get(ext, 9), docusign, editable_copy, modified)


def collapse_duplicates(docs: list[SopDocument]) -> list[SopDocument]:
    """One entry per document number and status.

    Libraries often hold the signed PDF next to an editable Word copy ("Word_Documents_DoNotEdit").
    The PDF is preferred, then a copy outside the editable-copies folder, then the latest modified.
    If the kept copy has no version in its name and the other copies agree on one, that version is used.
    """
    groups: dict[tuple[str, SopStatus], list[SopDocument]] = {}
    result: list[SopDocument] = []
    for doc in docs:
        if doc.sop_number is None:
            result.append(doc)
        else:
            groups.setdefault((doc.sop_number.upper(), doc.status), []).append(doc)
    for copies in groups.values():
        best = min(copies, key=_copy_preference)
        # DocuSign shortens exported file names ("Filing of Electronic Study Documen"): use the full
        # title of another copy that starts with the shortened one.
        longer = [
            c.title
            for c in copies
            if len(c.title) > len(best.title) and c.title.lower().startswith(best.title.lower())
        ]
        if longer:
            best = best.model_copy(update={"title": max(longer, key=len)})
        # Keep the Word copy alongside the signed PDF, so forms can be downloaded for filling in.
        if _extension(best.file_name) not in _WORD_EXTENSIONS:
            word = [c for c in copies if _extension(c.file_name) in _WORD_EXTENSIONS]
            if word:
                pick = min(word, key=_copy_preference)  # .docx before .doc, then latest modified
                best = best.model_copy(
                    update={
                        "editable_copy": EditableCopy(
                            id=pick.id,
                            file_name=pick.file_name,
                            size_bytes=pick.size_bytes,
                            mime_type=pick.mime_type,
                        )
                    }
                )
        if best.version is None:
            versions = {c.version for c in copies if c.version}
            if len(versions) == 1:
                best = best.model_copy(update={"version": versions.pop(), "version_source": "file-name"})
        result.append(best)
    return result


def _natural_key(text: str) -> list[Any]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def sort_sops(docs: list[SopDocument]) -> list[SopDocument]:
    """Natural sort by SOP number (SOP-2 before SOP-10); documents without a number go last."""
    return sorted(
        docs,
        key=lambda d: (d.sop_number is None, _natural_key(d.sop_number or ""), d.title.lower()),
    )
