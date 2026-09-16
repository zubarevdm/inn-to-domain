"""Валидация ИНН и ОГРН по контрольным суммам.

Отсекаем мусор до того, как тратить лимиты поиска и LLM, а на стороне
проверки сайта не принимаем за реквизит любую последовательность цифр.
"""
from __future__ import annotations

import re

_DIGITS = re.compile(r"\D")
_W10 = (2, 4, 10, 3, 5, 9, 4, 6, 8)
_W12_1 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_W12_2 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)


def normalize_inn(raw: str) -> str:
    return _DIGITS.sub("", raw or "")


def _checksum(digits: str, weights: tuple[int, ...]) -> int:
    return sum(int(d) * w for d, w in zip(digits, weights)) % 11 % 10


def is_valid_inn(raw: str) -> bool:
    inn = normalize_inn(raw)
    if len(inn) == 10:
        return _checksum(inn, _W10) == int(inn[9])
    if len(inn) == 12:
        return _checksum(inn, _W12_1) == int(inn[10]) and _checksum(inn, _W12_2) == int(inn[11])
    return False


def is_valid_ogrn(raw: str) -> bool:
    ogrn = normalize_inn(raw)
    if len(ogrn) == 13:
        return int(ogrn[:12]) % 11 % 10 == int(ogrn[12])
    if len(ogrn) == 15:
        return int(ogrn[:14]) % 13 % 10 == int(ogrn[14])
    return False


def inn_kind(raw: str) -> str:
    """ЮЛ (10 цифр) или ИП/физлицо (12 цифр)."""
    return {10: "legal", 12: "individual"}.get(len(normalize_inn(raw)), "unknown")
