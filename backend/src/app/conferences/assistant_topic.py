"""Ask Avi.Intelligence about conferences: answered from the conference list by fixed rules (no AI)."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.assistant import topics
from app.assistant.study_questions import AnswerTable, SourceLink, StudyAnswer, day
from app.auth.rbac import CurrentUser, Permission
from app.core.config import get_settings
from app.studies.clock import today

from .models import AvionRole
from .report import build_conferences
from .source import get_conference_source

WORDS = frozenset(
    {"conference", "conferences", "congress", "congresses", "summit", "summits", "exhibiting", "exhibit",
     "exhibition", "booth", "booths", "bd", "convention", "conventions", "forum", "meeting", "meetings"}
)  # fmt: skip
PHRASES = ("trade show", "business development", "where is avion going", "where are we going", "who is going")
ROLE_WORDS = {
    "exhibiting": AvionRole.EXHIBITING,
    "exhibit": AvionRole.EXHIBITING,
    "booth": AvionRole.EXHIBITING,
    "booths": AvionRole.EXHIBITING,
    "speaking": AvionRole.SPEAKING,
    "talk": AvionRole.SPEAKING,
    "talks": AvionRole.SPEAKING,
    "attending": AvionRole.ATTENDING,
    "considering": AvionRole.CONSIDERING,
}


async def answer(_db: Session, user: CurrentUser, question: str) -> StudyAnswer | None:
    q = " ".join(question.lower().split())
    words = topics.words_of(q)
    # "Meeting" or "forum" alone is not about conferences ("sponsor meeting"): needs a conference word too.
    if not (words & (WORDS - {"meeting", "meetings", "forum"}) or any(p in q for p in PHRASES)):
        return None
    if not get_settings().conferences_enabled or not user.can(Permission.CONFERENCE_VIEW):
        return None
    source = get_conference_source()
    records = await source.list_conferences()
    years = [int(y) for y in re.findall(r"\b(20\d\d)\b", q)]
    role = next((r for w, r in ROLE_WORDS.items() if w in words), None)
    can_cost = user.can(Permission.CONFERENCE_COST)
    r = build_conferences(
        records, today(), year=years[0] if years else None, role=role, can_see_cost=can_cost
    )
    rows = r.conferences
    place = [c for c in rows if (c.city and c.city.lower() in q) or (c.country and c.country.lower() in q)]
    if place:
        rows = place
    deadlines = bool(words & {"register", "registration", "registrations", "deadline", "deadlines"})
    if deadlines:
        rows = [c for c in rows if c.register_by and not c.past]
        rows.sort(key=lambda c: c.register_by or c.starts_on)
    elif words & {"next", "upcoming", "coming"}:
        rows = [c for c in rows if not c.past]
    show_cost = can_cost and bool(words & {"cost", "costs", "budget", "spend", "price"})

    columns = ["Dates", "Conference", "Where", "Avion's role", "Who is going", "Register by"]
    if show_cost:
        columns.append("Cost")
    table = AnswerTable(
        title="Registration deadlines" if deadlines else f"Conferences in {r.year}",
        columns=columns,
        rows=[
            [
                f"{day(c.starts_on)} – {day(c.ends_on)}" if c.ends_on != c.starts_on else day(c.starts_on),
                c.name,
                ", ".join(x for x in (c.city, c.country) if x) or "—",
                c.role.value,
                c.team or "—",
                day(c.register_by),
            ]
            + (
                [f"{c.cost:,.0f} {c.currency or ''}".strip() if c.cost is not None else "—"]
                if show_cost
                else []
            )
            for c in rows[:25]
        ],
        links=[f"/conferences?year={r.year}&id={c.id}" for c in rows[:25]],
        more=max(0, len(rows) - 25),
    )
    nxt = next((c for c in r.conferences if c.id == r.next_id), None)
    if deadlines:
        head = f"{len(rows)} upcoming registration deadline{'s' if len(rows) != 1 else ''}" + (
            f"; the first is {rows[0].name}, register by {day(rows[0].register_by)}." if rows else "."
        )
    else:
        head = f"{len(rows)} conference{'s' if len(rows) != 1 else ''} in {r.year}" + (
            f"{' as ' + role.value.lower() if role else ''}."
        )
        if nxt and not place:
            head += f" Next: {nxt.name} in {nxt.city}, {day(nxt.starts_on)} (in {nxt.days_until} days)."
    lines = []
    if source.info().mode == "demo":
        lines.append("These are demo conferences: the BD team's SharePoint list is not connected yet.")
    if words & {"cost", "costs", "budget", "spend", "price"} and not can_cost:
        lines.append("Costs are shown only to people allowed to see them.")
    understood = "Registration deadlines" if deadlines else "Conferences"
    understood += (
        f" · {r.year}"
        + (f" · {role.value}" if role else "")
        + (" · " + (place[0].city or place[0].country or "") if place else "")
    )
    return StudyAnswer(
        intent="conferences",
        understood=understood,
        headline=head,
        lines=lines,
        tables=[table] if rows else [],
        sources=[SourceLink(label="Conferences", url="/conferences")],
        as_of=source.info().fetched_at,
        sandbox_only=False,
        follow_ups=[
            "Which conference registrations are due?",
            "Where are we exhibiting this year?",
            "What is the next conference?",
        ],  # fmt: skip
        note="Worked out by Avi.Intelligence from the BD team's conference list (read-only), by fixed rules.",
    )


topics.register(topics.Topic("conferences", WORDS, PHRASES, answer))
