"""Общий интерфейс поисковика.

Провайдер меняется одной переменной окружения: лицензии и лимиты у поисковых
API разные, привязываться к одному нельзя.
"""
from __future__ import annotations

from typing import Protocol

from ..models import SearchHit


class SearchProvider(Protocol):
    name: str

    @property
    def available(self) -> bool: ...

    def search(self, query: str, limit: int = 10) -> list[SearchHit]: ...
