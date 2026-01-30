"""
Itinerary management router.

Provides endpoints for creating, managing, sharing, and exporting travel itineraries.
"""

import secrets
import uuid
import math
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_optional
from app.models.user import User
from app.models.itinerary import SavedItinerary
from app.schemas.itinerary import (
    ItineraryCreate,
    ItineraryUpdate,
    ItineraryResponse,
    ItineraryListResponse,
    ShareItineraryRequest,
    ShareItineraryResponse,
    ExportItineraryRequest,
)


router = APIRouter(prefix="/itineraries", tags=["Itineraries"])


@router.post("", response_model=ItineraryResponse, status_code=status.HTTP_201_CREATED)
async def create_itinerary(
    itinerary: ItineraryCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Save a new itinerary.

    Creates a new saved itinerary from RAG pipeline output.

    Requires:
        Authorization: Bearer <firebase_token>

    Args:
        itinerary: Itinerary data including destination, duration, and full JSON

    Returns:
        Created itinerary with ID and timestamps
    """
    new_itinerary = SavedItinerary(
        id=uuid.uuid4(),
        user_id=user.id,
        title=itinerary.title or f"{itinerary.destination} - {itinerary.duration_days} Days",
        destination=itinerary.destination,
        duration_days=itinerary.duration_days,
        itinerary_data=itinerary.itinerary_data,
        notes=itinerary.notes,
        is_public=itinerary.is_public,
        created_at=datetime.now(timezone.utc)
    )

    db.add(new_itinerary)
    db.commit()
    db.refresh(new_itinerary)

    return new_itinerary


@router.get("", response_model=ItineraryListResponse)
async def list_itineraries(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    destination: str = Query(None, description="Filter by destination")
):
    """
    List user's saved itineraries (paginated).

    Returns all itineraries created by the authenticated user.

    Requires:
        Authorization: Bearer <firebase_token>

    Query params:
        page: Page number (default 1)
        per_page: Items per page (default 20, max 100)
        destination: Filter by destination name (optional)

    Returns:
        Paginated list of itineraries
    """
    # Build query
    query = db.query(SavedItinerary).filter(SavedItinerary.user_id == user.id)

    # Apply destination filter if provided
    if destination:
        query = query.filter(SavedItinerary.destination.ilike(f"%{destination}%"))

    # Get total count
    total = query.count()

    # Apply pagination
    query = query.order_by(desc(SavedItinerary.created_at))
    query = query.offset((page - 1) * per_page).limit(per_page)

    # Execute query
    itineraries = query.all()

    return ItineraryListResponse(
        items=itineraries,
        total=total,
        page=page,
        per_page=per_page,
        pages=math.ceil(total / per_page) if total > 0 else 0
    )


@router.get("/{itinerary_id}", response_model=ItineraryResponse)
async def get_itinerary(
    itinerary_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific itinerary by ID.

    Requires:
        Authorization: Bearer <firebase_token>

    Args:
        itinerary_id: UUID of the itinerary

    Returns:
        Full itinerary details

    Raises:
        404: Itinerary not found or doesn't belong to user
    """
    itinerary = db.query(SavedItinerary).filter(
        SavedItinerary.id == itinerary_id,
        SavedItinerary.user_id == user.id
    ).first()

    if not itinerary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Itinerary not found"
        )

    return itinerary


@router.put("/{itinerary_id}", response_model=ItineraryResponse)
async def update_itinerary(
    itinerary_id: uuid.UUID,
    itinerary_update: ItineraryUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update an existing itinerary.

    Allows updating title, notes, public status, and itinerary data.

    Requires:
        Authorization: Bearer <firebase_token>

    Args:
        itinerary_id: UUID of the itinerary
        itinerary_update: Fields to update

    Returns:
        Updated itinerary

    Raises:
        404: Itinerary not found or doesn't belong to user
    """
    itinerary = db.query(SavedItinerary).filter(
        SavedItinerary.id == itinerary_id,
        SavedItinerary.user_id == user.id
    ).first()

    if not itinerary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Itinerary not found"
        )

    # Update fields if provided
    update_data = itinerary_update.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(itinerary, field, value)

    itinerary.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(itinerary)

    return itinerary


@router.delete("/{itinerary_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_itinerary(
    itinerary_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete an itinerary.

    Permanently removes the itinerary from the database.

    Requires:
        Authorization: Bearer <firebase_token>

    Args:
        itinerary_id: UUID of the itinerary

    Raises:
        404: Itinerary not found or doesn't belong to user
    """
    itinerary = db.query(SavedItinerary).filter(
        SavedItinerary.id == itinerary_id,
        SavedItinerary.user_id == user.id
    ).first()

    if not itinerary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Itinerary not found"
        )

    db.delete(itinerary)
    db.commit()


