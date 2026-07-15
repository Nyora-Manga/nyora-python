"""Automatic retries with exponential backoff for transient engine failures.

Both clients (:class:`nyora.Nyora`, :class:`nyora.AsyncNyora`) retry connect/read
timeouts, connection errors, and retryable status codes (``408``, ``429``, and
``5xx``) using exponential backoff with jitter. A ``Retry-After`` header (sent on
``429``/``503``) is honoured when present.

Configure via the ``retries`` argument on either client — pass an integer
(max attempts) or a :class:`RetryConfig`. ``retries=0`` disables retrying.

Example:
    >>> from nyora import Nyora, RetryConfig
    >>> policy = RetryConfig(max_retries=5, backoff_base=0.25, backoff_max=10)
    >>> client = Nyora(retries=policy)
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime

import httpx

logger = logging.getLogger("nyora")

#: HTTP status codes that are safe to retry (transient / rate-limited).
RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})

#: httpx exceptions treated as transient (connect/read/network/timeout errors).
TRANSIENT_EXCEPTIONS = (httpx.TransportError,)


@dataclass(frozen=True)
class RetryConfig:
    """Exponential-backoff retry policy.

    Attributes:
        max_retries: Maximum number of retries after the first attempt
            (``0`` disables retrying entirely).
        backoff_base: Base delay in seconds; the un-jittered delay for retry
            ``n`` is ``backoff_base * 2**n``.
        backoff_max: Upper bound (seconds) on any single backoff delay.
        jitter: Fractional jitter applied to each delay (``0.3`` = ±30%),
            spreading retries to avoid thundering herds.
        retry_statuses: HTTP status codes that trigger a retry.
    """

    max_retries: int = 3
    backoff_base: float = 0.5
    backoff_max: float = 20.0
    jitter: float = 0.3
    retry_statuses: frozenset[int] = field(default_factory=lambda: RETRYABLE_STATUS)

    @classmethod
    def coerce(cls, value: RetryConfig | int | None) -> RetryConfig:
        """Normalise ``value`` (``None`` / ``int`` / :class:`RetryConfig`) to a policy."""
        if isinstance(value, RetryConfig):
            return value
        if value is None:
            return cls()
        if isinstance(value, bool):  # guard against `retries=True`
            raise TypeError("retries must be an int or RetryConfig, not bool")
        if isinstance(value, int):
            return cls(max_retries=max(0, value))
        raise TypeError(f"retries must be an int or RetryConfig, got {type(value).__name__}")

    def should_retry_status(self, status_code: int) -> bool:
        """Return whether ``status_code`` is a retryable response."""
        return status_code in self.retry_statuses

    def backoff(self, attempt: int, *, retry_after: float | None = None) -> float:
        """Return the delay (seconds) before retry number ``attempt`` (0-based).

        Honours an explicit ``retry_after`` (from a ``Retry-After`` header) when
        given; otherwise uses jittered exponential backoff.
        """
        if retry_after is not None and retry_after >= 0:
            return min(retry_after, self.backoff_max)
        base = min(self.backoff_base * (2**attempt), self.backoff_max)
        spread = base * self.jitter
        return max(0.0, base + random.uniform(-spread, spread))


def retry_after_seconds(response: httpx.Response) -> float | None:
    """Parse a ``Retry-After`` header (delta-seconds or HTTP-date) into seconds."""
    value = response.headers.get("retry-after")
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    import datetime as _dt

    now = _dt.datetime.now(_dt.timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=_dt.timezone.utc)
    return max(0.0, (when - now).total_seconds())
