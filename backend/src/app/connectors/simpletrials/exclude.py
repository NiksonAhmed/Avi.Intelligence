"""Studies Avion leaves out of Avi.Intelligence, such as SimpleTrials test studies (user decision 2026-11-24).

SIMPLETRIALS_EXCLUDED_STUDIES lists study numbers or names separated by commas, e.g.
"Sandbox Study,TC 01 EC 01". Matching ignores capital letters and extra spaces. An excluded study is
skipped before anything else about it is read, so none of its sites, tasks, documents, deviations or
visits are fetched or stored, and studies stored earlier are hidden everywhere.
"""

from __future__ import annotations


def _norm(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def parse_excluded(raw: str | None) -> frozenset[str]:
    return frozenset(n for n in (_norm(part) for part in (raw or "").split(",")) if n)


def is_excluded(excluded: frozenset[str], *names: object) -> bool:
    """True when any of the study's number or name is on the list."""
    return bool(excluded) and any(_norm(n) in excluded for n in names if n)
