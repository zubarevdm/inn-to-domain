"""SQLite-кэш ответов поиска, страниц и LLM.

Нужен по двум причинам: бесплатные лимиты API конечны, а прогоны оценки
качества должны быть воспроизводимыми.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class Cache:
    def __init__(self, path: Path, ttl_days: int = 14, enabled: bool = True) -> None:
        self.enabled = enabled
        self.ttl = ttl_days * 86400
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache ("
            "ns TEXT, key TEXT, value TEXT, created_at REAL, PRIMARY KEY (ns, key))"
        )
        self._conn.commit()

    @staticmethod
    def _key(payload: Any) -> str:
        blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def get(self, ns: str, payload: Any) -> Any | None:
        if not self.enabled:
            return None
        row = self._conn.execute(
            "SELECT value, created_at FROM cache WHERE ns = ? AND key = ?",
            (ns, self._key(payload)),
        ).fetchone()
        if not row:
            return None
        value, created_at = row
        if self.ttl and time.time() - created_at > self.ttl:
            return None
        return json.loads(value)

    def set(self, ns: str, payload: Any, value: Any) -> None:
        if not self.enabled:
            return
        self._conn.execute(
            "REPLACE INTO cache (ns, key, value, created_at) VALUES (?, ?, ?, ?)",
            (ns, self._key(payload), json.dumps(value, ensure_ascii=False, default=str), time.time()),
        )
        self._conn.commit()
