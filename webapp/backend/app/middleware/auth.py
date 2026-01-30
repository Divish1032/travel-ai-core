"""
Authentication middleware for Firebase token validation.

This module provides middleware to verify Firebase tokens and
retrieve user information from the database.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.utils.firebase import firebase_admin_instance
from app.models.user import User


class FirebaseAuthMiddleware:
    """
    Middleware for Firebase authentication.

    Provides static methods for token verification and user retrieval.
    """

    @staticmethod
    async def verify_token(authorization: str) -> dict:
        """
        Verify Bearer token from Authorization header.

        Args:
            authorization: Authorization header value (e.g., "Bearer <token>")

        Returns:
            Decoded token claims

        Raises:
            HTTPException: If token is invalid or missing
        """
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization header format. Expected 'Bearer <token>'",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = authorization.replace("Bearer ", "")

        try:
            decoded_token = await firebase_admin_instance.verify_token(token)
            return decoded_token
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(e),
                headers={"WWW-Authenticate": "Bearer"},
            )

    @staticmethod
    async def get_current_user_from_token(
        decoded_token: dict,
        db: Session
    ) -> User:
        """
        Get User from database using Firebase UID from token.

        Args:
            decoded_token: Decoded Firebase token claims
            db: Database session

        Returns:
            User object

        Raises:
            HTTPException: If user not found in database
        """
        firebase_uid = decoded_token.get("uid")

        if not firebase_uid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing UID claim",
            )

        # Query user by Firebase UID
        user = db.query(User).filter(User.firebase_uid == firebase_uid).first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found. Please register first.",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is deactivated",
            )

        return user
