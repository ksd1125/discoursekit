"""RPM, TPM, and RPD rate limiter for API quota management."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


PT_OFFSET = timedelta(hours=-8)


def _now_utc() -> float:
    return time.time()


def _pt_midnight_next(now_utc: float) -> float:
    """Return Unix timestamp of the next PT midnight from now_utc."""
    dt = datetime.fromtimestamp(now_utc, tz=timezone.utc)
    pt_now = dt + PT_OFFSET
    pt_today_midnight = pt_now.replace(hour=0, minute=0, second=0, microsecond=0)
    pt_next_midnight = pt_today_midnight + timedelta(days=1)
    utc_next = pt_next_midnight - PT_OFFSET
    return utc_next.timestamp()


@dataclass
class RateLimiterState:
    """Tracks usage for one slot across RPM, TPM, and RPD."""

    rpm_limit: int
    tpm_limit: int
    rpd_limit: int
    _rpm_timestamps: list[float] = field(default_factory=list)
    _tpm_window: list[tuple[float, int]] = field(default_factory=list)
    _rpd_count: int = 0
    _rpd_reset_at: float = 0.0

    def __post_init__(self) -> None:
        if self._rpd_reset_at == 0.0:
            self._rpd_reset_at = _pt_midnight_next(_now_utc())

    def can_request(self, estimated_tokens: int = 0) -> bool:
        """Return True if a request can be made right now."""
        now = _now_utc()
        self._maybe_reset_rpd(now)
        self._prune_rpm(now)
        self._prune_tpm(now)

        if self._rpd_count >= self.rpd_limit:
            return False
        if len(self._rpm_timestamps) >= self.rpm_limit:
            return False
        if estimated_tokens > 0:
            current_tpm = sum(tokens for _, tokens in self._tpm_window)
            if current_tpm + estimated_tokens > self.tpm_limit:
                return False
        return True

    def record_request(self, tokens_used: int = 0) -> None:
        """Record one request and optional token usage."""
        now = _now_utc()
        self._rpm_timestamps.append(now)
        if tokens_used > 0:
            self._tpm_window.append((now, tokens_used))
        self._rpd_count += 1

    def wait_seconds(self) -> float:
        """Estimate seconds until next request is possible."""
        now = _now_utc()
        self._maybe_reset_rpd(now)
        self._prune_rpm(now)
        self._prune_tpm(now)

        if self._rpd_count >= self.rpd_limit:
            return max(0.0, self._rpd_reset_at - now)
        if len(self._rpm_timestamps) >= self.rpm_limit:
            return max(0.0, self._rpm_timestamps[0] + 60.0 - now)
        return 0.0

    def report_429(self, error_type: str) -> None:
        """Record a 429 response by quota axis."""
        if error_type == "rpd":
            self._rpd_count = self.rpd_limit

    def _maybe_reset_rpd(self, now: float) -> None:
        if now >= self._rpd_reset_at:
            self._rpd_count = 0
            self._rpd_reset_at = _pt_midnight_next(now)

    def _prune_rpm(self, now: float) -> None:
        cutoff = now - 60.0
        self._rpm_timestamps = [timestamp for timestamp in self._rpm_timestamps if timestamp > cutoff]

    def _prune_tpm(self, now: float) -> None:
        cutoff = now - 60.0
        self._tpm_window = [(timestamp, tokens) for timestamp, tokens in self._tpm_window if timestamp > cutoff]
