"""
Collections management router.

Provides endpoints for managing user's place collections.
"""

import uuid
import math
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.collection import Collection
from app.schemas.collection import (
    CollectionCreate,
    CollectionUpdate,
    CollectionResponse,
    CollectionListResponse,
    AddPlaceToCollectionRequest,
)


router = APIRouter(prefix="/collections", tags=["Collections"])


@router.post("", response_model=CollectionResponse, status_code=status.HTTP_201_CREATED)
async def create_collection(
    collection: CollectionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new collection.

    Creates a named collection for organizing places.

    Requires:
        Authorization: Bearer <firebase_token>

    Args:
        collection: Collection name, description, and initial places

    Returns:
        Created collection
    """
    new_collection = Collection(
        id=uuid.uuid4(),
        user_id=user.id,
        name=collection.name,
        description=collection.description,
        entity_ids=collection.entity_ids,
        is_public=collection.is_public,
        created_at=datetime.now(timezone.utc)
    )

    db.add(new_collection)
    db.commit()
    db.refresh(new_collection)

    return new_collection


@router.get("", response_model=CollectionListResponse)
async def list_collections(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page")
):
    """
    List user's collections (paginated).

    Returns all collections created by the authenticated user.

    Requires:
        Authorization: Bearer <firebase_token>

    Query params:
        page: Page number (default 1)
        per_page: Items per page (default 20, max 100)

    Returns:
        Paginated list of collections
    """
    # Build query
    query = db.query(Collection).filter(Collection.user_id == user.id)

    # Get total count
    total = query.count()

    # Apply pagination (newest first)
    query = query.order_by(desc(Collection.created_at))
    query = query.offset((page - 1) * per_page).limit(per_page)

    # Execute query
    collections = query.all()

    return CollectionListResponse(
        items=collections,
        total=total,
        page=page,
        per_page=per_page,
        pages=math.ceil(total / per_page) if total > 0 else 0
    )


@router.get("/{collection_id}", response_model=CollectionResponse)
async def get_collection(
    collection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific collection by ID.

    Requires:
        Authorization: Bearer <firebase_token>

    Args:
        collection_id: UUID of the collection

    Returns:
        Collection details with all entity IDs

    Raises:
        404: Collection not found or doesn't belong to user
    """
    collection = db.query(Collection).filter(
        Collection.id == collection_id,
        Collection.user_id == user.id
    ).first()

    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found"
        )

    return collection


@router.put("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: uuid.UUID,
    collection_update: CollectionUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update a collection's metadata.

    Updates name, description, or public status.

    Requires:
        Authorization: Bearer <firebase_token>

    Args:
        collection_id: UUID of the collection
        collection_update: Fields to update

    Returns:
        Updated collection

    Raises:
        404: Collection not found or doesn't belong to user
    """
    collection = db.query(Collection).filter(
        Collection.id == collection_id,
        Collection.user_id == user.id
    ).first()

    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found"
        )

    # Update fields if provided
    update_data = collection_update.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(collection, field, value)

    collection.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(collection)

    return collection


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a collection.

    Permanently removes the collection.

    Requires:
        Authorization: Bearer <firebase_token>

    Args:
        collection_id: UUID of the collection

    Raises:
        404: Collection not found or doesn't belong to user
    """
    collection = db.query(Collection).filter(
        Collection.id == collection_id,
        Collection.user_id == user.id
    ).first()

    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found"
        )

    db.delete(collection)
    db.commit()


@router.post("/{collection_id}/places", response_model=CollectionResponse)
async def add_place_to_collection(
    collection_id: uuid.UUID,
    place: AddPlaceToCollectionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add a place to a collection.

    Adds an entity ID to the collection's place list.

    Requires:
        Authorization: Bearer <firebase_token>

    Args:
        collection_id: UUID of the collection
        place: Entity ID to add

    Returns:
        Updated collection

    Raises:
        404: Collection not found or doesn't belong to user
        409: Place already in collection
    """
    collection = db.query(Collection).filter(
        Collection.id == collection_id,
        Collection.user_id == user.id
    ).first()

    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found"
        )

    # Check if already in collection
    if place.entity_id in collection.entity_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Place already in collection"
        )

    # Add to collection
    collection.entity_ids.append(place.entity_id)
    collection.updated_at = datetime.now(timezone.utc)

    # Mark as modified for SQLAlchemy to detect changes
    db.query(Collection).filter(Collection.id == collection_id).update(
        {"entity_ids": collection.entity_ids},
        synchronize_session=False
    )

    db.commit()
    db.refresh(collection)

    return collection


@router.delete("/{collection_id}/places/{entity_id}", response_model=CollectionResponse)
async def remove_place_from_collection(
    collection_id: uuid.UUID,
    entity_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Remove a place from a collection.

    Removes an entity ID from the collection's place list.

    Requires:
        Authorization: Bearer <firebase_token>

    Args:
        collection_id: UUID of the collection
        entity_id: Entity ID to remove

    Returns:
        Updated collection

    Raises:
        404: Collection or place not found
    """
    collection = db.query(Collection).filter(
        Collection.id == collection_id,
        Collection.user_id == user.id
    ).first()

    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found"
        )

    # Check if in collection
    if entity_id not in collection.entity_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Place not in collection"
        )

    # Remove from collection
    collection.entity_ids.remove(entity_id)
    collection.updated_at = datetime.now(timezone.utc)

    # Mark as modified for SQLAlchemy to detect changes
    db.query(Collection).filter(Collection.id == collection_id).update(
        {"entity_ids": collection.entity_ids},
        synchronize_session=False
    )

    db.commit()
    db.refresh(collection)

    return collection
