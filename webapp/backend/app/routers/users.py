"""
User management router.

Provides endpoints for managing user profiles, preferences, and account settings.
"""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.traveler_profile import TravelerProfile
from app.schemas.user import (
    UserResponse,
    UserWithProfileResponse,
    UserUpdateRequest,
    UserPreferencesUpdateRequest,
    TravelerProfileUpdate,
    TravelerProfileResponse,
    UserStatsResponse
)


router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me/profile", response_model=TravelerProfileResponse)
async def get_my_profile(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current user's traveler profile.

    Returns personalization settings used for recommendations and RAG functions.

    Requires:
        Authorization: Bearer <firebase_token>

    Returns:
        Traveler profile information
    """
    if not user.traveler_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Traveler profile not found"
        )

    return user.traveler_profile


@router.put("/me/profile", response_model=TravelerProfileResponse)
async def update_my_profile(
    profile_update: TravelerProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update current user's traveler profile.

    Updates personalization settings for recommendations.

    Requires:
        Authorization: Bearer <firebase_token>

    Args:
        profile_update: Profile fields to update

    Returns:
        Updated traveler profile
    """
    if not user.traveler_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Traveler profile not found"
        )

    # Update fields if provided
    update_data = profile_update.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(user.traveler_profile, field, value)

    db.commit()
    db.refresh(user.traveler_profile)

    return user.traveler_profile


@router.get("/me/preferences")
async def get_my_preferences(
    user: User = Depends(get_current_user)
):
    """
    Get current user's preferences.

    Requires:
        Authorization: Bearer <firebase_token>

    Returns:
        User preferences (notifications, language, currency, etc.)
    """
    return user.preferences


@router.put("/me/preferences")
async def update_my_preferences(
    preferences_update: UserPreferencesUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update current user's preferences.

    Requires:
        Authorization: Bearer <firebase_token>

    Args:
        preferences_update: Preferences to update

    Returns:
        Updated preferences
    """
    # Get current preferences
    current_prefs = user.preferences or {}

    # Update with new values
    update_data = preferences_update.model_dump(exclude_unset=True)
    current_prefs.update(update_data)

    user.preferences = current_prefs
    db.commit()
    db.refresh(user)

    return user.preferences


@router.get("/me/stats", response_model=UserStatsResponse)
async def get_my_stats(
    user: User = Depends(get_current_user)
):
    """
    Get current user's statistics.

    Returns counts of itineraries, favorites, collections, reviews, and trips.

    Requires:
        Authorization: Bearer <firebase_token>

    Returns:
        User statistics
    """
    # Calculate account age
    account_age = (datetime.now(timezone.utc) - user.created_at).days

    # TODO: Calculate actual counts when models are available
    # For now, return zeros
    return UserStatsResponse(
        total_itineraries=0,
        total_favorites=0,
        total_collections=0,
        total_reviews=0,
        total_trips=0,
        account_age_days=account_age
    )


@router.put("/me", response_model=UserResponse)
async def update_my_account(
    user_update: UserUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update current user's account information.

    Requires:
        Authorization: Bearer <firebase_token>

    Args:
        user_update: User fields to update (display_name, photo_url)

    Returns:
        Updated user information
    """
    # Update fields if provided
    update_data = user_update.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)

    return user


@router.delete("/me")
async def delete_my_account(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete current user's account (soft delete).

    Sets is_active to False instead of hard deletion.
    User data is retained but account is deactivated.

    Requires:
        Authorization: Bearer <firebase_token>

    Returns:
        Deletion confirmation message
    """
    user.is_active = False
    db.commit()

    return {
        "message": "Account deactivated successfully. Contact support to reactivate."
    }
