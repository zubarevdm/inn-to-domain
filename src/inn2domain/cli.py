"""CLI: inn2domain 7707083893 [--verbose] [--trace] [--mode full|verify|search_only]."""
from __future__ import annotations

import argparse
import json
import sys

from .pipeline import Pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="inn2domain",
        description="Определяет домен официального сайта организации по ИНН",
    )
    parser.add_argument("inn", nargs="+", help="ИНН организации (можно несколько)")
    parser.add_argument(
        "--mode",
        choices=["full", "verify", "search_only"],
        default="full",
        help="full — поиск + проверка сайта + LLM; остальные режимы нужны для абляции",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="ход работы в stderr")
    parser.add_argument("--trace", action="store_true", help="выводить кандидатов и доказательства")
    parser.add_argument("--no-cache", action="store_true", help="игнорировать кэш")
    args = parser.parse_args(argv)

    pipeline = Pipeline(mode=args.mode, use_cache=not args.no_cache, verbose=args.verbose)
    exit_code = 0
    for inn in args.inn:
        result = pipeline.run(inn)
        if args.trace:
            print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
        else:
            print(json.dumps(result.answer(), ensure_ascii=False))
        if args.verbose:
            print(
                f"  confidence={result.confidence} "
                f"({result.decided_by}): {result.reason}",
                file=sys.stderr,
            )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
