"""Google OAuth sign-in and API session tokens."""

from .config import (
    auth_disabled,
    frontend_url,
    google_client_id,
    google_oauth_configured,
    session_secret,
)
from .deps import get_current_user, resolve_bearer_token
from .google_verify import user_from_google_claims, verify_google_id_token
from .models import SessionTokenResponse, UserPublic
from .session import create_session_token, decode_session_token

__all__ = [
    "SessionTokenResponse",
    "UserPublic",
    "auth_disabled",
    "create_session_token",
    "decode_session_token",
    "frontend_url",
    "get_current_user",
    "google_client_id",
    "google_oauth_configured",
    "resolve_bearer_token",
    "session_secret",
    "user_from_google_claims",
    "verify_google_id_token",
]
