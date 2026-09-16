"""Сборка отчёта по результатам прогона.

Таблицы в отчёте генерируются из eval/out, чтобы цифры в тексте нельзя было
разойтись с фактическим прогоном. Комментарии к ошибкам пишутся руками ниже,
в разделе «Разбор ошибок».

Запуск: python eval/run_eval.py && python eval/make_report.py
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
MODES = ["search_only", "verify", "full"]
MODE_TITLES = {
    "search_only": "только поиск",
    "verify": "поиск + проверка реквизитов",
    "full": "полный пайплайн",
}
ROWS = [
    ("организаций", "организаций"),
    ("выдано доменов", "выдано доменов"),
    ("точность (precision)", "точность"),
    ("полнота (recall)", "полнота"),
    ("верных null", "верных null"),
    ("общая доля верных", "доля верных ответов"),
    ("неверных доменов", "неверных доменов"),
    ("ложных ответов на организациях без сайта", "ложных ответов там, где сайта нет"),
    ("секунд на организацию", "секунд на организацию"),
]


def fmt(value) -> str:
    if value is None:
        return "—"
    return str(value)


def main() -> None:
    metrics = json.loads((OUT / "metrics.json").read_text(encoding="utf-8"))
    strata = {}
    with (ROOT / "dataset.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            strata[row["inn"]] = row.get("stratum", "")

    lines = ["## Абляция: что даёт каждый этап", ""]
    header = "| метрика | " + " | ".join(MODE_TITLES[m] for m in MODES if m in metrics) + " |"
    lines.append(header)
    lines.append("|" + "---|" * (1 + len([m for m in MODES if m in metrics])))
    for key, title in ROWS:
        cells = [fmt(metrics[m].get(key)) for m in MODES if m in metrics]
        lines.append(f"| {title} | " + " | ".join(cells) + " |")

    full = json.loads((OUT / "records_full.json").read_text(encoding="utf-8"))
    by_stratum: dict[str, list[dict]] = defaultdict(list)
    for record in full:
        by_stratum[strata.get(record["inn"], record.get("stratum", ""))].append(record)

    lines += ["", "## Полный пайплайн по стратам", "",
              "| страта | организаций | верно | ошибки | пропуски |", "|---|---|---|---|---|"]
    for stratum, records in by_stratum.items():
        correct = sum(1 for r in records if r["outcome"] == "верно")
        wrong = sum(1 for r in records if r["outcome"] in ("ошибка", "ложный ответ"))
        missed = sum(1 for r in records if r["outcome"] == "пропуск")
        lines.append(f"| {stratum} | {len(records)} | {correct} | {wrong} | {missed} |")

    lines += ["", "## Как пайплайн принимал решения", "", "| основание | случаев |", "|---|---|"]
    for reason, count in sorted(
        metrics["full"]["решения"].items(), key=lambda kv: -kv[1]
    ):
        lines.append(f"| {reason} | {count} |")

    problems = [r for r in full if r["outcome"] != "верно"]
    lines += ["", "## Все расхождения с разметкой", ""]
    for record in problems:
        lines.append(
            f"- **{record['inn']} {record['name']}**: ожидали `{record['expected']}`, "
            f"получили `{record['got']}` ({record['outcome']}). {record['reason']}"
        )

    (OUT / "tables.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
