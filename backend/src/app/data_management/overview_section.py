"""Data Management's sections on the role-based Overview (registered when this module is loaded).

Figures come from the module's own views (same rules and numbers as the Data Management tab), for the
default study scope. Shown only while the module is switched on and to people who may view it.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.auth.rbac import CurrentUser, Permission
from app.core.config import get_settings
from app.overview import providers
from app.overview.schemas import Kpi, Row, Section, SourceInfo

from .api import overview as dm_overview
from .checks_api import labs_view, missing_view

LINK = "/data-management"
SOURCE = "from Viedoc"


def _kpis(tiles: list, keys: list[str], link: str, pct: set[str] | None = None) -> list[Kpi]:  # type: ignore[type-arg]
    by_key = {t.key: t for t in tiles}
    return [
        Kpi(
            label=by_key[k].label.replace(" (%)", ""),
            value=f"{by_key[k].value}%" if pct and k in pct else f"{by_key[k].value:,}",
            note=by_key[k].note,
            tone=by_key[k].tone,
            link=link,
        )
        for k in keys
        if k in by_key
    ]


async def contribute(db: Session, user: CurrentUser) -> providers.Contribution:
    settings = get_settings()
    if not settings.data_management_enabled or not user.can(Permission.DM_VIEW):
        return providers.Contribution()

    ov = await dm_overview(db, user, settings, scope=None)
    missing = await missing_view(
        db, user, settings, scope=None, study=None, view="fields", site=None, form=None, visit=None,
        since_from=None, since_to=None, search=None, limit=1, offset=0,
    )  # fmt: skip
    labs = await labs_view(
        db, user, settings, scope=None, study=None, view="flagged", site=None, form=None, visit=None,
        analyte=None, visit_from=None, visit_to=None, search=None, limit=1, offset=0,
    )  # fmt: skip

    sites = [
        Row(
            label=f"{s.site_code} · {s.site_name}",
            detail=(
                f"{s.open_at_site} open queries · {s.missing_items} missing · "
                f"SDV {s.sdv_done} of {s.sdv_required}"
            ),
            chip=f"{s.overdue} overdue" if s.overdue else "None overdue",
            tone="bad" if s.overdue else "good",
            link=f"{LINK}?tab=queries",
        )
        for s in ov.sites[:4]
    ]
    queries = Section(
        key="dm_queries", title="Queries", source=SOURCE, link=f"{LINK}?tab=queries", link_label="Queries",
        kpis=_kpis(ov.tiles, ["open_at_site", "awaiting_approval", "closed_30"], f"{LINK}?tab=queries"),
        rows=sites, empty="No sites with queries.",
    )  # fmt: skip
    missing_section = Section(
        key="dm_missing", title="Missing data", source=SOURCE, link=f"{LINK}?tab=missing",
        link_label="Missing data",
        kpis=_kpis(missing.tiles, ["fields", "overdue", "pending", "upgrades"], f"{LINK}?tab=missing"),
    )  # fmt: skip
    labs_section = Section(
        key="dm_labs", title="Labs (flags only)", source=SOURCE, link=f"{LINK}?tab=labs", link_label="Labs",
        kpis=_kpis(labs.tiles, ["reported", "out_of_range", "clin_sig", "checks"], f"{LINK}?tab=labs",
                   pct={"reported"}),
    )  # fmt: skip
    sdv = Section(
        key="dm_sdv", title="SDV", source=SOURCE, link=f"{LINK}?tab=sdv", link_label="SDV",
        kpis=[
            Kpi(label="Fields verified", value=f"{round(ov.sdv.percent or 0)}%",
                note=f"{ov.sdv.done:,} of {ov.sdv.required:,} fields", tone="info", link=f"{LINK}?tab=sdv"),
            Kpi(label="Forms fully verified", value=f"{ov.sdv.forms_complete:,}",
                note=f"of {ov.sdv.forms_total:,} forms", tone="neutral", link=f"{LINK}?tab=sdv"),
        ],
    )  # fmt: skip
    summary = Section(
        key="dm", title="Data management", source=SOURCE, link=LINK, link_label="Data Management",
        kpis=_kpis(ov.tiles, ["open_at_site", "awaiting_approval", "missing_items"], LINK)
        + _kpis(labs.tiles, ["clin_sig"], f"{LINK}?tab=labs") + sdv.kpis[:1],
        rows=sites, empty="No sites with queries.",
    )  # fmt: skip

    highlights = {}
    awaiting = next((k for k in queries.kpis if k.label.startswith("Answered")), None)
    if awaiting is not None:
        highlights["dm_awaiting"] = awaiting
    clin = next(iter(_kpis(labs.tiles, ["clin_sig"], f"{LINK}?tab=labs")), None)
    if clin is not None:
        highlights["dm_clin_sig"] = clin

    return providers.Contribution(
        sections={s.key: s for s in (summary, queries, missing_section, labs_section, sdv)},
        sources=[SourceInfo(name="Viedoc", as_of=ov.as_of)],
        highlights=highlights,
    )


providers.register(contribute)
