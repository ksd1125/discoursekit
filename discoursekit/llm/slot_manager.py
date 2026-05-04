"""Gemini project slot manager with round-robin rotation."""

from __future__ import annotations

from dataclasses import dataclass, field

from discoursekit.config import mask_key
from discoursekit.llm.rate_limiter import RateLimiterState


DEFAULT_RPM = 15
DEFAULT_TPM = 1_000_000
DEFAULT_RPD = 1500


@dataclass
class GeminiProjectSlot:
    """One Google Cloud project slot with an independent quota pool."""

    slot_name: str
    api_key: str
    project_id: str = ""
    rpm_quota: int = DEFAULT_RPM
    tpm_quota: int = DEFAULT_TPM
    rpd_quota: int = DEFAULT_RPD
    enabled: bool = True
    _limiter: RateLimiterState = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._limiter = RateLimiterState(
            rpm_limit=self.rpm_quota,
            tpm_limit=self.tpm_quota,
            rpd_limit=self.rpd_quota,
        )

    @property
    def masked_key(self) -> str:
        return mask_key(self.api_key)

    def can_request(self, estimated_tokens: int = 0) -> bool:
        return self.enabled and self._limiter.can_request(estimated_tokens)

    def record_request(self, tokens_used: int = 0) -> None:
        self._limiter.record_request(tokens_used)

    def report_429(self, error_type: str) -> None:
        self._limiter.report_429(error_type)

    def wait_seconds(self) -> float:
        return self._limiter.wait_seconds()


class GeminiSlotManager:
    """Manage up to 3 Gemini project slots."""

    MAX_SLOTS = 3

    def __init__(self) -> None:
        self._slots: list[GeminiProjectSlot] = []
        self._last_used_idx = -1

    def add_slot(self, slot: GeminiProjectSlot) -> None:
        if len(self._slots) >= self.MAX_SLOTS:
            raise ValueError(f"Maximum {self.MAX_SLOTS} slots allowed")
        self._slots.append(slot)

    def remove_slot(self, slot_name: str) -> None:
        self._slots = [slot for slot in self._slots if slot.slot_name != slot_name]
        self._last_used_idx = min(self._last_used_idx, len(self._slots) - 1)

    @property
    def slot_count(self) -> int:
        return len(self._slots)

    @property
    def slots(self) -> list[GeminiProjectSlot]:
        return list(self._slots)

    def get_next_available(self, estimated_tokens: int = 0) -> GeminiProjectSlot | None:
        """Return next available slot using round-robin order."""
        if not self._slots:
            return None

        n_slots = len(self._slots)
        for offset in range(n_slots):
            idx = (self._last_used_idx + 1 + offset) % n_slots
            slot = self._slots[idx]
            if slot.can_request(estimated_tokens):
                self._last_used_idx = idx
                return slot
        return None

    def report_429(self, slot: GeminiProjectSlot, error_type: str) -> None:
        slot.report_429(error_type)

    def all_exhausted(self) -> bool:
        return bool(self._slots) and all(not slot.can_request() for slot in self._slots)

    def min_wait_seconds(self) -> float:
        if not self._slots:
            return float("inf")
        return min(slot.wait_seconds() for slot in self._slots)

    def status_summary(self) -> list[dict]:
        """Return log-safe status for UI/reporting."""
        return [
            {
                "slot_name": slot.slot_name,
                "masked_key": slot.masked_key,
                "enabled": slot.enabled,
                "can_request": slot.can_request(),
                "wait_seconds": slot.wait_seconds(),
            }
            for slot in self._slots
        ]
