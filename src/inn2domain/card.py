"""Карточка организации по ИНН.

Зачем это нужно пайплайну: по одному ИНН поисковик выдаёт почти только
агрегаторы реквизитов. Искать сайт можно лишь по названию, городу и бренду,
а проверять найденное — по ИНН и ОГРН. Всё это даёт карточка из ЕГРЮЛ.

Источник по умолчанию — DaData Suggestions (findById/party), бесплатный тариф.
"""
from __future__ import annotations

import re

from .cache import Cache
from .config import Settings
from .http_client import new_client
from .models import Company

FIND_BY_ID_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party"

_OPF_PREFIXES = (
    "ООО", "АО", "ПАО", "ЗАО", "ОАО", "НАО", "ИП", "АНО", "НКО", "ФГУП", "МУП", "ГУП",
    "ТСЖ", "СНТ", "ООО-", "ФГБУ", "ФГБОУ", "ГБУ", "МБУ", "КФХ", "ОП",
)


def strip_opf(name: str | None) -> str | None:
    """ООО \"Ромашка\" -> Ромашка. Для поисковых запросов кавычки и ОПФ только мешают."""
    if not name:
        return None
    cleaned = re.sub(r"[«»\"']", " ", name).strip()
    tokens = cleaned.split()
    while tokens and tokens[0].upper().strip(".") in _OPF_PREFIXES:
        tokens = tokens[1:]
    cleaned = " ".join(tokens).strip(" -,")
    return cleaned or None


class DaDataCardSource:
    """Клиент DaData Suggestions: ИНН -> карточка организации."""

    def __init__(self, settings: Settings, cache: Cache) -> None:
        self.settings = settings
        self.cache = cache

    @property
    def available(self) -> bool:
        return bool(self.settings.dadata_token)

    def get(self, inn: str) -> Company:
        if not self.available:
            return Company(inn=inn, source="none")
        cached = self.cache.get("dadata", {"inn": inn})
        if cached is None:
            with new_client(trust_env=self.settings.http_trust_env, timeout=20.0) as client:
                response = client.post(
                    FIND_BY_ID_URL,
                    headers={
                        "Authorization": f"Token {self.settings.dadata_token}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json={"query": inn, "count": 1},
                )
                response.raise_for_status()
                cached = response.json()
            self.cache.set("dadata", {"inn": inn}, cached)
        return self._parse(inn, cached)

    @staticmethod
    def _parse(inn: str, payload: dict) -> Company:
        suggestions = payload.get("suggestions") or []
        if not suggestions:
            return Company(inn=inn, source="dadata-empty")
        item = suggestions[0]
        data = item.get("data") or {}
        name = data.get("name") or {}
        address = (data.get("address") or {}).get("data") or {}
        state = (data.get("state") or {}).get("status")
        okved_name = None
        for entry in data.get("okveds") or []:
            if entry.get("main"):
                okved_name = entry.get("name")
                break
        management = (data.get("management") or {}).get("name")
        city = address.get("city") or address.get("region_with_type") or address.get("settlement")
        short_name = name.get("short_with_opf") or item.get("value")
        return Company(
            inn=data.get("inn") or inn,
            ogrn=data.get("ogrn"),
            name_short=short_name,
            name_full=name.get("full_with_opf"),
            brand=strip_opf(short_name),
            city=city,
            address=(data.get("address") or {}).get("value"),
            status=state,
            okved=data.get("okved"),
            okved_name=okved_name,
            management=management,
            emails=[e.get("value") for e in (data.get("emails") or []) if e.get("value")],
            source="dadata",
        )
