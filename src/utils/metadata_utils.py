"""
Metadata Utilities for ChromaDB

Provides utilities for validating and truncating metadata to comply with
ChromaDB Cloud size limits (4KB per metadata value).

Author: TravelAI Team
Date: 2025-12-18
"""

import json
from typing import Dict, Any, List
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Chroma Cloud metadata size limits
CHROMA_CLOUD_MAX_METADATA_SIZE = 4096  # 4KB hard limit
SAFE_METADATA_SIZE = 3584  # 3.5KB safe limit (leaves 500 byte buffer)


def calculate_metadata_size(metadata: Dict[str, Any]) -> int:
    """
    Calculate the size of metadata dictionary in bytes.

    Args:
        metadata: Metadata dictionary

    Returns:
        Size in bytes
    """
    # Convert to JSON to get approximate size
    # ChromaDB internally serializes metadata
    json_str = json.dumps(metadata, ensure_ascii=False)
    return len(json_str.encode('utf-8'))


def truncate_string(text: str, max_chars: int = 500) -> str:
    """
    Truncate string to maximum characters.

    Args:
        text: String to truncate
        max_chars: Maximum characters (default: 500)

    Returns:
        Truncated string with ellipsis if truncated
    """
    if not text or len(text) <= max_chars:
        return text

    return text[:max_chars-3] + "..."


def truncate_list_field(value: str, max_items: int = 10, separator: str = ",") -> str:
    """
    Truncate comma-separated list to maximum number of items.

    Args:
        value: Comma-separated string
        max_items: Maximum number of items to keep
        separator: Separator character (default: comma)

    Returns:
        Truncated list as string
    """
    if not value:
        return value

    items = [item.strip() for item in value.split(separator)]

    if len(items) <= max_items:
        return value

    truncated_items = items[:max_items]
    return separator.join(truncated_items)


def truncate_metadata(
    metadata: Dict[str, Any],
    max_size: int = SAFE_METADATA_SIZE,
    field_limits: Dict[str, int] = None
) -> Dict[str, Any]:
    """
    Truncate metadata fields to stay under size limit.

    This function intelligently truncates metadata fields to ensure
    the total metadata size stays under the Chroma Cloud limit.

    Truncation priority:
    1. Truncate list fields (themes, travel_style) to 10 items
    2. Truncate long string fields to 500 chars
    3. If still over limit, progressively reduce field sizes

    Args:
        metadata: Original metadata dictionary
        max_size: Maximum total size in bytes (default: 3.5KB)
        field_limits: Optional dict of field-specific character limits

    Returns:
        Truncated metadata dictionary
    """
    if not metadata:
        return metadata

    # Default field limits
    if field_limits is None:
        field_limits = {
            'themes': 10,  # Max 10 themes
            'travel_style': 5,  # Max 5 styles
            'canonical_name': 200,
            'city': 100,
            'country': 100,
            'normalized_location': 200,
            'profile_key': 100,
            'source_video_id': 50,
            'cost_mentioned': 200
        }

    # Create copy to avoid modifying original
    truncated = metadata.copy()

    # First pass: Apply field-specific limits
    for field, value in truncated.items():
        if not value or not isinstance(value, str):
            continue

        # Handle list fields (comma-separated)
        if field in ['themes', 'travel_style'] and ',' in value:
            max_items = field_limits.get(field, 10)
            truncated[field] = truncate_list_field(value, max_items)

        # Handle string fields
        elif field in field_limits:
            max_chars = field_limits[field]
            truncated[field] = truncate_string(value, max_chars)

    # Check if we're still over limit
    current_size = calculate_metadata_size(truncated)

    if current_size <= max_size:
        return truncated

    # Second pass: Aggressively truncate remaining long fields
    logger.warning(f"Metadata size {current_size} bytes exceeds limit {max_size} bytes")
    logger.warning("Applying aggressive truncation...")

    for field, value in list(truncated.items()):
        if not isinstance(value, str) or len(value) < 50:
            continue

        # Progressively reduce length
        if len(value) > 200:
            truncated[field] = truncate_string(value, 200)
        elif len(value) > 100:
            truncated[field] = truncate_string(value, 100)

    return truncated


