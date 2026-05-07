"""LLM API budget tracking and priority management."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class LLMPriority(IntEnum):
    """Priority classes for interactive and batch LLM work."""

    SEARCH_ADVICE = 1
    ENRICHMENT = 2
    KEYWORD_INTERPRET = 3
    CODING_SUGGEST = 4


_CATEGORY_PRIORITY = {
    "search_advice": LLMPriority.SEARCH_ADVICE,
    "enrichment": LLMPriority.ENRICHMENT,
    "keyword_interpret": LLMPriority.KEYWORD_INTERPRET,
    "coding_suggest": LLMPriority.CODING_SUGGEST,
}


@dataclass
class BudgetTracker:
    """Track daily LLM request budget by category."""

    daily_limit: int
    used: dict[str, int] = field(default_factory=dict)

    @property
    def total_used(self) -> int:
        return sum(self.used.values())

    @property
    def remaining(self) -> int:
        return max(0, self.daily_limit - self.total_used)

    @property
    def usage_pct(self) -> float:
        return self.total_used / self.daily_limit * 100 if self.daily_limit else 0.0

    def can_request(self, category: str) -> bool:
        """Return whether one more request is allowed for a category."""
        if self.remaining <= 0:
            return False
        priority = _CATEGORY_PRIORITY.get(category, LLMPriority.CODING_SUGGEST)
        if self.usage_pct >= 95 and priority >= LLMPriority.KEYWORD_INTERPRET:
            return False
        if self.usage_pct >= 90 and priority >= LLMPriority.CODING_SUGGEST:
            return False
        return True

    def record(self, category: str, count: int = 1) -> None:
        self.used[category] = self.used.get(category, 0) + max(0, int(count))

    def summary(self) -> dict:
        return {
            "daily_limit": self.daily_limit,
            "total_used": self.total_used,
            "remaining": self.remaining,
            "usage_pct": round(self.usage_pct, 1),
            "by_category": dict(self.used),
        }
