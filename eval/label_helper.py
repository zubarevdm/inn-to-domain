"""Помощник ручной разметки.

Ставить метки по ответу пайплайна нельзя — получится проверка себя на себе.
Скрипт собирает сырой материал (выдачу без фильтров и факт публикации ИНН на
сайтах-кандидатах), а решение принимает человек и записывает в eval/dataset.csv.

Запуск: python eval/label_helper.py 7707083893 [ещё ИНН...]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inn2domain.cache import Cache  # noqa: E402
from inn2domain.card import DaDataCardSource  # noqa: E402
from inn2domain.config import get_settings  # noqa: E402
from inn2domain.domains import is_restricted, registrable_domain  # noqa: E402
from inn2domain.extract import find_requisite  # noqa: E402
from inn2domain.fetch import PROBE_PATHS, PageFetcher, html_to_text  # noqa: E402
from inn2domain.search import build_search_provider  # noqa: E402

CHECK_TOP_DOMAINS = 4


def main(inns: list[str]) -> None:
    settings = get_settings()
    cache = Cache(settings.cache_path, settings.cache_ttl_days)
    cards = DaDataCardSource(settings, cache)
    search = build_search_provider(settings, cache)
    fetcher = PageFetcher(settings, cache)

    for inn in inns:
        company = cards.get(inn)
        print(f"\n=== {inn} | {company.name_short} | {company.city} | ОГРН {company.ogrn}")
        queries = [
            f'"{inn}"',
            f"ИНН {inn} сайт компании",
            f'"{company.brand}" официальный сайт' if company.brand else f"{inn} сайт",
        ]
        domains: list[str] = []
        for query in queries:
            try:
                hits = search.search(query, limit=8)
            except Exception as exc:
                print(f"  [поиск не отработал] {query}: {exc}")
                continue
            print(f"  -- {query}")
            for hit in hits[:8]:
                domain = registrable_domain(hit.url)
                mark = "агрегатор" if is_restricted(domain) else "         "
                print(f"     {mark} {domain:28} {hit.title[:60]}")
                if domain and not is_restricted(domain) and domain not in domains:
                    domains.append(domain)
        print("  -- проверка реквизитов на сайтах")
        for domain in domains[:CHECK_TOP_DOMAINS]:
            urls = [f"https://{domain}/"] + [f"https://{domain}{p}" for p in PROBE_PATHS[:3]]
            verdict = "нет"
            for url in urls:
                status, html, error = fetcher.get(url)
                if not html:
                    continue
                found, context, developer = find_requisite(html_to_text(html), inn)
                if found:
                    verdict = f"ДА ({url}){' [разработчик]' if developer else ''}"
                    break
            print(f"     {domain:28} ИНН на сайте: {verdict}")


if __name__ == "__main__":
    main(sys.argv[1:])
