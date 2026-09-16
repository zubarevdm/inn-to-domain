"""Прогон пайплайна по размеченному набору и расчёт метрик.

Считаем не одну общую точность, а разложение, которое отвечает на вопрос
"можно ли отдавать это клиенту":

  precision — доля верных среди выданных доменов. Главная метрика: неверный
              домен в справочнике дороже, чем пустое поле;
  recall    — доля найденных сайтов среди организаций, у которых сайт есть;
  null-accuracy — как часто пайплайн правильно молчит;
  false positive — выдал домен там, где сайта нет или домен чужой.

Три режима запускаются по одному и тому же набору, чтобы было видно вклад
каждого этапа (абляция).

Запуск: python eval/run_eval.py [--modes full,verify,search_only] [--limit N]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inn2domain.pipeline import Pipeline  # noqa: E402

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "dataset.csv"
OUT_DIR = ROOT / "out"


def load_dataset(limit: int | None = None) -> list[dict[str, str]]:
    with DATASET.open(encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("inn")]
    return rows[:limit] if limit else rows


def expected_set(row: dict[str, str]) -> set[str]:
    """В метке допускается несколько равноправных доменов через '|'."""
    raw = (row.get("expected_domain") or "").strip()
    if not raw or raw.lower() in {"null", "none", ""}:
        return set()
    return {part.strip().lower() for part in raw.split("|") if part.strip()}


def evaluate(mode: str, rows: list[dict[str, str]], use_cache: bool = True) -> dict:
    pipeline = Pipeline(mode=mode, use_cache=use_cache)
    records = []
    started = time.time()
    for row in rows:
        result = pipeline.run(row["inn"])
        expected = expected_set(row)
        got = (result.domain or "").lower() or None
        if expected:
            outcome = "верно" if got in expected else ("пропуск" if got is None else "ошибка")
        else:
            outcome = "верно" if got is None else "ложный ответ"
        records.append(
            {
                "inn": row["inn"],
                "name": row.get("name", ""),
                "stratum": row.get("stratum", ""),
                "expected": "|".join(sorted(expected)) or None,
                "got": got,
                "outcome": outcome,
                "confidence": result.confidence,
                "decided_by": result.decided_by,
                "reason": result.reason,
                "elapsed_sec": result.stats.get("elapsed_sec"),
            }
        )
        print(f"  {row['inn']} {outcome:12} ожидали={'|'.join(sorted(expected)) or 'null':22} получили={got}")

    has_site = [r for r in records if r["expected"]]
    no_site = [r for r in records if not r["expected"]]
    answered = [r for r in records if r["got"]]
    correct_answers = [r for r in answered if r["outcome"] == "верно"]

    metrics = {
        "режим": mode,
        "организаций": len(records),
        "из них с сайтом": len(has_site),
        "из них без сайта": len(no_site),
        "выдано доменов": len(answered),
        "точность (precision)": round(len(correct_answers) / len(answered), 3) if answered else None,
        "полнота (recall)": round(
            len([r for r in has_site if r["outcome"] == "верно"]) / len(has_site), 3
        )
        if has_site
        else None,
        "верных null": round(
            len([r for r in no_site if r["outcome"] == "верно"]) / len(no_site), 3
        )
        if no_site
        else None,
        "общая доля верных": round(
            len([r for r in records if r["outcome"] == "верно"]) / len(records), 3
        )
        if records
        else None,
        "ложных ответов на организациях без сайта": len(
            [r for r in no_site if r["outcome"] == "ложный ответ"]
        ),
        "неверных доменов": len([r for r in records if r["outcome"] == "ошибка"]),
        "секунд на организацию": round((time.time() - started) / max(len(records), 1), 1),
        "решения": dict(Counter(r["decided_by"] for r in records)),
    }
    return {"metrics": metrics, "records": records}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--modes", default="search_only,verify,full")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    rows = load_dataset(args.limit)
    OUT_DIR.mkdir(exist_ok=True)
    report = {}
    for mode in args.modes.split(","):
        print(f"\n=== режим {mode} ===")
        result = evaluate(mode.strip(), rows, use_cache=not args.no_cache)
        report[mode.strip()] = result
        (OUT_DIR / f"records_{mode.strip()}.json").write_text(
            json.dumps(result["records"], ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print("\n=== метрики ===")
    for mode, result in report.items():
        print(json.dumps(result["metrics"], ensure_ascii=False, indent=2))
    (OUT_DIR / "metrics.json").write_text(
        json.dumps({m: r["metrics"] for m, r in report.items()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
