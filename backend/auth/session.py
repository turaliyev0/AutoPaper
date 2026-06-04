"""API session tokens issued after Google sign-in."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from .config import auth_disabled, session_secret, token_expire_minutes
from .models import SessionTokenResponse

ALGORITHM = "HS256"
_ISSUER = "autopaper-google"


def create_session_token(
    *,
    email: str,
    name: str = "",
    picture: str = "",
    google_sub: str = "",
) -> SessionTokenResponse:
    expire = datetime.now(timezone.utc) + timedelta(minutes=token_expire_minutes())
    payload = {
        "sub": email or google_sub,
        "email": email,
        "name": name,
        "picture": picture,
        "google_sub": google_sub,
        "iss": _ISSUER,
        "exp": expire,
    }
    token = jwt.encode(payload, session_secret(), algorithm=ALGORITHM)
    return SessionTokenResponse(
        access_token=token,
        expires_in=token_expire_minutes() * 60,
    )


def decode_session_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(token, session_secret(), algorithms=[ALGORITHM])
    if payload.get("iss") != _ISSUER and not auth_disabled():
        raise JWTError("Invalid token issuer")
    return payload
