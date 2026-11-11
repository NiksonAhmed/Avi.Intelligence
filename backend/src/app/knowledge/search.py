"""Lexical (BM25) retrieval over indexed passages.

Anthropic does not provide an embeddings API; BM25 works well for SOP vocabulary (exact terms such
as "SIV", "SAE", "database lock") and needs no extra service. It can be swapped for hybrid search
(pgvector) later without changing callers.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an and are as at be by can do does for from has have how i in is it its of on or our should "
    "that the their them then there these this to was we what when where which who why will with "
    "you your about into must may per".split()
)


def _stem(token: str) -> str:
    """Very light suffix stripping so "reported"/"reporting"/"reports" and "SAE"/"SAEs" match."""
    if len(token) > 6 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 5 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith("sses"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]


@dataclass(frozen=True)
class Passage:
    chunk_id: str
    document_id: str
    position: int
    section: str
    text: str
    title: str
    sop_number: str | None


@dataclass(frozen=True)
class Hit:
    passage: Passage
    score: float


class Bm25Index:
    def __init__(self, passages: list[Passage], k1: float = 1.5, b: float = 0.75) -> None:
        self.passages = passages
        self.k1 = k1
        self.b = b
        # Title, SOP number and section heading are indexed with the passage text so a question
        # like "site activation steps" finds the Site Activation SOP.
        self._tf: list[Counter[str]] = []
        lengths: list[int] = []
        df: Counter[str] = Counter()
        for p in passages:
            tokens = tokenize(f"{p.sop_number or ''} {p.title} {p.title} {p.section} {p.text}")
            counts = Counter(tokens)
            self._tf.append(counts)
            lengths.append(len(tokens))
            df.update(counts.keys())
        self._len = lengths
        self._avg = (sum(lengths) / len(lengths)) if lengths else 0.0
        n = len(passages)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, limit: int = 10) -> list[Hit]:
        terms = set(tokenize(query))
        if not terms or not self.passages:
            return []
        hits: list[Hit] = []
        for i, passage in enumerate(self.passages):
            tf = self._tf[i]
            score = 0.0
            for term in terms:
                f = tf.get(term)
                if not f:
                    continue
                norm = f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self._len[i] / self._avg))
                score += self._idf[term] * norm
            if score > 0:
                hits.append(Hit(passage, score))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]
