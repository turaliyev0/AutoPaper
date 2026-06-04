"""FastAPI auth dependencies."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from .config import auth_disabled
from .models import UserPublic
from .session import decode_session_token

bearer_scheme = HTTPBearer(auto_error=False)


async def resolve_bearer_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    access_token: str | None = Query(
        None,
        description="Session token for SSE (EventSource cannot send Authorization)",
    ),
) -> str | None:
    if credentials and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    return access_token


async def get_current_user(
    token: str | None = Depends(resolve_bearer_token),
) -> UserPublic:
    if auth_disabled():
        return UserPublic(
            email="dev@localhost",
            name="Dev",
            auth_disabled=True,
        )
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in with Google first",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_session_token(token)
        return UserPublic(
            email=str(payload.get("email") or payload.get("sub") or ""),
            name=str(payload.get("name") or ""),
            picture=str(payload.get("picture") or ""),
            google_sub=str(payload.get("google_sub") or ""),
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid — sign in with Google again",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
