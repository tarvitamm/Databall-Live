"""Model answers cached per match, keyed by everything the answer depends on, so a replay never pays twice."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


class Cache:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.items: dict[str, dict] = {}
        self.dirty = False
        if path and path.exists():
            self.items = json.loads(path.read_text())

    @staticmethod
    def key(kind: str, parts: object) -> str:
        raw = json.dumps([kind, parts], sort_keys=True, ensure_ascii=False, default=str)
        return f"{kind}:{hashlib.sha1(raw.encode()).hexdigest()[:16]}"

    def get(self, key: str) -> dict | None:
        return self.items.get(key)

    def put(self, key: str, value: dict) -> None:
        self.items[key] = value
        self.dirty = True

    def save(self) -> None:
        if self.path and self.dirty:
            self.path.write_text(json.dumps(self.items, ensure_ascii=False))
            self.dirty = False
