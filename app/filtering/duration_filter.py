from __future__ import annotations
from dataclasses import dataclass


def hhmmss_to_seconds(hhmmss: str) -> int | None:
    if not hhmmss:
        return None
    parts = hhmmss.strip().split(":")
    if len(parts) != 3:
        return None
    try:
        h, m, s = (int(x) for x in parts)
        return h * 3600 + m * 60 + s
    except ValueError:
        return None


@dataclass(frozen=True)
class DurationFilter:
    min_sec: int | None = None
    max_sec: int | None = None

    def evaluate(self, duration_hhmmss: str) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        dur = hhmmss_to_seconds(duration_hhmmss)

        # If duration not known, allow (configurable later)
        if dur is None:
            return True, reasons

        if self.min_sec is not None and dur < self.min_sec:
            reasons.append("too_short")
            return False, reasons

        if self.max_sec is not None and dur > self.max_sec:
            reasons.append("too_long")
            return False, reasons

        return True, reasons