"""
Favorites management router.

Provides endpoints for managing user's favorite places.
"""

import uuid
import math
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.favorite import Favorite
from app.schemas.favorite import (
    FavoriteCreate,
    FavoriteUpdate,
    FavoriteResponse,
    FavoriteListResponse,
    FavoriteCheckRequest,
    FavoriteCheckResponse,
)


router = APIRouter(prefix="/favorites", tags=["Favorites"])


@router.post("", response_model=FavoriteResponse, status_code=status.HTTP_201_CREATED)
async def add_favorite(
    favorite: FavoriteCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add a place to favorites.

    Saves an entity (place, restaurant, attraction) to user's favorites.

    Requires:
        Authorization: Bearer <firebase_token>

    Args:
        favorite: Entity ID and optional notes

    Returns:
        Created favorite

    Raises:
        409: Entity already favorited by user
    """
    new_favorite = Favorite(
        id=uuid.uuid4(),
        user_id=user.id,
        entity_id=favorite.entity_id,
        notes=favorite.notes,
        saved_at=datetime.now(timezone.utc)
    )

    try:
        db.add(new_favorite)
        db.commit()
        db.refresh(new_favorite)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Entity already favorited"
        )

    return new_favorite


@router.get("", response_model=FavoriteListResponse)
async def list_favorites(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page")
):
    """
    List user's favorites (paginated).

    Returns all places favorited by the authenticated user.

    Requires:
        Authorization: Bearer <firebase_token>

    Query params:
        page: Page number (default 1)
        per_page: Items per page (default 20, max 100)

    Returns:
        Paginated list of favorites
    """
    # Build query
    query = db.query(Favorite).filter(Favorite.user_id == user.id)

    # Get total count
    total = query.count()

    # Apply pagination (newest first)
    query = query.order_by(desc(Favorite.saved_at))
    query = query.offset((page - 1) * per_page).limit(per_page)

    # Execute query
    favorites = query.all()

    return FavoriteListResponse(
        items=favorites,
        total=total,
        page=page,
        per_page=per_page,
        pages=math.ceil(total / per_page) if total > 0 else 0
    )


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite(
    entity_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Remove a place from favorites.

    Deletes the favorite by entity ID.

    Requires:
        Authorization: Bearer <firebase_token>

    Args:
        entity_id: Canonical entity ID to unfavorite

    Raises:
        404: Favorite not found
    """
    favorite = db.query(Favorite).filter(
        Favorite.user_id == user.id,
        Favorite.entity_id == entity_id
    ).first()

    if not favorite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Favorite not found"
        )

    db.delete(favorite)
    db.commit()


@router.put("/{entity_id}", response_model=FavoriteResponse)
async def update_favorite(
    entity_id: str,
    favorite_update: FavoriteUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update favorite notes.

    Allows updating notes associated with a favorite.

    Requires:
        Authorization: Bearer <firebase_token>

    Args:
        entity_id: Canonical entity ID
        favorite_update: Updated notes

    Returns:
        Updated favorite

    Raises:
        404: Favorite not found
    """
    favorite = db.query(Favorite).filter(
        Favorite.user_id == user.id,
        Favorite.entity_id == entity_id
    ).first()

    if not favorite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Favorite not found"
        )

    # Update notes
    if favorite_update.notes is not None:
        favorite.notes = favorite_update.notes

    db.commit()
    db.refresh(favorite)

    return favorite


@router.post("/check", response_model=FavoriteCheckResponse)
async def check_favorites(
    check_request: FavoriteCheckRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Bulk check if entities are favorited.

    Checks favorite status for multiple entities at once.
    Useful for displaying favorite icons in place lists.

    Requires:
        Authorization: Bearer <firebase_token>

    Args:
        check_request: List of entity IDs to check

    Returns:
        Map of entity_id to favorited boolean
    """
    # Query favorites for these entities
    favorites = db.query(Favorite.entity_id).filter(
        Favorite.user_id == user.id,
        Favorite.entity_id.in_(check_request.entity_ids)
    ).all()

    # Create set of favorited entity IDs
    favorited_ids = {fav.entity_id for fav in favorites}

    # Build response map
    result = {
        entity_id: (entity_id in favorited_ids)
        for entity_id in check_request.entity_ids
    }

    return FavoriteCheckResponse(favorited=result)
