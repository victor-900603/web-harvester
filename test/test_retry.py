from __future__ import annotations

import email.utils
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from src.core.retry import (
    BackoffPolicy,
    is_retryable,
    parse_retry_after,
    retry_after_from_exception,
)


def _status_error(status_code: int, headers=None) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://e.com/a")
    return httpx.HTTPStatusError(
        f"{status_code}",
        request=request,
        response=httpx.Response(status_code, headers=headers or {}, request=request),
    )


class TestIsRetryable:
    @pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
    def test_retryable_status_codes(self, status):
        assert is_retryable(_status_error(status)) is True

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
    def test_non_retryable_client_errors(self, status):
        assert is_retryable(_status_error(status)) is False

    def test_transport_error_retryable(self):
        assert is_retryable(httpx.ConnectError("boom")) is True
        assert is_retryable(httpx.ReadTimeout("slow")) is True

    def test_unknown_exception_defaults_to_retryable(self):
        assert is_retryable(RuntimeError("curl_cffi failure")) is True


class TestParseRetryAfter:
    def test_none_returns_none(self):
        assert parse_retry_after(None) is None

    def test_integer_seconds(self):
        assert parse_retry_after("5") == 5.0

    def test_float_string(self):
        assert parse_retry_after("2.5") == 2.5

    def test_numeric_value(self):
        assert parse_retry_after(7) == 7.0

    def test_negative_clamped_to_zero(self):
        assert parse_retry_after("-3") == 0.0

    def test_empty_string_none(self):
        assert parse_retry_after("  ") is None

    def test_garbage_none(self):
        assert parse_retry_after("not-a-date") is None

    def test_http_date(self):
        future = datetime.now(timezone.utc) + timedelta(seconds=60)
        value = email.utils.format_datetime(future)
        delay = parse_retry_after(value)
        assert delay is not None
        assert 55 <= delay <= 61

    def test_past_http_date_clamped(self):
        past = datetime.now(timezone.utc) - timedelta(seconds=60)
        value = email.utils.format_datetime(past)
        assert parse_retry_after(value) == 0.0


class TestRetryAfterFromException:
    def test_reads_header_from_http_status_error(self):
        exc = _status_error(429, {"Retry-After": "12"})
        assert retry_after_from_exception(exc) == 12.0

    def test_missing_header(self):
        assert retry_after_from_exception(_status_error(429)) is None

    def test_non_http_error(self):
        assert retry_after_from_exception(RuntimeError("x")) is None
        assert retry_after_from_exception(None) is None


class TestBackoffPolicy:
    def test_from_settings_skips_none(self):
        policy = BackoffPolicy.from_settings({"base_delay": 2, "max_delay": None})
        assert policy.base_delay == 2
        assert policy.max_delay == 30.0

    def test_from_settings_none(self):
        policy = BackoffPolicy.from_settings(None)
        assert policy == BackoffPolicy()

    def test_exponential_growth_without_jitter(self):
        policy = BackoffPolicy(base_delay=1, max_delay=100, multiplier=2, jitter="none")
        assert policy.delay(1) == 1.0
        assert policy.delay(2) == 2.0
        assert policy.delay(3) == 4.0

    def test_max_delay_cap(self):
        policy = BackoffPolicy(base_delay=1, max_delay=5, multiplier=2, jitter="none")
        assert policy.delay(10) == 5.0

    def test_full_jitter_range(self, monkeypatch):
        monkeypatch.setattr("src.core.retry.random.uniform", lambda a, b: b)
        policy = BackoffPolicy(base_delay=2, max_delay=100, multiplier=2, jitter="full")
        assert policy.delay(1) == 2.0

    def test_none_jitter_no_random(self, monkeypatch):
        def boom(a, b):
            raise AssertionError("random should not be called")

        monkeypatch.setattr("src.core.retry.random.uniform", boom)
        policy = BackoffPolicy(base_delay=3, jitter="none")
        assert policy.delay(1) == 3.0

    def test_respect_retry_after_uses_header(self, monkeypatch):
        monkeypatch.setattr("src.core.retry.random.uniform", lambda a, b: 0.0)
        policy = BackoffPolicy(base_delay=1, max_delay=100, multiplier=2, jitter="none")
        exc = _status_error(429, {"Retry-After": "10"})
        assert policy.delay(1, exc) == 10.0

    def test_retry_after_capped_by_max_delay(self, monkeypatch):
        monkeypatch.setattr("src.core.retry.random.uniform", lambda a, b: 0.0)
        policy = BackoffPolicy(base_delay=1, max_delay=5, multiplier=2, jitter="none")
        exc = _status_error(429, {"Retry-After": "600"})
        assert policy.delay(1, exc) == 5.0

    def test_retry_after_ignored_when_disabled(self, monkeypatch):
        monkeypatch.setattr("src.core.retry.random.uniform", lambda a, b: 0.0)
        policy = BackoffPolicy(base_delay=1, max_delay=100, jitter="none", respect_retry_after=False)
        exc = _status_error(429, {"Retry-After": "10"})
        assert policy.delay(1, exc) == 1.0

    def test_retry_after_does_not_reduce_computed_delay(self, monkeypatch):
        monkeypatch.setattr("src.core.retry.random.uniform", lambda a, b: 0.0)
        policy = BackoffPolicy(base_delay=20, max_delay=100, multiplier=2, jitter="none")
        exc = _status_error(429, {"Retry-After": "3"})
        assert policy.delay(1, exc) == 20.0
