from __future__ import annotations

import asyncio

import pytest

from web_harvester.core import rate_limit
from web_harvester.core.rate_limit import DomainRateLimiter, domain_of


class FakeClock:
    """Deterministic clock whose ``sleep`` advances time instead of blocking."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    async def sleep_async(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(rate_limit.time, "monotonic", fake.monotonic)
    monkeypatch.setattr(rate_limit.time, "sleep", fake.sleep)
    monkeypatch.setattr(rate_limit.asyncio, "sleep", fake.sleep_async)
    return fake


class TestDomainOf:
    def test_hostname_is_used(self):
        assert domain_of("https://News.Example.com/path?q=1") == "news.example.com"

    def test_port_does_not_split_bucket(self):
        assert domain_of("http://example.com:8080/a") == "example.com"

    def test_url_without_host_falls_back_to_url(self):
        assert domain_of("not-a-url") == "not-a-url"


class TestSyncWait:
    def test_first_request_does_not_wait(self, clock):
        limiter = DomainRateLimiter(1.0)
        limiter.wait("https://example.com/a")
        assert clock.sleeps == []

    def test_same_domain_waits_remaining_interval(self, clock):
        limiter = DomainRateLimiter(1.0)
        limiter.wait("https://example.com/a")
        clock.now += 0.25
        limiter.wait("https://example.com/b")
        assert sum(clock.sleeps) == pytest.approx(0.75)

    def test_no_wait_after_interval_elapsed(self, clock):
        limiter = DomainRateLimiter(1.0)
        limiter.wait("https://example.com/a")
        clock.now += 2.0
        limiter.wait("https://example.com/b")
        assert clock.sleeps == []

    def test_different_domains_are_independent(self, clock):
        limiter = DomainRateLimiter(1.0)
        limiter.wait("https://example.com/a")
        limiter.wait("https://other.example.com/b")
        assert clock.sleeps == []

    def test_zero_interval_disables_throttling(self, clock):
        limiter = DomainRateLimiter(0)
        limiter.wait("https://example.com/a")
        limiter.wait("https://example.com/b")
        assert clock.sleeps == []
        assert limiter.min_interval == 0

    def test_negative_interval_is_clamped(self, clock):
        limiter = DomainRateLimiter(-5)
        limiter.wait("https://example.com/a")
        limiter.wait("https://example.com/b")
        assert clock.sleeps == []
        assert limiter.min_interval == 0


class TestAsyncWait:
    def test_first_request_does_not_wait(self, clock):
        limiter = DomainRateLimiter(1.0)

        async def run():
            await limiter.wait_async("https://example.com/a")

        asyncio.run(run())
        assert clock.sleeps == []

    def test_same_domain_waits_remaining_interval(self, clock):
        limiter = DomainRateLimiter(1.0)

        async def run():
            await limiter.wait_async("https://example.com/a")
            clock.now += 0.4
            await limiter.wait_async("https://example.com/b")

        asyncio.run(run())
        assert sum(clock.sleeps) == pytest.approx(0.6)

    def test_concurrent_callers_are_spaced(self, clock):
        limiter = DomainRateLimiter(1.0)

        async def run():
            await asyncio.gather(
                limiter.wait_async("https://example.com/a"),
                limiter.wait_async("https://example.com/b"),
                limiter.wait_async("https://example.com/c"),
            )

        asyncio.run(run())
        # Three concurrent callers occupy slots at t, t+1 and t+2; the second and
        # third sleep concurrently, so the total added delay is two intervals.
        assert sum(clock.sleeps) == pytest.approx(2.0)
        assert clock.now == pytest.approx(1002.0)

    def test_zero_interval_disables_throttling(self, clock):
        limiter = DomainRateLimiter(0)

        async def run():
            await limiter.wait_async("https://example.com/a")
            await limiter.wait_async("https://example.com/b")

        asyncio.run(run())
        assert clock.sleeps == []
