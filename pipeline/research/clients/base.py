"""Base retry helpers for LLM clients."""

from __future__ import annotations

import logging
import random
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

_RETRYABLE_HTTP_CODES = frozenset({429, 500, 502, 503, 504})

_RETRY_AFTER_MS = re.compile(r"try again in (\d+(?:\.\d+)?)\s*ms", re.IGNORECASE)
_RETRY_AFTER_S = re.compile(r"try again in (\d+(?:\.\d+)?)\s*s", re.IGNORECASE)


def is_retryable_http_code(code: int | None) -> bool:
    return code in _RETRYABLE_HTTP_CODES if code is not None else False


def gemini_error_to_retryable(exc: BaseException) -> TimeoutError | None:
    """Map transient Gemini API errors to TimeoutError for tenacity."""
    code = getattr(exc, "code", None)
    if is_retryable_http_code(code):
        return TimeoutError(str(exc))
    msg = str(exc).lower()
    if any(
        token in msg
        for token in (
            "503",
            "429",
            "unavailable",
            "high demand",
            "overloaded",
            "resource exhausted",
        )
    ):
        return TimeoutError(str(exc))
    return None


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
    lower = msg.lower()
    if "503" in lower or "unavailable" in lower or "high demand" in lower:
        return 10.0
    if "rate limit" in lower or "429" in lower:
        return 5.0
    return None


class _LlmRetryWait(wait_base):
    """Prefer API-suggested delay; otherwise exponential backoff with jitter (2s → 90s)."""

    def __call__(self, retry_state) -> float:
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        hinted = retry_wait_seconds(exc)
        if hinted is not None:
            base = hinted
        else:
            attempt = retry_state.attempt_number
            base = min(2.0 ** attempt, 90.0)
        return base + random.uniform(0.0, 2.0)


def llm_retry(max_attempts: int = 8) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    return retry(
        reraise=True,
        stop=stop_after_attempt(max_attempts),
        wait=_LlmRetryWait(),
        retry=retry_if_exception_type(RETRYABLE),
        before_sleep=lambda rs: logger.warning(
            "LLM call failed (attempt %s/%s): %s",
            rs.attempt_number,
            max_attempts,
            rs.outcome.exception() if rs.outcome else "unknown",
        ),
    )
