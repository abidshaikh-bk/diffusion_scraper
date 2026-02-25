from __future__ import annotations

from dataclasses import dataclass
from app.filtering.keyword_filter import KeywordFilter
from app.filtering.duration_filter import DurationFilter


@dataclass(frozen=True)
class RelevanceResult:
    is_relevant: bool
    reasons: list[str]


class RelevancePipeline:
    def __init__(self, keyword_filter: KeywordFilter, duration_filter: DurationFilter):
        self.keyword_filter = keyword_filter
        self.duration_filter = duration_filter

    def evaluate(self, title: str | None, description: str | None, duration_hhmmss: str | None) -> RelevanceResult:
        ok1, r1 = self.keyword_filter.is_relevant(title, description)
        ok2, r2 = self.duration_filter.is_allowed(duration_hhmmss)
        reasons = r1 + r2
        return RelevanceResult(is_relevant=(ok1 and ok2), reasons=reasons)