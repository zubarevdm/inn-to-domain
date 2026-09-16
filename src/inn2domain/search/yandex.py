"""Yandex Search API v2 (синхронный режим).

Выбран основным: российский малый и средний бизнес индексируется Яндексом
заметно полнее, чем зарубежными поисковиками, а у задачи вся выборка русская.
Ответ приходит как base64 от XML выдачи.
"""
from __future__ import annotations

import base64
import xml.etree.ElementTree as ET

import httpx

from ..cache import Cache
from ..config import Settings
from ..http_client import new_client
from ..models import SearchHit

SEARCH_URL = "https://searchapi.api.cloud.yandex.net/v2/web/search"


class YandexSearch:
    name = "yandex"

    def __init__(self, settings: Settings, cache: Cache) -> None:
        self.settings = settings
        self.cache = cache

    @property
    def available(self) -> bool:
        return bool(self.settings.yandex_api_key and self.settings.yandex_folder_id)

    def search(self, query: str, limit: int = 10) -> list[SearchHit]:
        if not self.available:
            raise RuntimeError("Не заданы YANDEX_SEARCH_API_KEY и YANDEX_FOLDER_ID")
        cache_key = {"provider": self.name, "query": query, "limit": limit}
        raw_xml = self.cache.get("search", cache_key)
        if raw_xml is None:
            raw_xml = self._request(query, limit)
            self.cache.set("search", cache_key, raw_xml)
        return self._parse(raw_xml, query)

    def _request(self, query: str, limit: int) -> str:
        body = {
            "query": {
                "searchType": "SEARCH_TYPE_RU",
                "queryText": query,
                "familyMode": "FAMILY_MODE_NONE",
                "page": "0",
            },
            "groupSpec": {
                "groupMode": "GROUP_MODE_FLAT",
                "groupsOnPage": str(limit),
                "docsInGroup": "1",
            },
            "maxPassages": "3",
            "region": "225",
            "l10N": "LOCALIZATION_RU",
            "folderId": self.settings.yandex_folder_id,
            "responseFormat": "FORMAT_XML",
        }
        headers = {"Authorization": f"Api-Key {self.settings.yandex_api_key}"}
        with new_client(trust_env=self.settings.http_trust_env, timeout=40.0) as client:
            response = client.post(SEARCH_URL, headers=headers, json=body)
            if response.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"Yandex Search API {response.status_code}: {response.text[:300]}",
                    request=response.request,
                    response=response,
                )
            payload = response.json()
        raw = payload.get("rawData") or ""
        return base64.b64decode(raw).decode("utf-8", errors="replace")

    @staticmethod
    def _parse(raw_xml: str, query: str) -> list[SearchHit]:
        try:
            root = ET.fromstring(raw_xml)
        except ET.ParseError:
            return []
        error = root.find(".//response/error")
        if error is not None and (error.text or "").strip():
            raise RuntimeError(f"Yandex Search API: {error.text.strip()}")
        hits: list[SearchHit] = []
        for position, doc in enumerate(root.iter("doc"), start=1):
            url = (doc.findtext("url") or "").strip()
            if not url:
                continue
            title = _text_of(doc.find("title"))
            passages = " ".join(_text_of(p) for p in doc.iter("passage"))
            headline = _text_of(doc.find("headline"))
            hits.append(
                SearchHit(
                    url=url,
                    title=title,
                    snippet=(passages or headline).strip(),
                    position=position,
                    query=query,
                )
            )
        return hits


def _text_of(node: ET.Element | None) -> str:
    """Выдача Яндекса подсвечивает слова тегами <hlword>, нужен плоский текст."""
    if node is None:
        return ""
    return "".join(node.itertext()).strip()
