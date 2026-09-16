"""Скачивание страниц кандидатов и превращение HTML в текст.

Тяжёлый парсер не нужен: нам требуются только текст, заголовок и ссылки на
страницы с реквизитами. Зато нужны жёсткие лимиты по времени и размеру —
кандидатов много, а среди них попадаются и мегабайтные главные страницы.
"""
from __future__ import annotations

import re
from html import unescape
from urllib.parse import urljoin

import httpx

from .cache import Cache
from .config import Settings
from .http_client import new_client

MAX_BYTES = 400_000

_SCRIPTS = re.compile(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", re.I | re.S)
_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[ \t\r\f\v ]+")
_NEWLINES = re.compile(r"\n{3,}")
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_META_CHARSET = re.compile(rb"""charset=["']?\s*([\w\-]+)""", re.I)
_LINK = re.compile(r"""<a\s[^>]*href=["']([^"'#]+)["'][^>]*>(.*?)</a>""", re.I | re.S)

# Страницы, где российские компании публикуют ИНН и ОГРН.
CONTACT_HINTS = (
    "контакт", "реквизит", "о компании", "о нас", "about", "contact", "kontakt",
    "rekvizity", "requisites", "политика", "privacy", "oferta", "оферта", "юридическ",
    "информация о продавце", "impressum",
)
CONTACT_PATHS = (
    "/contacts", "/contact", "/kontakty", "/about", "/o-kompanii", "/rekvizity",
    "/privacy", "/policy", "/oferta", "/info",
)

# Если ссылок на реквизиты в разметке не нашлось (одностраничники, сайты на JS),
# пробуем типовые адреса напрямую.
PROBE_PATHS = ("/contacts", "/kontakty", "/about", "/company", "/rekvizity", "/privacy")


def decode(content: bytes, declared: str | None) -> str:
    """Кодировку часто объявляют только в meta, а windows-1251 на рунете жив."""
    candidates = []
    if declared:
        candidates.append(declared)
    match = _META_CHARSET.search(content[:4000])
    if match:
        candidates.append(match.group(1).decode("ascii", "ignore"))
    candidates += ["utf-8", "windows-1251"]
    for encoding in candidates:
        try:
            return content.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return content.decode("utf-8", errors="ignore")


def html_to_text(html: str) -> str:
    text = _SCRIPTS.sub(" ", html)
    text = _TAGS.sub(" ", text)
    text = unescape(text)
    text = _SPACES.sub(" ", text)
    return _NEWLINES.sub("\n\n", text).strip()


def page_title(html: str) -> str | None:
    match = _TITLE.search(html)
    return html_to_text(match.group(1))[:200] if match else None


def contact_links(html: str, base_url: str, limit: int = 3) -> list[str]:
    """Ссылки на страницы, где вероятны реквизиты."""
    found: list[str] = []
    for href, anchor in _LINK.findall(html):
        if href.lower().startswith(("mailto:", "tel:", "javascript:")):
            continue
        anchor_text = html_to_text(anchor).lower()
        target = urljoin(base_url, href)
        haystack = f"{anchor_text} {href.lower()}"
        if any(hint in haystack for hint in CONTACT_HINTS) or any(
            path in href.lower() for path in CONTACT_PATHS
        ):
            if target not in found:
                found.append(target)
        if len(found) >= limit:
            break
    return found


class PageFetcher:
    def __init__(self, settings: Settings, cache: Cache, timeout: float = 15.0) -> None:
        self.settings = settings
        self.cache = cache
        self.timeout = timeout

    def get(self, url: str) -> tuple[int | None, str, str | None]:
        """Возвращает (http-статус, html, ошибка). Ошибки сети — часть данных,
        недоступный сайт это сигнал, а не повод падать."""
        cached = self.cache.get("page", {"url": url})
        if cached is not None:
            return cached.get("status"), cached.get("html", ""), cached.get("error")
        status: int | None = None
        html = ""
        error: str | None = None
        try:
            with new_client(trust_env=self.settings.http_trust_env, timeout=self.timeout) as client:
                with client.stream("GET", url) as response:
                    status = response.status_code
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_bytes():
                        chunks.append(chunk)
                        size += len(chunk)
                        if size >= MAX_BYTES:
                            break
                    html = decode(b"".join(chunks), response.charset_encoding)
        except httpx.HTTPError as exc:
            error = f"{type(exc).__name__}: {exc}"[:200]
        except Exception as exc:  # битый TLS, редирект в никуда и прочая экзотика рунета
            error = f"{type(exc).__name__}: {exc}"[:200]
        self.cache.set("page", {"url": url}, {"status": status, "html": html[:200_000], "error": error})
        return status, html, error
