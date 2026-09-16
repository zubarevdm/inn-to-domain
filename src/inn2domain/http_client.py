"""Единая фабрика HTTP-клиентов.

trust_env по умолчанию выключен: системный прокси или VPN ломает доступ
к российским API (GigaChat закрывает соединение с зарубежных адресов).
"""
from __future__ import annotations

import httpx

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def new_client(
    *,
    verify: bool = True,
    timeout: float = 20.0,
    trust_env: bool = False,
    headers: dict[str, str] | None = None,
    follow_redirects: bool = True,
) -> httpx.Client:
    return httpx.Client(
        verify=verify,
        timeout=httpx.Timeout(timeout, connect=10.0),
        trust_env=trust_env,
        follow_redirects=follow_redirects,
        headers={"User-Agent": BROWSER_UA, **(headers or {})},
    )
