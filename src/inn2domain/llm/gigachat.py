"""Клиент GigaChat: OAuth, ретраи, разбор JSON-ответа.

Почему GigaChat: модель российская, работает без VPN и не требует зарубежной
карты. Проверка сертификатов по умолчанию отключена — цепочка НУЦ Минцифры
редко установлена в системе; в проде сюда подставляется бандл сертификатов.
"""
from __future__ import annotations

import json
import re
import time
import uuid

import httpx

from ..cache import Cache
from ..config import Settings
from ..http_client import new_client

OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


class GigaChatError(RuntimeError):
    pass


class GigaChatClient:
    def __init__(self, settings: Settings, cache: Cache) -> None:
        self.settings = settings
        self.cache = cache
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self.calls = 0
        self.tokens_used = 0

    @property
    def available(self) -> bool:
        return bool(self.settings.gigachat_auth_key)

    def _access_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        with new_client(
            verify=self.settings.gigachat_verify_ssl,
            trust_env=self.settings.http_trust_env,
            timeout=30.0,
        ) as client:
            response = client.post(
                OAUTH_URL,
                headers={
                    "Authorization": f"Basic {self.settings.gigachat_auth_key}",
                    "RqUID": str(uuid.uuid4()),
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                data={"scope": self.settings.gigachat_scope},
            )
        if response.status_code >= 400:
            raise GigaChatError(f"OAuth {response.status_code}: {response.text[:200]}")
        payload = response.json()
        self._token = payload["access_token"]
        # expires_at приходит в миллисекундах
        self._token_expires_at = float(payload.get("expires_at", 0)) / 1000 or time.time() + 1500
        return self._token

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 700,
        attempts: int = 3,
    ) -> str:
        if not self.available:
            raise GigaChatError("Не задан GIGACHAT_AUTH_KEY")
        cache_key = {"model": self.settings.gigachat_model, "messages": messages, "t": temperature}
        cached = self.cache.get("llm", cache_key)
        if cached is not None:
            return cached
        body = {
            "model": self.settings.gigachat_model,
            "messages": messages,
            "temperature": temperature or 0.000001,  # 0 API не принимает
            "max_tokens": max_tokens,
        }
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                with new_client(
                    verify=self.settings.gigachat_verify_ssl,
                    trust_env=self.settings.http_trust_env,
                    timeout=90.0,
                ) as client:
                    response = client.post(
                        API_URL,
                        headers={
                            "Authorization": f"Bearer {self._access_token()}",
                            "Content-Type": "application/json",
                            "X-Request-ID": str(uuid.uuid4()),
                        },
                        json=body,
                    )
                if response.status_code == 401:
                    self._token = None
                    raise GigaChatError("401, обновляю токен")
                if response.status_code >= 400:
                    raise GigaChatError(f"{response.status_code}: {response.text[:200]}")
                payload = response.json()
                content = payload["choices"][0]["message"]["content"]
                self.calls += 1
                self.tokens_used += int((payload.get("usage") or {}).get("total_tokens") or 0)
                self.cache.set("llm", cache_key, content)
                return content
            except (httpx.HTTPError, GigaChatError, KeyError) as exc:
                last_error = exc
                time.sleep(1.5 * (attempt + 1))
        raise GigaChatError(f"GigaChat недоступен после {attempts} попыток: {last_error}")


def parse_json_object(raw: str) -> dict:
    """Модель любит обрамлять JSON в ```json ... ```, достаём объект как есть."""
    if not raw:
        return {}
    text = raw.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    match = _JSON_BLOCK.search(text)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
