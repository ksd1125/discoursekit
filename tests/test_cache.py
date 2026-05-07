"""LLM cache tests."""

from discoursekit.llm.cache import cache_key, get_cached, invalidate, set_cache


def test_set_get(tmp_path):
    key = cache_key("search_advice", topic="x")
    set_cache(tmp_path, key, {"_category": "search_advice", "value": 1})

    assert get_cached(tmp_path, key)["value"] == 1


def test_miss(tmp_path):
    assert get_cached(tmp_path, "missing") is None


def test_invalidate_all(tmp_path):
    key = cache_key("search_advice", topic="x")
    set_cache(tmp_path, key, {"_category": "search_advice"})

    invalidate(tmp_path)

    assert get_cached(tmp_path, key) is None


def test_invalidate_category(tmp_path):
    key_a = cache_key("search_advice", topic="x")
    key_b = cache_key("keyword_interpret", topic="x")
    set_cache(tmp_path, key_a, {"_category": "search_advice"})
    set_cache(tmp_path, key_b, {"_category": "keyword_interpret"})

    invalidate(tmp_path, "search_advice")

    assert get_cached(tmp_path, key_a) is None
    assert get_cached(tmp_path, key_b) is not None
