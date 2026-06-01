"""Authlib Google OAuth client (authorization code flow)."""

from __future__ import annotations

from authlib.integrations.starlette_client import OAuth

from backend.auth import (
    GOOGLE_METADATA_URL,
    google_client_id,
    google_client_secret,
    google_redirect_uri,
)

oauth = OAuth()

oauth.register(
    name="google",
    client_id=google_client_id(),
    client_secret=google_client_secret(),
    server_metadata_url=GOOGLE_METADATA_URL,
    client_kwargs={
        "scope": "openid email profile",
    },
)


def redirect_uri() -> str:
    return google_redirect_uri()
