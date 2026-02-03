"""
Authentication schemas for request/response validation.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID


class FirebaseTokenRequest(BaseModel):
    """Request schema for Firebase token authentication."""

    firebase_token: str = Field(
        ...,
        description="Firebase ID token from client-side authentication"
    )


class RegisterRequest(BaseModel):
    """Request schema for user registration."""

    firebase_token: str = Field(..., description="Firebase ID token")
    display_name: Optional[str] = Field(None, max_length=255)


class LoginRequest(BaseModel):
    """Request schema for user login."""

    firebase_token: str = Field(..., description="Firebase ID token")


class AuthResponse(BaseModel):
    """Response schema for successful authentication."""

    user_id: UUID
    email: str
    display_name: Optional[str]
    firebase_uid: str
    is_active: bool
    created_at: datetime
    message: str

    class Config:
        from_attributes = True


class LogoutResponse(BaseModel):
    """Response schema for logout."""

    message: str = "Successfully logged out"
