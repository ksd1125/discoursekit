"""LLM budget manager tests."""

from discoursekit.llm.budget_manager import BudgetTracker


def test_initial_state():
    tracker = BudgetTracker(daily_limit=100)

    assert tracker.total_used == 0
    assert tracker.remaining == 100


def test_record():
    tracker = BudgetTracker(daily_limit=100)
    tracker.record("enrichment", 3)

    assert tracker.total_used == 3
    assert tracker.used["enrichment"] == 3


def test_priority_90pct():
    tracker = BudgetTracker(daily_limit=100, used={"enrichment": 90})

    assert not tracker.can_request("coding_suggest")
    assert tracker.can_request("keyword_interpret")


def test_priority_95pct():
    tracker = BudgetTracker(daily_limit=100, used={"enrichment": 95})

    assert not tracker.can_request("keyword_interpret")
    assert tracker.can_request("search_advice")


def test_summary():
    tracker = BudgetTracker(daily_limit=100, used={"search_advice": 2})

    assert tracker.summary()["remaining"] == 98
    assert tracker.summary()["by_category"]["search_advice"] == 2
