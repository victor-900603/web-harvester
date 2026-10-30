"""Per-domain rate limiting for outbound requests.

The engine throttles by hostname rather than globally so that concurrent async
workers stay parallel across different domains while every individual domain
still receives requests at a polite, configurable interval.
"""

from __future__ import annotations

import asyncio
import time
from typing import Callable, Dict, Optional
from urllib.parse import urlsplit

# Long waits are sliced so a cancelled crawl does not have to sit out a full
# interval before the worker notices it should stop.
POLL_INTERVAL = 0.1


def domain_of(url: str) -> str:
    """Return the throttling key for ``url``.

    Hostname is used when present so scheme, port and path do not split the
    bucket; URLs without a host fall back to the whole URL.
    """
    hostname = urlsplit(url).hostname
    return hostname.lower() if hostname else url


class DomainRateLimiter:
    """Enforce a minimum interval between requests to the same domain.

    ``min_interval`` of zero or less disables throttling entirely. Robots.txt
    fetches bypass the limiter: they occur at most once per origin per run.
    """

    def __init__(self, min_interval: float) -> None:
        self._min_interval = max(0.0, float(min_interval))
        self._last_request: Dict[str, float] = {}

    @property
    def min_interval(self) -> float:
        """The configured minimum interval in seconds."""
        return self._min_interval

    def wait(self, url: str, should_stop: Optional[Callable[[], bool]] = None) -> None:
        """Block until ``url``'s domain may receive its next request.

        ``should_stop`` is polled while waiting so a cancelled crawl returns
        promptly instead of sleeping out the whole interval.
        """
        if self._min_interval <= 0:
            return

        remaining = self._remaining_delay(domain_of(url))
        while remaining > 0:
            if should_stop is not None and should_stop():
                return
            step = min(remaining, POLL_INTERVAL)
            time.sleep(step)
            remaining -= step

    async def wait_async(self, url: str, should_stop: Optional[Callable[[], bool]] = None) -> None:
        """Await until ``url``'s domain may receive its next request."""
        if self._min_interval <= 0:
            return

        remaining = self._remaining_delay(domain_of(url))
        while remaining > 0:
            if should_stop is not None and should_stop():
                return
            step = min(remaining, POLL_INTERVAL)
            await asyncio.sleep(step)
            remaining -= step

    def _remaining_delay(self, domain: str) -> float:
        """Reserve the next slot for ``domain`` and return the delay before it.

        The reservation updates the last-request timestamp immediately so that
        concurrent async callers queue up behind each other instead of all
        observing the same stale timestamp.
        """
        now = time.monotonic()
        last = self._last_request.get(domain)
        delay = 0.0 if last is None else self._min_interval - (now - last)
        self._last_request[domain] = now + max(0.0, delay)
        return max(0.0, delay)
