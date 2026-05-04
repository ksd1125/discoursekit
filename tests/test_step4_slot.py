"""Step 4 slot manager tests."""

from __future__ import annotations

import pytest

from discoursekit.llm.slot_manager import GeminiProjectSlot, GeminiSlotManager


def test_slot_creation():
    slot = GeminiProjectSlot(slot_name="personal", api_key="test-key-12345")
    assert slot.masked_key != "test-key-12345"
    assert "****" in slot.masked_key
    assert slot.can_request()


def test_manager_add_max_3():
    manager = GeminiSlotManager()
    for i in range(3):
        manager.add_slot(GeminiProjectSlot(slot_name=f"slot{i}", api_key=f"key{i}"))
    assert manager.slot_count == 3
    with pytest.raises(ValueError, match="Maximum"):
        manager.add_slot(GeminiProjectSlot(slot_name="slot4", api_key="key4"))


def test_manager_round_robin():
    manager = GeminiSlotManager()
    manager.add_slot(GeminiProjectSlot(slot_name="a", api_key="ka"))
    manager.add_slot(GeminiProjectSlot(slot_name="b", api_key="kb"))
    assert manager.get_next_available().slot_name == "a"
    assert manager.get_next_available().slot_name == "b"
    assert manager.get_next_available().slot_name == "a"


def test_manager_skip_exhausted():
    manager = GeminiSlotManager()
    slot_a = GeminiProjectSlot(slot_name="a", api_key="ka", rpd_quota=1)
    slot_b = GeminiProjectSlot(slot_name="b", api_key="kb", rpd_quota=100)
    manager.add_slot(slot_a)
    manager.add_slot(slot_b)
    first = manager.get_next_available()
    assert first.slot_name == "a"
    first.record_request()
    assert manager.get_next_available().slot_name == "b"


def test_manager_all_exhausted():
    manager = GeminiSlotManager()
    slot = GeminiProjectSlot(slot_name="only", api_key="k", rpd_quota=1)
    manager.add_slot(slot)
    slot.record_request()
    assert manager.all_exhausted()
    assert manager.get_next_available() is None
