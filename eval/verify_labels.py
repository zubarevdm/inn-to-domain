"""Проверка меток.

Метка в dataset.csv должна опираться на доказательство, а не на память
разметчика. Скрипт берёт пары «ИНН, предполагаемый домен» и сообщает, найден
ли ИНН или ОГРН организации на этом сайте.

Запуск: python eval/verify_labels.py 7707083893=sberbank.ru 7736050003=gazprom.ru
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inn2domain.cache import Cache  # noqa: E402
from inn2domain.card import DaDataCardSource  # noqa: E402
from inn2domain.config import get_settings  # noqa: E402
from inn2domain.extract import find_requisite, name_similarity  # noqa: E402
from inn2domain.fetch import PROBE_PATHS, PageFetcher, html_to_text  # noqa: E402


def main(pairs: list[str]) -> None:
    settings = get_settings()
    cache = Cache(settings.cache_path, settings.cache_ttl_days)
    cards = DaDataCardSource(settings, cache)
    fetcher = PageFetcher(settings, cache)

    for pair in pairs:
        inn, _, domain = pair.partition("=")
        company = cards.get(inn)
        verdict = "нет"
        detail = ""
        for url in [f"https://{domain}/"] + [f"https://{domain}{p}" for p in PROBE_PATHS]:
            status, html, error = fetcher.get(url)
            if not html:
                detail = detail or f"http={status} {error or ''}".strip()
                continue
            text = html_to_text(html)
            inn_found, context, developer = find_requisite(text, inn)
            ogrn_found, _, _ = find_requisite(text, company.ogrn or "")
            if inn_found or ogrn_found:
                verdict = "ИНН" if inn_found else "ОГРН"
                detail = f"{url}{' [разработчик]' if developer else ''}"
                break
            detail = f"название на странице: {name_similarity(company.brand, text)}"
        print(f"{inn} {domain:22} {company.name_short[:28] if company.name_short else '':30} {verdict:5} {detail[:70]}")


if __name__ == "__main__":
    main(sys.argv[1:])
