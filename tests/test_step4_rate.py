"""Step 4 rate limiter tests."""

from __future__ import annotations

from discoursekit.llm.rate_limiter import RateLimiterState


def test_rate_limiter_rpm():
    limiter = RateLimiterState(rpm_limit=2, tpm_limit=100000, rpd_limit=1000)
    assert limiter.can_request()
    limiter.record_request()
    limiter.record_request()
    assert not limiter.can_request()


def test_rate_limiter_rpd():
    limiter = RateLimiterState(rpm_limit=100, tpm_limit=100000, rpd_limit=2)
    limiter.record_request()
    limiter.record_request()
    assert not limiter.can_request()


def test_rate_limiter_tpm():
    limiter = RateLimiterState(rpm_limit=100, tpm_limit=1000, rpd_limit=1000)
    assert limiter.can_request(estimated_tokens=500)
    limiter.record_request(tokens_used=800)
    assert not limiter.can_request(estimated_tokens=500)
