"""Auth request/response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SessionTokenResponse(BaseModel):
    access_token: str = Field(description="Bearer token for AutoPaper API")
    token_type: str = Field(default="bearer")
    expires_in: int = Field(description="Seconds until expiry")


class UserPublic(BaseModel):
    email: str = ""
    name: str = ""
    picture: str = ""
    google_sub: str = ""
    auth_disabled: bool = False

    @property
    def username(self) -> str:
        return self.email or self.google_sub or "user"
