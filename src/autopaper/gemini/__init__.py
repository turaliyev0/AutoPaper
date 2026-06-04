"""Deprecated — use ``backend.logging.gemini``."""

from backend.logging.gemini import gemini_trace_enabled, log_request, log_response

__all__ = ["gemini_trace_enabled", "log_request", "log_response"]
