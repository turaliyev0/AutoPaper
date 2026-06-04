"""Auth-related environment configuration."""

from __future__ import annotations

import os

GOOGLE_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"


def auth_disabled() -> bool:
    return os.environ.get("AUTOPAPER_AUTH_DISABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def session_secret() -> str:
    secret = (
        os.environ.get("AUTOPAPER_SESSION_SECRET", "").strip()
        or os.environ.get("AUTOPAPER_JWT_SECRET", "").strip()
    )
    if not secret:
        if auth_disabled():
            return "dev-only-insecure-secret"
        raise RuntimeError(
            "AUTOPAPER_SESSION_SECRET is required when auth is enabled. "
            "Set AUTOPAPER_AUTH_DISABLED=1 for local dev without login."
        )
    return secret


def token_expire_minutes() -> int:
    raw = os.environ.get("AUTOPAPER_SESSION_EXPIRE_MINUTES", "1440").strip()
    try:
        return max(5, int(raw))
    except ValueError:
        return 1440


def google_client_id() -> str:
    return os.environ.get("GOOGLE_CLIENT_ID", "").strip()


def google_client_secret() -> str:
    return os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()


def google_redirect_uri() -> str:
    return os.environ.get(
        "AUTOPAPER_GOOGLE_REDIRECT_URI",
        "http://localhost:8000/api/auth/google/callback",
    ).strip()


def frontend_url() -> str:
    return os.environ.get("AUTOPAPER_FRONTEND_URL", "http://localhost:5173").rstrip("/")


def google_oauth_configured() -> bool:
    return bool(google_client_id() and google_client_secret())
