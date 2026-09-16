"""Настройки читаются из .env в корне репозитория и из переменных окружения."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    dadata_token: str | None
    gigachat_auth_key: str | None
    gigachat_scope: str
    gigachat_model: str
    gigachat_verify_ssl: bool
    search_provider: str
    yandex_api_key: str | None
    yandex_folder_id: str | None
    exa_api_key: str | None
    http_trust_env: bool
    cache_path: Path
    cache_ttl_days: int

    @property
    def has_llm(self) -> bool:
        return bool(self.gigachat_auth_key)

    @property
    def has_search(self) -> bool:
        if self.search_provider == "yandex":
            return bool(self.yandex_api_key and self.yandex_folder_id)
        return bool(self.exa_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv(ROOT / ".env", override=False)
    return Settings(
        dadata_token=os.getenv("DADATA_TOKEN") or None,
        gigachat_auth_key=os.getenv("GIGACHAT_AUTH_KEY") or None,
        gigachat_scope=os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
        gigachat_model=os.getenv("GIGACHAT_MODEL", "GigaChat-2"),
        gigachat_verify_ssl=_bool("GIGACHAT_VERIFY_SSL", False),
        search_provider=(os.getenv("SEARCH_PROVIDER", "yandex") or "yandex").lower(),
        yandex_api_key=os.getenv("YANDEX_SEARCH_API_KEY") or None,
        yandex_folder_id=os.getenv("YANDEX_FOLDER_ID") or None,
        exa_api_key=os.getenv("EXA_API_KEY") or None,
        http_trust_env=_bool("HTTP_TRUST_ENV", False),
        cache_path=Path(os.getenv("CACHE_PATH", str(ROOT / "cache.sqlite3"))),
        cache_ttl_days=int(os.getenv("CACHE_TTL_DAYS", "14")),
    )