def validate_metadata_size(
    metadata: Dict[str, Any],
    entity_id: str = None,
    auto_truncate: bool = True
) -> Dict[str, Any]:
    """
    Validate metadata size and optionally truncate if needed.

    Args:
        metadata: Metadata dictionary to validate
        entity_id: Optional entity ID for logging
        auto_truncate: If True, automatically truncate oversized metadata

    Returns:
        Validated (and possibly truncated) metadata

    Raises:
        ValueError: If metadata exceeds hard limit and auto_truncate is False
    """
    size = calculate_metadata_size(metadata)

    # Log size for monitoring
    entity_label = f" for {entity_id}" if entity_id else ""

    if size > CHROMA_CLOUD_MAX_METADATA_SIZE:
        error_msg = (
            f"Metadata{entity_label} size {size:,} bytes exceeds "
            f"Chroma Cloud hard limit of {CHROMA_CLOUD_MAX_METADATA_SIZE:,} bytes"
        )

        if not auto_truncate:
            raise ValueError(error_msg)

        logger.warning(error_msg)
        logger.warning("Auto-truncating metadata...")

        metadata = truncate_metadata(metadata, max_size=SAFE_METADATA_SIZE)
        new_size = calculate_metadata_size(metadata)

        if new_size > CHROMA_CLOUD_MAX_METADATA_SIZE:
            raise ValueError(
                f"Metadata{entity_label} still exceeds limit after truncation: "
                f"{new_size:,} bytes > {CHROMA_CLOUD_MAX_METADATA_SIZE:,} bytes"
            )

        logger.info(f"Metadata truncated: {size:,} → {new_size:,} bytes")

    elif size > SAFE_METADATA_SIZE:
        logger.warning(
            f"Metadata{entity_label} size {size:,} bytes approaching limit "
            f"(safe threshold: {SAFE_METADATA_SIZE:,} bytes)"
        )

        if auto_truncate:
            metadata = truncate_metadata(metadata, max_size=SAFE_METADATA_SIZE)
            new_size = calculate_metadata_size(metadata)
            logger.info(f"Metadata truncated: {size:,} → {new_size:,} bytes")

    return metadata


def log_metadata_stats(metadata_list: List[Dict[str, Any]], collection_name: str = None):
    """
    Log statistics about metadata sizes in a batch.

    Args:
        metadata_list: List of metadata dictionaries
        collection_name: Optional collection name for logging
    """
    if not metadata_list:
        return

    sizes = [calculate_metadata_size(m) for m in metadata_list]

    avg_size = sum(sizes) / len(sizes)
    max_size = max(sizes)
    min_size = min(sizes)
    over_safe = sum(1 for s in sizes if s > SAFE_METADATA_SIZE)
    over_limit = sum(1 for s in sizes if s > CHROMA_CLOUD_MAX_METADATA_SIZE)

    collection_label = f" ({collection_name})" if collection_name else ""

    logger.info(f"\n📊 Metadata Size Statistics{collection_label}:")
    logger.info(f"   Total items: {len(metadata_list)}")
    logger.info(f"   Avg size: {avg_size:,.0f} bytes")
    logger.info(f"   Min size: {min_size:,} bytes")
    logger.info(f"   Max size: {max_size:,} bytes")
    logger.info(f"   Over safe limit ({SAFE_METADATA_SIZE:,} bytes): {over_safe}")
    logger.info(f"   Over hard limit ({CHROMA_CLOUD_MAX_METADATA_SIZE:,} bytes): {over_limit}")

    if over_limit > 0:
        logger.error(f"   ⚠️  {over_limit} metadata items exceed Chroma Cloud limit!")
    elif over_safe > 0:
        logger.warning(f"   ⚠️  {over_safe} metadata items approaching limit")
