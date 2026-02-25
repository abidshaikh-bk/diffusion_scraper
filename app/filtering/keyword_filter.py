from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class KeywordFilter:
    include: tuple[str, ...]
    exclude: tuple[str, ...] = ()

    def is_relevant(self, title: str | None, description: str | None) -> tuple[bool, list[str]]:
        text = f"{title or ''} {description or ''}".lower()
        reasons: list[str] = []

        if any(k.lower() in text for k in self.exclude):
            reasons.append("contains_excluded_keyword")
            return False, reasons

        if self.include and not any(k.lower() in text for k in self.include):
            reasons.append("missing_required_keywords")
            return False, reasons

        return True, reasons