"""OAuth2 password flow + JWT access tokens for the AutoPaper API."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel, Field

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)

ALGORITHM = "HS256"


class TokenResponse(BaseModel):
    access_token: str = Field(description="Bearer JWT")
    token_type: str = Field(default="bearer")
    expires_in: int = Field(description="Seconds until expiry")


class UserPublic(BaseModel):
    username: str
    auth_disabled: bool = False


def auth_disabled() -> bool:
    return os.environ.get("AUTOPAPER_AUTH_DISABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _jwt_secret() -> str:
    secret = os.environ.get("AUTOPAPER_JWT_SECRET", "").strip()
    if not secret:
        if auth_disabled():
            return "dev-only-insecure-secret"
        raise RuntimeError(
            "AUTOPAPER_JWT_SECRET is required when auth is enabled. "
            "Set AUTOPAPER_AUTH_DISABLED=1 for local dev without tokens."
        )
    return secret


def token_expire_minutes() -> int:
    raw = os.environ.get("AUTOPAPER_JWT_EXPIRE_MINUTES", "1440").strip()
    try:
        return max(5, int(raw))
    except ValueError:
        return 1440


def _load_users() -> dict[str, str]:
    """username -> bcrypt hash. Env: AUTOPAPER_AUTH_USERS=user:pass,user2:pass2"""
    users: dict[str, str] = {}
    bulk = os.environ.get("AUTOPAPER_AUTH_USERS", "").strip()
    if bulk:
        for part in bulk.split(","):
            part = part.strip()
            if ":" not in part:
                continue
            name, secret = part.split(":", 1)
            name = name.strip()
            secret = secret.strip()
            if name and secret:
                users[name] = _hash_password(secret)
    single_user = os.environ.get("AUTOPAPER_AUTH_USER", "").strip()
    single_pass = os.environ.get("AUTOPAPER_AUTH_PASSWORD", "").strip()
    if single_user and single_pass:
        users[single_user] = _hash_password(single_pass)
    if not users and not auth_disabled():
        users["admin"] = _hash_password(
            os.environ.get("AUTOPAPER_AUTH_PASSWORD", "changeme")
        )
    return users


_USERS_CACHE: dict[str, str] | None = None


def get_users() -> dict[str, str]:
    global _USERS_CACHE
    if _USERS_CACHE is None:
        _USERS_CACHE = _load_users()
    return _USERS_CACHE


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    users = get_users()
    hashed = users.get(username)
    if not hashed or not verify_password(password, hashed):
        return None
    return {"username": username}


def create_access_token(*, username: str) -> TokenResponse:
    expire = datetime.now(timezone.utc) + timedelta(minutes=token_expire_minutes())
    payload = {"sub": username, "exp": expire}
    token = jwt.encode(payload, _jwt_secret(), algorithm=ALGORITHM)
    return TokenResponse(
        access_token=token,
        expires_in=token_expire_minutes() * 60,
    )


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, _jwt_secret(), algorithms=[ALGORITHM])


async def resolve_bearer_token(
    token: str | None = Depends(oauth2_scheme),
    access_token: str | None = Query(
        None,
        description="Optional JWT for EventSource/SSE (cannot set Authorization header)",
    ),
) -> str | None:
    return token or access_token


async def get_current_user(
    token: str | None = Depends(resolve_bearer_token),
) -> UserPublic:
    if auth_disabled():
        return UserPublic(username="dev", auth_disabled=True)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(token)
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token payload")
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return UserPublic(username=str(username))


async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> TokenResponse:
    if auth_disabled():
        return create_access_token(username=form_data.username or "dev")
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return create_access_token(username=user["username"])
