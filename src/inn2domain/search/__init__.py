"""Провайдеры веб-поиска. Интерфейс один, реализации взаимозаменяемы."""
from __future__ import annotations

from ..cache import Cache
from ..config import Settings
from .base import SearchProvider
from .exa import ExaSearch
from .yandex import YandexSearch

__all__ = ["SearchProvider", "YandexSearch", "ExaSearch", "build_search_provider"]


def build_search_provider(settings: Settings, cache: Cache) -> SearchProvider:
    if settings.search_provider == "exa":
        return ExaSearch(settings, cache)
    return YandexSearch(settings, cache)
