"""Exa — запасной поисковый провайдер.

Держим его на случай, если Yandex Search API недоступен (нет гранта, исчерпан
лимит). Интерфейс тот же, пайплайн о подмене не знает.
"""
from __future__ import annotations

from ..cache import Cache
from ..config import Settings
from ..http_client import new_client
from ..models import SearchHit

SEARCH_URL = "https://api.exa.ai/search"


class ExaSearch:
    name = "exa"

    def __init__(self, settings: Settings, cache: Cache) -> None:
        self.settings = settings
        self.cache = cache

    @property
    def available(self) -> bool:
        return bool(self.settings.exa_api_key)

    def search(self, query: str, limit: int = 10) -> list[SearchHit]:
        if not self.available:
            raise RuntimeError("Не задан EXA_API_KEY")
        cache_key = {"provider": self.name, "query": query, "limit": limit}
        payload = self.cache.get("search", cache_key)
        if payload is None:
            body = {
                "query": query,
                "numResults": limit,
                "type": "auto",
                "contents": {"text": {"maxCharacters": 600}},
            }
            headers = {"x-api-key": self.settings.exa_api_key, "Content-Type": "application/json"}
            with new_client(trust_env=self.settings.http_trust_env, timeout=40.0) as client:
                response = client.post(SEARCH_URL, headers=headers, json=body)
                response.raise_for_status()
                payload = response.json()
            self.cache.set("search", cache_key, payload)
        hits = []
        for position, item in enumerate(payload.get("results") or [], start=1):
            url = item.get("url")
            if not url:
                continue
            hits.append(
                SearchHit(
                    url=url,
                    title=item.get("title") or "",
                    snippet=(item.get("text") or item.get("summary") or "")[:600],
                    position=position,
                    query=query,
                )
            )
        return hits
