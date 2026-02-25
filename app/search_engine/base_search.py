from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, List


@dataclass(frozen=True)
class SearchQuery:
    text: str
    max_results: int = 50
    search_engine_name: str = "Google"  # used for "(Google)" suffix later


class BaseSearchProvider(Protocol):
    async def search(self, query: SearchQuery) -> List[str]:
        """Return a list of video URLs (YouTube/Vimeo/others)."""
        ...