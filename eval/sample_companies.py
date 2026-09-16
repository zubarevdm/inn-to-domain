"""Отбор организаций для тестового набора.

Набор известных компаний брать нельзя: на них любой пайплайн выглядит хорошо.
Поэтому вторую половину выборки набираем через подсказки DaData по нейтральным
словам из названий — так в набор попадают обычные ООО и ИП, у которых сайта
может и не быть.

Запуск: python eval/sample_companies.py > eval/sample_raw.csv
"""
from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inn2domain.config import get_settings  # noqa: E402
from inn2domain.http_client import new_client  # noqa: E402

SUGGEST_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party"

# Корни слов, а не целые названия: по ним подсказки отдают разные компании,
# а не десяток одноимённых.
SEED_WORDS = [
    "строй", "техно", "мед", "транс", "агро", "пласт", "торг", "сервис",
    "инжиниринг", "групп", "софт", "ресурс",
]
# Для ИП фамилии: названия у них нет, есть ФИО.
SEED_SURNAMES = ["Иванов", "Кузнецов", "Смирнов", "Попов", "Соколов", "Новиков"]
RANDOM_SEED = 42


def suggest(query: str, count: int = 5, kind: str = "LEGAL") -> list[dict]:
    settings = get_settings()
    body = {"query": query, "count": count, "type": kind, "status": ["ACTIVE"]}
    with new_client(trust_env=settings.http_trust_env, timeout=20.0) as client:
        response = client.post(
            SUGGEST_URL,
            headers={
                "Authorization": f"Token {settings.dadata_token}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        response.raise_for_status()
        return response.json().get("suggestions", [])


def main() -> None:
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(["inn", "name", "city", "kind"])
    seen: set[str] = set()
    for word in SEED_WORDS:
        for kind in ("LEGAL", "INDIVIDUAL"):
            for item in suggest(word, count=3, kind=kind):
                data = item.get("data") or {}
                inn = data.get("inn")
                if not inn or inn in seen:
                    continue
                seen.add(inn)
                address = (data.get("address") or {}).get("data") or {}
                writer.writerow(
                    [inn, item.get("value"), address.get("city") or "", kind.lower()]
                )


if __name__ == "__main__":
    main()
