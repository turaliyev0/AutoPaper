"""Base retry helpers for LLM clients."""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from typing import TypeVar

from tenacity import retry, retry_if_exception_type, stop_after_attempt
from tenacity.wait import wait_base

logger = logging.getLogger(__name__)

T = TypeVar("T")

RETRYABLE = (
    TimeoutError,
    ConnectionError,
    OSError,
)

_RETRY_AFTER_MS = re.compile(r"try again in (\d+(?:\.\d+)?)\s*ms", re.IGNORECASE)
_RETRY_AFTER_S = re.compile(r"try again in (\d+(?:\.\d+)?)\s*s", re.IGNORECASE)


def retry_wait_seconds(exc: BaseException | None) -> float | None:
    """Parse OpenAI/Gemini 'try again in …' hints from an exception message."""
    if exc is None:
        return None
    msg = str(exc)
    m = _RETRY_AFTER_MS.search(msg)
    if m:
        return float(m.group(1)) / 1000.0 + 1.0
    m = _RETRY_AFTER_S.search(msg)
    if m:
        return float(m.group(1)) + 0.5
    if "rate limit" in msg.lower() or "429" in msg:
        return 3.0
    return None


class _LlmRetryWait(wait_base):
    """Prefer API-suggested delay; otherwise exponential backoff (2s → 60s)."""

    def __call__(self, retry_state) -> float:
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        hinted = retry_wait_seconds(exc)
        if hinted is not None:
            return hinted
        attempt = retry_state.attempt_number
        return min(2.0 ** attempt, 60.0)


def llm_retry(max_attempts: int = 6) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    return retry(
        reraise=True,
        stop=stop_after_attempt(max_attempts),
        wait=_LlmRetryWait(),
        retry=retry_if_exception_type(RETRYABLE),
        before_sleep=lambda rs: logger.warning(
            "LLM call failed (attempt %s): %s",
            rs.attempt_number,
            rs.outcome.exception() if rs.outcome else "unknown",
        ),
    )
