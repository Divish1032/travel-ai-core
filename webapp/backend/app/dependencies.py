"""
FastAPI dependency injection functions.

This module provides reusable dependencies for routes, including
database sessions and user authentication.
"""

from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.middleware.auth import FirebaseAuthMiddleware


# HTTP Bearer security scheme
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Dependency to get current authenticated user.

    Requires valid Firebase ID token in Authorization header.
    Returns User object from database.

    Args:
        credentials: HTTP Bearer credentials from request header
        db: Database session

    Returns:
        Authenticated User object

    Raises:
        HTTPException: If authentication fails

    Usage:
        @router.get("/me")
        async def get_me(user: User = Depends(get_current_user)):
            return {"email": user.email}
    """
    # Verify Firebase token
    decoded_token = await FirebaseAuthMiddleware.verify_token(
        f"Bearer {credentials.credentials}"
    )

    # Get user from database
    user = await FirebaseAuthMiddleware.get_current_user_from_token(
        decoded_token, db
    )

    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    ),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Optional authentication dependency.

    Returns User if authenticated, None if not.
    Does not raise exceptions for missing/invalid tokens.

    Use for endpoints that are enhanced with auth but don't require it
    (e.g., public content that shows personalized results when logged in).

    Args:
        credentials: Optional HTTP Bearer credentials
        db: Database session

    Returns:
        User object if authenticated, None otherwise

    Usage:
        @router.get("/places")
        async def get_places(user: Optional[User] = Depends(get_current_user_optional)):
            if user:
                # Return personalized results
                pass
            else:
                # Return generic results
                pass
    """
    if not credentials:
        return None

    try:
        decoded_token = await FirebaseAuthMiddleware.verify_token(
            f"Bearer {credentials.credentials}"
        )
        user = await FirebaseAuthMiddleware.get_current_user_from_token(
            decoded_token, db
        )
        return user
    except HTTPException:
        # If authentication fails, return None instead of raising
        return None
