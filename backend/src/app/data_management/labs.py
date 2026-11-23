"""Lab results from the lab forms in a Viedoc export, kept as flags only (user decision).

The values are read in memory during the sync and only the outcome is kept per expected result: reported,
missing or not done; out of range (high or low) against the normal range entered on the form; unit or
normal range missing; the investigator's evaluation (normal, abnormal not clinically significant,
abnormal clinically significant) and whether a clinically significant result has its AE/MH reference.
No result values and no normal-range numbers are stored.

Lab forms are recognised by their CDASH-style item IDs, so no study-specific set-up is needed:
  <prefix>ORRES<slot>              result (original units)      e.g. LBHMORRES$1, D1_LBWBC_LBORRES
  <prefix>ORRESU<slot>[__n]        unit (or ORRESUOTH, "other unit")
  <prefix>ORNR<slot>_Lower/_Upper  normal range
  <prefix>RANGE<slot>              comparator (=, >, <) of the result
  <prefix>TEST<slot>[__n]          analyte (repeating rows); otherwise the result's label names it
  <prefix>CLSIG<slot>              evaluation;  ...CSREF<slot>  AE/MH reference for a CS result
  ...ND<slot>                      test not done;  ...PERF / ...LBYN = "No"  whole form not done
Only result items whose prefix contains "LB" are labs: vital signs (VSORRES), ECG (EGORRES) and the
pregnancy test (PREGORRES) are left out. Qualitative results (no number, e.g. urine dipstick) count as
reported, without range checks.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

SYSTEM_FILES = (
    "_queries.csv",
    "_pending_forms.csv",
    "_sdv.csv",
    "_review_status.csv",
    "_items.csv",
    "_codelists.csv",
)
RESULT = re.compile(r"^(?P<pre>.*?)ORRES(?P<slot>\$\d+)?$")
FORM_NOT_DONE = re.compile(r"^[A-Za-z0-9_]*(PERF|LBYN)$")
NOT_DONE_ANSWERS = {"no", "n", "not done"}

TimeParser = Callable[[str | None], datetime | None]


@dataclass
class LabResult:
    site_code: str
    site_name: str
    subject_id: str
    event_id: str | None
    event_name: str | None
    event_date: datetime | None
    form_id: str
    analyte: str
    status: str  # reported | missing | not_done
    out_of_range: str | None = None  # high | low
    unit_missing: bool = False
    range_missing: bool = False
    evaluation: str | None = None  # normal | abnormal_ncs | abnormal_cs | other | missing
    cs_reference_missing: bool = False


@dataclass
class _Slot:
    """Where one result and its companion items sit in a lab form's columns."""

    result: int
    label: str
    fallback: str
    test: list[int]
    unit: list[int]
    lower: list[int]
    upper: list[int]
    comparator: list[int]
    clsig: list[int]
    cs_ref: list[int]
    not_done: list[int]


def evaluation_of(text: str) -> str:
    """Viedoc's evaluation wording -> normal | abnormal_ncs | abnormal_cs | other."""
    t = " ".join(text.lower().replace("-", " ").split())
    words = t.split()
    if t.startswith(("normal", "within normal")):
        return "normal"
    if "ncs" in words or "not clinically" in t or "non clinically" in t:
        return "abnormal_ncs"
    if "cs" in words or "clinically significant" in t:
        return "abnormal_cs"
    return "other"


def number(text: str) -> float | None:
    try:
        return float(text.strip().replace(",", "."))
    except ValueError:
        return None


def out_of_range(value: float, comparator: str, low: float | None, high: float | None) -> str | None:
    """'<5' with a lower limit of 5 is low; '>100' with an upper limit of 100 is high."""
    if comparator == "<":
        return "low" if low is not None and value <= low else None
    if comparator == ">":
        return "high" if high is not None and value >= high else None
    if low is not None and value < low:
        return "low"
    if high is not None and value > high:
        return "high"
    return None


def _form_id(file_name: str) -> str:
    base = file_name.rsplit("/", 1)[-1]
    match = re.search(r"_\d{8}_\d{6}_(.+)\.csv$", base, re.IGNORECASE)
    return match.group(1) if match else base.rsplit(".", 1)[0]