@router.post("/{itinerary_id}/fork", response_model=ItineraryResponse, status_code=status.HTTP_201_CREATED)
async def fork_itinerary(
    itinerary_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Duplicate/fork an itinerary.

    Creates a copy of an existing itinerary.

    Requires:
        Authorization: Bearer <firebase_token>

    Args:
        itinerary_id: UUID of the itinerary to fork

    Returns:
        New forked itinerary

    Raises:
        404: Itinerary not found or doesn't belong to user
    """
    original = db.query(SavedItinerary).filter(
        SavedItinerary.id == itinerary_id,
        SavedItinerary.user_id == user.id
    ).first()

    if not original:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Itinerary not found"
        )

    # Create duplicate
    forked = SavedItinerary(
        id=uuid.uuid4(),
        user_id=user.id,
        title=f"{original.title} (Copy)" if original.title else "Copy",
        destination=original.destination,
        duration_days=original.duration_days,
        itinerary_data=original.itinerary_data,
        notes=original.notes,
        is_public=False,  # Forks are private by default
        created_at=datetime.now(timezone.utc)
    )

    db.add(forked)
    db.commit()
    db.refresh(forked)

    return forked


@router.post("/{itinerary_id}/share", response_model=ShareItineraryResponse)
async def share_itinerary(
    itinerary_id: uuid.UUID,
    share_request: ShareItineraryRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate a shareable link for an itinerary.

    Creates a unique token for public access to the itinerary.

    Requires:
        Authorization: Bearer <firebase_token>

    Args:
        itinerary_id: UUID of the itinerary
        share_request: Sharing configuration (expiration)

    Returns:
        Share token and URL

    Raises:
        404: Itinerary not found or doesn't belong to user
    """
    itinerary = db.query(SavedItinerary).filter(
        SavedItinerary.id == itinerary_id,
        SavedItinerary.user_id == user.id
    ).first()

    if not itinerary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Itinerary not found"
        )

    # Generate share token if not exists
    if not itinerary.share_token:
        itinerary.share_token = secrets.token_urlsafe(32)

    # Set expiration if provided
    if share_request.expires_in_days:
        itinerary.share_expires_at = datetime.now(timezone.utc) + timedelta(days=share_request.expires_in_days)
    else:
        itinerary.share_expires_at = None

    itinerary.is_public = True
    itinerary.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(itinerary)

    # Build share URL (you'll need to replace with actual domain)
    share_url = f"/api/itineraries/shared/{itinerary.share_token}"

    return ShareItineraryResponse(
        share_token=itinerary.share_token,
        share_url=share_url,
        expires_at=itinerary.share_expires_at
    )


@router.get("/shared/{share_token}", response_model=ItineraryResponse)
async def get_shared_itinerary(
    share_token: str,
    user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    Access a publicly shared itinerary.

    No authentication required - uses share token for access.

    Args:
        share_token: Share token from share URL

    Returns:
        Shared itinerary

    Raises:
        404: Share token invalid or expired
    """
    itinerary = db.query(SavedItinerary).filter(
        SavedItinerary.share_token == share_token,
        SavedItinerary.is_public == True
    ).first()

    if not itinerary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shared itinerary not found"
        )

    # Check expiration
    if itinerary.share_expires_at and itinerary.share_expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Share link has expired"
        )

    return itinerary


@router.post("/{itinerary_id}/export")
async def export_itinerary(
    itinerary_id: uuid.UUID,
    export_request: ExportItineraryRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Export itinerary to various formats.

    Supports PDF, JSON, and iCal formats.

    Requires:
        Authorization: Bearer <firebase_token>

    Args:
        itinerary_id: UUID of the itinerary
        export_request: Export format configuration

    Returns:
        File download or export data

    Raises:
        404: Itinerary not found
        501: Export format not implemented yet
    """
    itinerary = db.query(SavedItinerary).filter(
        SavedItinerary.id == itinerary_id,
        SavedItinerary.user_id == user.id
    ).first()

    if not itinerary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Itinerary not found"
        )

    # TODO: Implement actual export logic
    # For now, return JSON format as it's simplest
    if export_request.format == "json":
        return {
            "format": "json",
            "data": itinerary.itinerary_data,
            "metadata": {
                "title": itinerary.title,
                "destination": itinerary.destination,
                "duration_days": itinerary.duration_days,
                "created_at": itinerary.created_at.isoformat()
            }
        }

    # Other formats not yet implemented
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Export format '{export_request.format}' not yet implemented"
    )
