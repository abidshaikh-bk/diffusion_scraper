from __future__ import annotations
from dataclasses import dataclass

from app.filtering.keyword_filter import KeywordFilter
from app.filtering.duration_filter import DurationFilter
from app.models.video_metadata import VideoMetadata


@dataclass(frozen=True)
class RelevanceResult:
    is_relevant: bool
    reasons: list[str]


def build_relevance_text(meta: VideoMetadata) -> str:
    parts: list[str] = [
        meta.title or "",
        meta.description or "",
        meta.uploader or "",
        meta.channel or "",
    ]
    if meta.categories:
        parts.append(" ".join(meta.categories))
    if meta.tags:
        parts.append(" ".join(meta.tags))
    return " ".join(parts)


class RelevancePipeline:
    def __init__(self, keyword_filter: KeywordFilter, duration_filter: DurationFilter):
        self.keyword_filter = keyword_filter
        self.duration_filter = duration_filter

    def evaluate(self, meta: VideoMetadata) -> RelevanceResult:
        text = build_relevance_text(meta)
        ok1, r1 = self.keyword_filter.evaluate_text(text)
        ok2, r2 = self.duration_filter.evaluate(meta.duration)
        return RelevanceResult(is_relevant=(ok1 and ok2), reasons=r1 + r2)