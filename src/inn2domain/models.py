"""Схемы данных пайплайна. Всё, что уходит наружу, проходит через pydantic."""
from __future__ import annotations

from pydantic import BaseModel, Field


class Company(BaseModel):
    """Карточка организации из официального источника (DaData / ЕГРЮЛ)."""

    inn: str
    ogrn: str | None = None
    name_short: str | None = None
    name_full: str | None = None
    brand: str | None = None
    city: str | None = None
    address: str | None = None
    status: str | None = None
    okved: str | None = None
    okved_name: str | None = None
    management: str | None = None
    emails: list[str] = Field(default_factory=list)
    source: str = "none"

    @property
    def display_name(self) -> str:
        return self.name_short or self.name_full or self.inn


class SearchHit(BaseModel):
    url: str
    title: str = ""
    snippet: str = ""
    position: int = 0
    query: str = ""


class PageEvidence(BaseModel):
    """Результат проверки конкретной страницы кандидата."""

    url: str
    http_status: int | None = None
    title: str | None = None
    inn_found: bool = False
    ogrn_found: bool = False
    inn_context: str | None = None
    developer_mention: bool = False
    name_similarity: float = 0.0
    excerpt: str = ""
    error: str | None = None


class Candidate(BaseModel):
    domain: str
    hits: list[SearchHit] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
    best_position: int = 99
    evidence: list[PageEvidence] = Field(default_factory=list)
    from_email: bool = False
    score: float = 0.0
    flags: list[str] = Field(default_factory=list)

    @property
    def inn_confirmed(self) -> bool:
        return any(e.inn_found and not e.developer_mention for e in self.evidence)

    @property
    def ogrn_confirmed(self) -> bool:
        return any(e.ogrn_found and not e.developer_mention for e in self.evidence)

    @property
    def reachable(self) -> bool:
        return any(e.http_status is not None and e.http_status < 400 for e in self.evidence)

    @property
    def best_name_similarity(self) -> float:
        return max((e.name_similarity for e in self.evidence), default=0.0)


class LLMVerdict(BaseModel):
    domain: str | None = None
    confidence: float = 0.0
    reasoning: str = ""
    extra_query: str | None = None
    raw: str = ""


class Result(BaseModel):
    """Полный результат: наружу отдаётся только domain, остальное — трассировка."""

    inn: str
    domain: str | None = None
    confidence: float = 0.0
    reason: str = ""
    decided_by: str = "none"
    company: Company | None = None
    candidates: list[Candidate] = Field(default_factory=list)
    llm: LLMVerdict | None = None
    queries: list[str] = Field(default_factory=list)
    stats: dict[str, float | int] = Field(default_factory=dict)

    def answer(self) -> dict[str, str | None]:
        return {"domain": self.domain}
