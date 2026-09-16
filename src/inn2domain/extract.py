"""Поиск реквизитов организации в тексте страницы.

Это главный источник твёрдых доказательств: если на сайте опубликован ИНН
или ОГРН нужной организации, связка "ИНН -> домен" подтверждена документально,
а не мнением модели.

Две ловушки, из-за которых наивный поиск подстроки даёт ложные срабатывания:
1) в подвале сайта часто стоит ИНН веб-студии ("разработка сайта — ООО ..."),
2) бухгалтерские и юридические фирмы публикуют реквизиты своих клиентов.
Поэтому вокруг найденного номера смотрим контекст.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from .inn import normalize_inn

_DIGIT_GROUP = re.compile(r"(?<![\d-])(\d[\d\s-]{8,18}\d)(?![\d-])")

DEVELOPER_MARKERS = (
    "разработка сайта", "разработка и продвижение", "создание сайта", "сделано в",
    "разработано", "разработчик сайта", "студия", "powered by", "работает на",
    "продвижение сайта", "техническая поддержка сайта", "дизайн сайта",
)

CONTEXT_WINDOW = 120


def _candidate_numbers(text: str) -> list[tuple[str, int]]:
    """Номера в тексте вместе с позицией: цифры могут быть разделены пробелами."""
    out = []
    for match in _DIGIT_GROUP.finditer(text):
        digits = normalize_inn(match.group(1))
        if 10 <= len(digits) <= 15:
            out.append((digits, match.start()))
    return out


def find_requisite(text: str, target: str) -> tuple[bool, str | None, bool]:
    """Ищем конкретный ИНН или ОГРН.

    Возвращает (найден, контекст, признак упоминания разработчика сайта).
    """
    if not text or not target:
        return False, None, False
    target_digits = normalize_inn(target)
    for digits, position in _candidate_numbers(text):
        if digits != target_digits:
            continue
        start = max(0, position - CONTEXT_WINDOW)
        context = text[start : position + len(target_digits) + CONTEXT_WINDOW]
        context = re.sub(r"\s+", " ", context).strip()
        lowered = context.lower()
        developer = any(marker in lowered for marker in DEVELOPER_MARKERS)
        return True, context, developer
    return False, None, False


_WORD = re.compile(r"[а-яёa-z0-9]+", re.I)
_STOP_TOKENS = {
    "ооо", "оао", "зао", "пао", "нао", "ао", "ип", "ано", "нко", "фгуп", "муп", "гуп",
    "компания", "фирма", "группа", "холдинг", "центр", "торговый", "дом", "завод",
    "производственная", "коммерческая", "научно", "и", "the", "ltd", "llc", "inc",
}


def _tokens(value: str | None) -> list[str]:
    if not value:
        return []
    return [t.lower() for t in _WORD.findall(value) if t.lower() not in _STOP_TOKENS and len(t) > 2]


def name_similarity(company_name: str | None, page_text: str | None) -> float:
    """Доля значимых слов названия, встретившихся на странице.

    Грубая метрика намеренно: точное совпадение названия юрлица и бренда на
    сайте — скорее исключение (ООО "Хайтек" может продавать под маркой Ozon).
    """
    name_tokens = _tokens(company_name)
    if not name_tokens or not page_text:
        return 0.0
    haystack = page_text.lower()
    hits = sum(1 for token in name_tokens if token in haystack)
    return round(hits / len(name_tokens), 3)


def fuzzy_ratio(left: str | None, right: str | None) -> float:
    if not left or not right:
        return 0.0
    return round(SequenceMatcher(None, left.lower(), right.lower()).ratio(), 3)


def brand_matches_domain(brand: str | None, domain: str | None) -> float:
    """Транслитерация бренда в домен: "Ромашка" -> romashka.ru.

    Сигнал слабый, но полезный, когда реквизитов на сайте нет.
    """
    if not brand or not domain:
        return 0.0
    table = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
        "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
        "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c",
        "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e",
        "ю": "yu", "я": "ya",
    }
    translit = "".join(table.get(ch, ch) for ch in brand.lower() if ch.isalnum() or ch.isspace())
    translit = translit.replace(" ", "")
    second_level = domain.split(".")[0].replace("-", "")
    if not translit or not second_level:
        return 0.0
    if translit == second_level:
        return 1.0
    if translit in second_level or second_level in translit:
        return 0.8
    return fuzzy_ratio(translit, second_level)
