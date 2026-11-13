"""Questions that optional modules answer themselves (Conferences, Data Management...).

A module registers a topic: the words that point at it and an async function that answers from the
module's own data, by fixed rules (no AI). Ask Avi.Intelligence never imports the modules (one-way
dependencies); a topic whose module is switched off, or that the person may not see, answers None and the
question falls through to studies and then SOP search.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.auth.rbac import CurrentUser

from .study_questions import StudyAnswer

Answerer = Callable[[Session, CurrentUser, str], Awaitable[StudyAnswer | None]]


@dataclass(frozen=True)
class Topic:
    name: str
    words: frozenset[str]
    phrases: tuple[str, ...]
    answer: Answerer


_TOPICS: list[Topic] = []


def register(topic: Topic) -> None:
    if all(t.name != topic.name for t in _TOPICS):
        _TOPICS.append(topic)


def words_of(question: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", question.lower()))


def matching(question: str) -> list[Topic]:
    """Topics the question points at, the strongest match first."""
    q = " ".join(question.lower().split())
    words = words_of(q)
    scored = []
    for t in _TOPICS:
        hits = len(words & t.words) + 2 * sum(1 for p in t.phrases if p in q)
        if hits:
            scored.append((hits, t))
    scored.sort(key=lambda pair: -pair[0])
    return [t for _hits, t in scored]
