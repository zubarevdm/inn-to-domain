"""WHOIS домена.

Задумывался как независимый официальный источник: в зонах .ru, .su и .рф
реестр отдаёт поля org и taxpayer-id, то есть название и ИНН владельца домена.
Связка "ИНН -> домен" тут была бы документальной.

Проверка на живых доменах показала, что сейчас оба поля скрыты: у yandex.ru,
gazprom.ru, rzd.ru, wildberries.ru и у мелких доменов они приходят пустыми.
Реестр закрыл их для публичного WHOIS, данные остались у регистраторов.
Поэтому модуль используется в двух узких ролях: дата регистрации домена
(нужна для контроля перехвата освободившихся доменов) и редкие записи,
где владелец всё же указан. Если появится доступ к данным регистратора,
источник сразу станет сильным — код к этому готов.
"""
from __future__ import annotations

import re
import socket

from .cache import Cache
from .extract import fuzzy_ratio
from .inn import normalize_inn

WHOIS_SERVERS = {
    "ru": "whois.tcinet.ru",
    "su": "whois.tcinet.ru",
    "рф": "whois.tcinet.ru",
}
_ORG = re.compile(r"^org:[ 	]*(\S.*?)\s*$", re.I | re.M)
_TAXPAYER = re.compile(r"^taxpayer-id:[ 	]*(\S.*?)\s*$", re.I | re.M)
_CREATED = re.compile(r"^created:\s*(.+)$", re.I | re.M)
_PERSON = re.compile(r"private person", re.I)
_QUOTES = re.compile(r"[\"«»']")


def _zone(domain: str) -> str:
    return domain.rsplit(".", 1)[-1].lower()


def query(domain: str, cache: Cache, timeout: float = 6.0) -> str | None:
    """Сырой ответ WHOIS. Сеть может не ответить — это не ошибка пайплайна."""
    server = WHOIS_SERVERS.get(_zone(domain))
    if not server:
        return None
    cached = cache.get("whois", {"domain": domain})
    if cached is not None:
        return cached or None
    ascii_domain = domain
    try:
        ascii_domain = domain.encode("idna").decode("ascii")
    except Exception:
        pass
    text = ""
    try:
        with socket.create_connection((server, 43), timeout=timeout) as sock:
            sock.sendall(f"{ascii_domain}\r\n".encode())
            chunks = []
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
            text = b"".join(chunks).decode("utf-8", errors="replace")
    except OSError:
        text = ""
    cache.set("whois", {"domain": domain}, text)
    return text or None


def owner(domain: str, cache: Cache) -> tuple[str | None, str | None, str | None]:
    """(название владельца, ИНН владельца, дата регистрации домена)."""
    raw = query(domain, cache)
    if not raw:
        return None, None, None
    org_match = _ORG.search(raw)
    org = org_match.group(1).strip() if org_match else None
    if org and _PERSON.search(org):
        org = None
    tax_match = _TAXPAYER.search(raw)
    created_match = _CREATED.search(raw)
    return (
        org,
        tax_match.group(1).strip() if tax_match else None,
        created_match.group(1).strip() if created_match else None,
    )


def owner_similarity(org: str | None, company_name: str | None, brand: str | None) -> float:
    """Насколько владелец домена похож на нашу организацию.

    В WHOIS названия пишут латиницей и по-разному: "OOO Romashka", "Romashka Ltd",
    "JSC ROMASHKA". Поэтому сравниваем и с полным названием, и с брендом.
    """
    if not org:
        return 0.0
    cleaned = _QUOTES.sub(" ", org).lower()
    cleaned = re.sub(r"\b(ooo|zao|oao|pao|jsc|llc|ltd|inc|company|co)\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    best = 0.0
    for name in filter(None, (brand, company_name)):
        target = _QUOTES.sub(" ", name).lower().strip()
        best = max(best, fuzzy_ratio(cleaned, target))
        if cleaned and target and (cleaned in target or target in cleaned):
            best = max(best, 0.85)
    return round(best, 3)


def contains_inn(raw: str | None, inn: str) -> bool:
    """Некоторые регистраторы оставляют ИНН владельца прямо в ответе WHOIS."""
    if not raw:
        return False
    return normalize_inn(inn) in normalize_inn(raw)
