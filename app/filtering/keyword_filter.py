from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class KeywordFilter:
    include: tuple[str, ...]
    exclude: tuple[str, ...] = ()
    min_include_hits: int = 1

    def evaluate_text(self, text: str) -> tuple[bool, list[str]]:
        text_l = (text or "").lower()
        reasons: list[str] = []

        for k in self.exclude:
            if k.lower() in text_l:
                reasons.append(f"excluded_keyword:{k}")
                return False, reasons

        hits = [k for k in self.include if k.lower() in text_l]
        if self.include and len(hits) < self.min_include_hits:
            reasons.append(f"include_hits:{len(hits)}<{self.min_include_hits}")
            return False, reasons

        reasons.append(f"include_hits:{len(hits)}")
        return True, reasons