def read_lab_files(archive: zipfile.ZipFile, parse_time: TimeParser) -> list[LabResult]:
    results: list[LabResult] = []
    for name in archive.namelist():
        low = name.lower()
        if not low.endswith(".csv") or low.endswith(SYSTEM_FILES):
            continue
        text = archive.read(name).decode("utf-8-sig", errors="replace")
        if "ORRES" not in text[:20000]:
            continue  # not a lab form; skip without parsing
        rows = list(csv.reader(io.StringIO(text)))
        if len(rows) < 3:
            continue
        head, ids, data = rows[0], rows[1], rows[2:]
        slots = _slots(_form_id(name), head, ids)
        if slots:
            results.extend(_read_rows(_form_id(name), head, ids, data, slots, parse_time))
    return results


def _slots(form_id: str, head: list[str], ids: list[str]) -> list[_Slot]:
    by_id = {oid: i for i, oid in enumerate(ids)}

    def columns(pattern: str) -> list[int]:
        rx = re.compile(pattern)
        return [i for oid, i in by_id.items() if rx.fullmatch(oid)]

    slots: list[_Slot] = []
    for i, oid in enumerate(ids):
        m = RESULT.match(oid)
        if not m or "LB" not in m.group("pre").upper():
            continue  # vital signs, ECG and pregnancy results use ORRES too, but are not lab results
        pre, slot = m.group("pre"), m.group("slot") or ""
        p, s = re.escape(pre), re.escape(slot)
        cs_ref = columns(rf"{p}CSREF{s}|{re.escape(pre.removesuffix('_LB'))}CSREF{s}")
        if slot and not cs_ref:
            cs_ref = columns(rf".*CSREF{s}")
        label = head[i] if i < len(head) else ""
        slots.append(
            _Slot(
                result=i,
                label=re.sub(r"\s*result.*$", "", label, flags=re.IGNORECASE).strip(),
                fallback=pre.removesuffix("_LB").strip("_") or form_id,
                test=columns(rf"{p}TEST{s}(__\d+)?"),
                unit=columns(rf"{p}ORRESU(OTH)?{s}(__\d+)?"),
                lower=columns(rf"{p}ORNR{s}_Lower"),
                upper=columns(rf"{p}ORNR{s}_Upper"),
                comparator=columns(rf"{p}RANGE{s}"),
                clsig=columns(rf"{p}CLSIG{s}"),
                cs_ref=cs_ref,
                not_done=columns(rf".*ND{s}") if slot else [],
            )
        )
    return slots


def _read_rows(
    form_id: str,
    head: list[str],
    ids: list[str],
    data: list[list[str]],
    slots: list[_Slot],
    parse_time: TimeParser,
) -> list[LabResult]:
    by_label = {h: i for i, h in enumerate(head)}
    form_level = [i for i, oid in enumerate(ids) if FORM_NOT_DONE.match(oid)]
    out: list[LabResult] = []
    for row in data:

        def get(i: int | None, row: list[str] = row) -> str:
            return row[i].strip() if i is not None and i < len(row) else ""

        def first(cols: list[int], row: list[str] = row) -> str:
            return next((v for i in cols if (v := get(i, row))), "")

        subject = get(by_label.get("Subject Id"))
        if not subject:
            continue
        form_not_done = any(get(i).lower() in NOT_DONE_ANSWERS for i in form_level)

        def result(analyte: str, status: str, row: list[str] = row, subject: str = subject) -> LabResult:
            def cell(label: str) -> str:
                return get(by_label.get(label), row)

            return LabResult(
                site_code=cell("Site code"),
                site_name=cell("Site name"),
                subject_id=subject,
                event_id=cell("Event Id") or None,
                event_name=cell("Event name") or None,
                event_date=parse_time(cell("Event date")),
                form_id=form_id,
                analyte=analyte[:200],
                status=status,
            )

        for slot in slots:
            analyte = first(slot.test)
            if slot.test and not analyte:
                continue  # an unused repeating row
            analyte = analyte or slot.label or slot.fallback
            if form_not_done or first(slot.not_done):
                out.append(result(analyte, "not_done"))
                continue
            text = get(slot.result)
            if not text:
                out.append(result(analyte, "missing"))
                continue
            r = result(analyte, "reported")
            value = number(text)
            low, high = number(first(slot.lower)), number(first(slot.upper))
            if value is not None:
                r.out_of_range = out_of_range(value, first(slot.comparator), low, high)
                r.unit_missing = bool(slot.unit) and not first(slot.unit)
                r.range_missing = bool(slot.lower or slot.upper) and low is None and high is None
            if slot.clsig:
                evaluation = first(slot.clsig)
                r.evaluation = evaluation_of(evaluation) if evaluation else "missing"
            r.cs_reference_missing = (
                r.evaluation == "abnormal_cs" and bool(slot.cs_ref) and not first(slot.cs_ref)
            )
            out.append(r)
    return out
