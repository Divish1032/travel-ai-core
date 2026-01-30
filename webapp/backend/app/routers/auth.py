"""
Authentication router with Firebase integration.

Provides endpoints for user registration, login, and session management.
"""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.traveler_profile import TravelerProfile
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    AuthResponse,
    LogoutResponse
)
from app.schemas.user import UserWithProfileResponse
from app.utils.firebase import firebase_admin_instance


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    db: Session = Depends(get_db)
):
    """
    Register a new user after Firebase authentication.

    Flow:
    1. Client authenticates with Firebase (Google/Phone)
    2. Client sends Firebase token to this endpoint
    3. Backend verifies token and creates user in database

    Args:
        request: Firebase token and optional display name
        db: Database session

    Returns:
        User information and success message

    Raises:
        HTTPException: If token invalid or user already exists
    """
    # Verify Firebase token
    try:
        decoded_token = await firebase_admin_instance.verify_token(request.firebase_token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Firebase token: {str(e)}"
        )

    firebase_uid = decoded_token.get("uid")
    email = decoded_token.get("email")

    if not firebase_uid or not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Firebase token missing required claims (uid, email)"
        )

    # Check if user already exists
    existing_user = db.query(User).filter(User.firebase_uid == firebase_uid).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already registered. Please use /auth/login endpoint."
        )

    # Create new user
    new_user = User(
        id=uuid.uuid4(),
        firebase_uid=firebase_uid,
        email=email,
        display_name=request.display_name or decoded_token.get("name"),
        photo_url=decoded_token.get("picture"),
        created_at=datetime.now(timezone.utc),
        last_login=datetime.now(timezone.utc),
        is_active=True
    )

    db.add(new_user)
    db.flush()  # Flush to get user ID

    # Create default traveler profile
    traveler_profile = TravelerProfile(
        id=uuid.uuid4(),
        user_id=new_user.id,
        traveler_type="solo",
        budget_tier="mid-range",
        travel_style=[],
        interests=[]
    )

    db.add(traveler_profile)
    db.commit()
    db.refresh(new_user)

    return AuthResponse(
        user_id=new_user.id,
        email=new_user.email,
        display_name=new_user.display_name,
        firebase_uid=new_user.firebase_uid,
        is_active=new_user.is_active,
        created_at=new_user.created_at,
        message="User registered successfully"
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    Login existing user with Firebase token.

    Flow:
    1. Client authenticates with Firebase
    2. Client sends Firebase token to this endpoint
    3. Backend verifies token and returns user info

    Args:
        request: Firebase token
        db: Database session

    Returns:
        User information and success message

    Raises:
        HTTPException: If token invalid or user not found
    """
    # Verify Firebase token
    try:
        decoded_token = await firebase_admin_instance.verify_token(request.firebase_token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Firebase token: {str(e)}"
        )

    firebase_uid = decoded_token.get("uid")

    if not firebase_uid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Firebase token missing UID"
        )

    # Find user
    user = db.query(User).filter(User.firebase_uid == firebase_uid).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found. Please register first at /auth/register."
        )

    # Update last login
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    return AuthResponse(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        firebase_uid=user.firebase_uid,
        is_active=user.is_active,
        created_at=user.created_at,
        message="Login successful"
    )


@router.get("/me", response_model=UserWithProfileResponse)
async def get_current_user_info(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current authenticated user information.

    Requires:
        Authorization: Bearer <firebase_token>

    Returns:
        User information with traveler profile
    """
    # Load traveler profile
    db.refresh(user)

    return UserWithProfileResponse(
        id=user.id,
        firebase_uid=user.firebase_uid,
        email=user.email,
        display_name=user.display_name,
        photo_url=user.photo_url,
        preferences=user.preferences,
        created_at=user.created_at,
        last_login=user.last_login,
        is_active=user.is_active,
        traveler_profile=user.traveler_profile
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(user: User = Depends(get_current_user)):
    """
    Logout user (client-side token invalidation).

    Note: Firebase tokens are stateless, so logout is primarily
    a client-side operation (delete token from storage).

    This endpoint exists for consistency and potential future
    server-side session tracking.

    Requires:
        Authorization: Bearer <firebase_token>

    Returns:
        Logout confirmation message
    """
    return LogoutResponse(message="Successfully logged out. Please delete token on client.")


@router.post("/refresh", response_model=AuthResponse)
async def refresh_token(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Refresh user session.

    Updates last_login timestamp and returns user info.
    Client should handle Firebase token refresh separately.

    Requires:
        Authorization: Bearer <firebase_token>

    Returns:
        Updated user information
    """
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    return AuthResponse(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        firebase_uid=user.firebase_uid,
        is_active=user.is_active,
        created_at=user.created_at,
        message="Session refreshed successfully"
    )
