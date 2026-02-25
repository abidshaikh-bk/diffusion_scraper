from __future__ import annotations

from dataclasses import dataclass


def hhmmss_to_seconds(s: str | None) -> int | None:
    if not s:
        return None
    s = s.strip()
    parts = s.split(":")
    if len(parts) != 3:
        return None
    try:
        h, m, sec = (int(x) for x in parts)
        return h * 3600 + m * 60 + sec
    except ValueError:
        return None


@dataclass(frozen=True)
class DurationFilter:
    min_sec: int | None = None
    max_sec: int | None = None

    def is_allowed(self, duration_hhmmss: str | None) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        dur = hhmmss_to_seconds(duration_hhmmss)

        # If missing duration, allow for now (we can tighten later)
        if dur is None:
            return True, reasons

        if self.min_sec is not None and dur < self.min_sec:
            reasons.append("too_short")
            return False, reasons

        if self.max_sec is not None and dur > self.max_sec:
            reasons.append("too_long")
            return False, reasons

        return True, reasons