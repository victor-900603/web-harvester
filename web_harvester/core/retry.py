from __future__ import annotations

import email.utils
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

import httpx

logger = logging.getLogger(__name__)

BACKOFF_JITTERS = ("none", "full", "equal")

RETRYABLE_STATUS_CODES = frozenset({408, 429})

DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_DELAY = 30.0
DEFAULT_MULTIPLIER = 2.0
DEFAULT_JITTER = "full"


def is_retryable(exc: BaseException) -> bool:
    """Return whether an exception raised during a fetch should be retried.

    HTTP status errors are retryable only for transient conditions (408, 429
    and 5xx); other 4xx responses fail fast. Transport errors (timeouts,
    connection failures) and unknown network errors (e.g. curl_cffi errors)
    are treated as retryable.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        return status_code in RETRYABLE_STATUS_CODES or status_code >= 500
    return True


def parse_retry_after(value: Any) -> Optional[float]:
    """Parse a ``Retry-After`` header value into seconds.

    Supports both the delta-seconds form and the HTTP-date form. Returns None
    when the value is missing or cannot be parsed. Non-positive values are
    clamped to 0.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return max(0.0, float(value))

    text = str(value).strip()
    if not text:
        return None

    try:
        return max(0.0, float(text))
    except ValueError:
        pass

    try:
        parsed = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None

    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0.0, (parsed - datetime.now(timezone.utc)).total_seconds())


def retry_after_from_exception(exc: Optional[BaseException]) -> Optional[float]:
    """Extract the ``Retry-After`` delay (seconds) from an exception, if any."""
    if isinstance(exc, httpx.HTTPStatusError):
        return parse_retry_after(exc.response.headers.get("Retry-After"))
    return None


@dataclass
class BackoffPolicy:
    """Exponential backoff policy with optional jitter and Retry-After support."""

    base_delay: float = DEFAULT_BASE_DELAY
    max_delay: float = DEFAULT_MAX_DELAY
    multiplier: float = DEFAULT_MULTIPLIER
    jitter: str = DEFAULT_JITTER
    respect_retry_after: bool = True

    @classmethod
    def from_settings(cls, cfg: Optional[Mapping[str, Any]]) -> "BackoffPolicy":
        """Build a policy from the ``engine.retry`` mapping (None values skipped)."""
        cfg = cfg or {}
        kwargs: Dict[str, Any] = {}
        for key in ("base_delay", "max_delay", "multiplier", "jitter", "respect_retry_after"):
            value = cfg.get(key)
            if value is not None:
                kwargs[key] = value
        return cls(**kwargs)

    def delay(self, attempt: int, exc: Optional[BaseException] = None) -> float:
        """Compute the sleep delay (seconds) before the given retry attempt.

        Args:
            attempt (int): 1-based number of the attempt that just failed.
            exc (Optional[BaseException]): The failure, used to read Retry-After.
        """
        raw = min(self.base_delay * (self.multiplier ** (attempt - 1)), self.max_delay)

        if self.jitter == "full":
            raw = random.uniform(0, raw)
        elif self.jitter == "equal":
            raw = raw / 2 + random.uniform(0, raw / 2)

        if self.respect_retry_after and exc is not None:
            retry_after = retry_after_from_exception(exc)
            if retry_after is not None:
                raw = min(max(raw, retry_after), self.max_delay)

        return raw
