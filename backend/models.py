"""Shared data models used across agents."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    provider: str = ""
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Document:
    url: str
    title: str
    text: str
    provider: str = ""
    fetch_ok: bool = False
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Passage:
    doc_url: str
    doc_title: str
    text: str
    score: float = 0.0
    provider: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Plan:
    query: str
    intent: str
    language: str
    keywords: list[str]
    subqueries: list[str]
    entities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Source:
    id: int
    title: str
    url: str
    domain: str
    provider: str
    snippet: str
    credibility: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Answer:
    markdown: str
    cited_source_ids: list[int]
    confidence: float
    follow_ups: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Critique:
    coverage: float
    source_diversity: float
    confidence: float
    warnings: list[str]
    needs_retry: bool
    retry_query: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PipelineResult:
    query: str
    plan: Plan
    sources: list[Source]
    answer: Answer
    critique: Critique
    stats: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "plan": self.plan.to_dict(),
            "sources": [s.to_dict() for s in self.sources],
            "answer": self.answer.to_dict(),
            "critique": self.critique.to_dict(),
            "stats": self.stats,
        }
