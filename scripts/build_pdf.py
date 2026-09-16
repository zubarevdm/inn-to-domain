"""Сборка итогового PDF с ответами на оба задания.

Markdown превращается в HTML небольшим конвертером (внешних зависимостей нет,
разметка в документах простая), затем Edge в headless-режиме печатает страницу
в PDF.

Запуск: python scripts/build_pdf.py
"""
from __future__ import annotations

import html
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_HTML = ROOT / "docs" / "answer.html"
OUT_PDF = ROOT / "docs" / "Тестовое задание DaData, Зубарев.pdf"

EDGE_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
]

CSS = """
@page { size: A4; margin: 18mm 16mm; }
body { font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif; font-size: 10.5pt;
       line-height: 1.5; color: #111; }
h1 { font-size: 19pt; margin: 0 0 6pt; border-bottom: 2px solid #111; padding-bottom: 4pt; }
h2 { font-size: 14pt; margin: 16pt 0 6pt; }
h3 { font-size: 11.5pt; margin: 12pt 0 4pt; }
p, li { margin: 0 0 6pt; }
ul, ol { margin: 0 0 8pt; padding-left: 18pt; }
code { font-family: Consolas, "Courier New", monospace; font-size: 9.5pt;
       background: #f2f2f2; padding: 1px 3px; border-radius: 3px; }
pre { background: #f6f6f6; border: 1px solid #ddd; border-radius: 4px; padding: 8pt;
      font-family: Consolas, "Courier New", monospace; font-size: 8.5pt; line-height: 1.35;
      white-space: pre-wrap; page-break-inside: avoid; }
pre code { background: none; padding: 0; font-size: inherit; }
table { border-collapse: collapse; width: 100%; margin: 0 0 10pt; font-size: 9.5pt; }
th, td { border: 1px solid #ccc; padding: 4pt 6pt; text-align: left; }
th { background: #f0f0f0; }
a { color: #0b57d0; text-decoration: none; }
blockquote { margin: 0 0 8pt; padding-left: 10pt; border-left: 3px solid #ccc; color: #444; }
.pagebreak { page-break-before: always; }
.meta { color: #555; font-size: 9.5pt; margin-bottom: 14pt; }
"""

_INLINE = (
    (re.compile(r"`([^`]+)`"), r"<code>\1</code>"),
    (re.compile(r"\*\*([^*]+)\*\*"), r"<strong>\1</strong>"),
    (re.compile(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])"), r"<em>\1</em>"),
    (re.compile(r"\[([^\]]+)\]\(([^)]+)\)"), r'<a href="\2">\1</a>'),
)


def inline(text: str) -> str:
    out = html.escape(text, quote=False)
    for pattern, replacement in _INLINE:
        out = pattern.sub(replacement, out)
    return out


def render(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    parts: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if stripped.startswith("```"):
            index += 1
            block: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                block.append(lines[index])
                index += 1
            index += 1
            parts.append("<pre><code>" + html.escape("\n".join(block)) + "</code></pre>")
            continue

        if not stripped:
            index += 1
            continue

        heading = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if heading:
            level = len(heading.group(1))
            parts.append(f"<h{level}>{inline(heading.group(2))}</h{level}>")
            index += 1
            continue

        if stripped.startswith("|") and index + 1 < len(lines) and set(
            lines[index + 1].strip()
        ) <= set("|-: "):
            header = [c.strip() for c in stripped.strip("|").split("|")]
            index += 2
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append([c.strip() for c in lines[index].strip().strip("|").split("|")])
                index += 1
            head = "".join(f"<th>{inline(c)}</th>" for c in header)
            body = "".join(
                "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>" for row in rows
            )
            parts.append(f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")
            continue

        if re.match(r"^[-*]\s+", stripped) or re.match(r"^\d+\.\s+", stripped):
            ordered = bool(re.match(r"^\d+\.\s+", stripped))
            items: list[str] = []
            while index < len(lines):
                current = lines[index].strip()
                match = re.match(r"^(?:[-*]|\d+\.)\s+(.*)$", current)
                if not match:
                    if current and items and lines[index].startswith(("  ", "\t")):
                        items[-1] += " " + inline(current)
                        index += 1
                        continue
                    break
                items.append(inline(match.group(1)))
                index += 1
            tag = "ol" if ordered else "ul"
            parts.append(f"<{tag}>" + "".join(f"<li>{item}</li>" for item in items) + f"</{tag}>")
            continue

        if stripped.startswith(">"):
            parts.append(f"<blockquote>{inline(stripped.lstrip('> '))}</blockquote>")
            index += 1
            continue

        if set(stripped) <= set("-") and len(stripped) >= 3:
            index += 1
            continue

        paragraph = [stripped]
        index += 1
        while index < len(lines) and lines[index].strip() and not re.match(
            r"^(#{1,4}\s|[-*]\s|\d+\.\s|\||>|```)", lines[index].strip()
        ):
            paragraph.append(lines[index].strip())
            index += 1
        parts.append(f"<p>{inline(' '.join(paragraph))}</p>")
    return "\n".join(parts)


def find_browser() -> Path:
    for path in EDGE_CANDIDATES:
        if path.exists():
            return path
    raise SystemExit("Не найден Edge или Chrome для печати PDF")


def main() -> None:
    repo_url = "https://github.com/zubarevdm/inn-to-domain"
    task1 = (ROOT / "docs" / "task1.md").read_text(encoding="utf-8")
    task2 = (ROOT / "docs" / "task2.md").read_text(encoding="utf-8")

    body = [
        "<h1>Тестовое задание: аналитик данных, DaData</h1>",
        f'<p class="meta">Дмитрий Зубарев · репозиторий с кодом: '
        f'<a href="{repo_url}">{repo_url}</a></p>',
        render(task1),
        '<div class="pagebreak"></div>',
        render(task2),
    ]
    page = (
        "<!doctype html><html lang=\"ru\"><head><meta charset=\"utf-8\">"
        "<title>Тестовое задание DaData</title>"
        f"<style>{CSS}</style></head><body>{''.join(body)}</body></html>"
    )
    OUT_HTML.write_text(page, encoding="utf-8")

    browser = find_browser()
    subprocess.run(
        [
            str(browser),
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={OUT_PDF}",
            OUT_HTML.as_uri(),
        ],
        check=True,
        timeout=180,
    )
    # Edge закрывает файл чуть позже выхода процесса
    size = 0
    for _ in range(20):
        if OUT_PDF.exists():
            size = OUT_PDF.stat().st_size
            if size:
                break
        time.sleep(0.5)
    print(f"Готово: {OUT_PDF} ({size // 1024} КБ)")
    if not size:
        sys.exit(1)


if __name__ == "__main__":
    main()
