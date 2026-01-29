# Adding New Pipeline Stages

Guide to extending the TravelAI pipeline with new stages.

---

## Overview

TravelAI's 5-stage pipeline can be extended with additional stages. This guide shows how to add Stage 6 (or modify existing stages).

**Example Use Cases:**
- Stage 6: Price aggregation from booking sites
- Stage 6: User review sentiment analysis
- Stage 6: Image/video content analysis
- Parallel pipeline: Social media integration

---

## Stage Template

### 1. Create Stage Module

**File:** `src/processors/stage6_example.py`

```python
"""
Stage 6: Price Aggregation

Fetches and aggregates pricing data for entities from booking sites.

Input:
    - Stage 3 canonical entities
    - Entity types: hotel, restaurant, activity

Output:
    - Price ranges per entity
    - Availability information
    - Booking links

Data Flow:
    Stage 3 canonical → Fetch prices → Aggregate → Update metadata
"""

from typing import List, Dict, Any, Optional
from src.utils.logging import get_logger
from src.storage.s3 import S3Storage

logger = get_logger(__name__)


class Stage6Processor:
    """
    Stage 6: Price Aggregation Processor
    """

    def __init__(self, storage: S3Storage):
        """Initialize Stage 6 processor."""
        self.storage = storage
        logger.info("Stage 6 Processor initialized")

    def process_entity(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process single entity and add price data.

        Args:
            entity: Canonical entity from Stage 3

        Returns:
            Entity with added price_data field
        """
        entity_name = entity.get('canonical_name')
        entity_type = entity.get('entity_type')

        logger.info(f"Processing {entity_type}: {entity_name}")

        # Fetch prices from APIs
        price_data = self._fetch_prices(entity_name, entity_type)

        # Add to entity
        entity['price_data'] = price_data

        return entity

    def _fetch_prices(
        self,
        entity_name: str,
        entity_type: str
    ) -> Dict[str, Any]:
        """
        Fetch prices from booking sites.

        Args:
            entity_name: Name of entity
            entity_type: Type of entity (hotel, restaurant, activity)

        Returns:
            Price data dict
        """
        # Implementation: Call booking APIs
        # Example: Booking.com, Agoda, Expedia
        pass

    def process_all(self) -> Dict[str, Any]:
        """
        Process all canonical entities.

        Returns:
            Processing statistics
        """
        # Load canonical entities from Stage 3
        entities = self.storage.download_json("metadata/canonical_entities.json")

        results = {
            'processed': 0,
            'failed': 0,
            'total_entities': len(entities)
        }

        for canonical_id, entity in entities.items():
            try:
                updated_entity = self.process_entity(entity)
                entities[canonical_id] = updated_entity
                results['processed'] += 1
            except Exception as e:
                logger.error(f"Failed to process {canonical_id}: {e}")
                results['failed'] += 1

        # Save updated entities
        self.storage.upload_json(
            entities,
            "stage6_prices/canonical_entities_with_prices.json"
        )

        logger.info(f"Stage 6 complete: {results}")
        return results
```

---

### 2. Create CLI Command

**File:** `cli/process_stage6.py`

```python
#!/usr/bin/env python3
"""
CLI command for Stage 6: Price Aggregation

Usage:
    ./crawl.sh process-stage6
    ./crawl.sh process-stage6 --entity-types hotel,restaurant
"""

import click
from src.processors.stage6_example import Stage6Processor
from src.storage.s3 import S3Storage
from src.utils.logging import get_logger

logger = get_logger(__name__)


@click.command()
@click.option(
    '--entity-types',
    default='hotel,restaurant,activity',
    help='Comma-separated entity types to process'
)
def process_stage6(entity_types: str):
    """
    Run Stage 6: Price Aggregation
    """
    logger.info("="*80)
    logger.info("STAGE 6: PRICE AGGREGATION")
    logger.info("="*80)

    # Initialize
    storage = S3Storage()
    processor = Stage6Processor(storage)

    # Process
    types_list = [t.strip() for t in entity_types.split(',')]
    logger.info(f"Processing entity types: {types_list}")

    results = processor.process_all()

    # Summary
    logger.info("\n" + "="*80)
    logger.info("STAGE 6 COMPLETE")
    logger.info("="*80)
    logger.info(f"Processed: {results['processed']}")
    logger.info(f"Failed: {results['failed']}")
    logger.info(f"Total: {results['total_entities']}")


if __name__ == '__main__':
    process_stage6()
```

---

### 3. Add to crawl.sh

**File:** `crawl.sh`

```bash
#!/bin/bash

# ... existing code ...

case "$1" in
    # ... existing stages ...

    process-stage6)
        shift
        python cli/process_stage6.py "$@"
        ;;

    stage6-stats)
        python -c "
from src.storage.s3 import S3Storage
storage = S3Storage()
data = storage.download_json('stage6_prices/canonical_entities_with_prices.json')
print(f'Total entities with prices: {len(data)}')
"
        ;;

    # ... rest of code ...
esac
```

---

### 4. Update Metadata Tracker

**File:** `src/utils/metadata_tracker.py`

Add Stage 6 status tracking:

```python
def update_stage6_status(self, entity_id: str, status: str):
    """Update Stage 6 status for entity."""
    self.update_status(entity_id, "stage6_prices", status)

def get_stage6_pending(self) -> List[str]:
    """Get entities pending Stage 6 processing."""
    return self.get_pending_entities("stage6_prices")
```

---

### 5. Add Tests

**File:** `tests/unit/test_stage6.py`

```python
import pytest
from src.processors.stage6_example import Stage6Processor
from src.storage.s3 import S3Storage

def test_stage6_processor_init():
    """Test Stage 6 processor initialization."""
    storage = S3Storage()
    processor = Stage6Processor(storage)

    assert processor.storage is not None

def test_fetch_prices():
    """Test price fetching logic."""
    storage = S3Storage()
    processor = Stage6Processor(storage)

    price_data = processor._fetch_prices("Test Hotel", "hotel")

    assert price_data is not None
    assert 'price_range' in price_data

@pytest.mark.integration
def test_stage6_full_pipeline():
    """Test Stage 6 integration with S3."""
    storage = S3Storage()
    processor = Stage6Processor(storage)

    results = processor.process_all()

    assert results['total_entities'] > 0
```

---

## Integration Points

### S3 Storage Structure

Add new S3 path:

```
s3://your-bucket/
├── stage6_prices/
│   ├── canonical_entities_with_prices.json
│   └── price_history/
│       └── 2026-01-29.json
```

### Metadata Schema

Extend canonical entity schema:

```typescript
{
  canonical_id: string
  // ... existing fields ...

  // Stage 6 additions
  price_data?: {
    currency: string
    price_range: {
      min: number
      max: number
      avg: number
    }
    last_updated: string
    booking_links: Array<{
      site: string
      url: string
      price: number
    }>
    availability: boolean
  }
}
```

---

## Parallel Pipeline Example

### Creating a Parallel Pipeline

**Use Case:** Social Media Integration Pipeline

```python
"""
Social Media Integration Pipeline (Parallel to Main Pipeline)

Input:
    - Stage 1 transcripts
    - Social media data (Instagram, TikTok)

Output:
    - Social sentiment scores
    - Trending entities
    - User-generated content

Independence:
    - Runs parallel to main pipeline
    - Does not block Stages 2-5
"""

class SocialMediaPipeline:
    def __init__(self):
        self.instagram_api = InstagramAPI()
        self.tiktok_api = TikTokAPI()

    def process_video(self, video_id: str):
        """Process video for social media data."""
        # Fetch related social media posts
        posts = self.fetch_related_posts(video_id)

        # Analyze sentiment
        sentiment = self.analyze_sentiment(posts)

        # Identify trending entities
        trending = self.identify_trending(posts)

        return {
            'social_sentiment': sentiment,
            'trending_entities': trending,
            'post_count': len(posts)
        }
```

---

## Best Practices

### 1. Design Principles

- **Single Responsibility:** One stage, one purpose
- **Idempotent:** Can re-run safely
- **S3-Based:** Store outputs in S3
- **Independent:** Don't tightly couple with other stages
- **Logged:** Comprehensive logging
- **Tested:** Unit and integration tests

### 2. Error Handling

```python
def process_entity(self, entity: Dict[str, Any]) -> Dict[str, Any]:
    """Process entity with error handling."""
    try:
        result = self._do_processing(entity)
        return result
    except APIError as e:
        logger.error(f"API error: {e}")
        # Retry logic
        return self._retry_processing(entity)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        # Mark as failed, continue with next entity
        return entity  # Return unmodified
```

### 3. Cost Tracking

```python
from src.utils.cost_tracker import CostTracker

class Stage6Processor:
    def __init__(self, storage: S3Storage):
        self.storage = storage
        self.cost_tracker = CostTracker("stage6")

    def process_entity(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        # Track API costs
        cost = self._fetch_prices(entity)
        self.cost_tracker.add_cost(
            entity_id=entity['canonical_id'],
            cost=cost,
            api='booking_api'
        )

        return entity
```

---

## Documentation

### Update Documentation

1. **Create stage doc:** `docs/03-pipeline-stages/stage6-prices.md`
2. **Update pipeline overview:** Add Stage 6 to data flow
3. **Update CLI commands:** Document new commands
4. **Update configuration:** Add new .env variables

---

## Example: Real Extension

### Stage 6: Image Analysis

**Purpose:** Analyze images from videos to extract visual entities

**Implementation:**

```python
from PIL import Image
import torch
from transformers import CLIPModel, CLIPProcessor

class Stage6ImageAnalysis:
    def __init__(self):
        self.model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        self.processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

    def extract_frames(self, video_path: str) -> List[Image.Image]:
        """Extract key frames from video."""
        # Use OpenCV to extract frames
        pass

    def analyze_frame(self, image: Image.Image) -> Dict[str, Any]:
        """Analyze single frame for travel entities."""
        # Use CLIP to identify landmarks, food, activities
        pass

    def process_video(self, video_id: str) -> Dict[str, Any]:
        """Process video for visual entities."""
        frames = self.extract_frames(video_id)
        results = [self.analyze_frame(f) for f in frames]
        return self.aggregate_results(results)
```

---

## References

- **Project Structure:** [project-structure.md](../01-getting-started/project-structure.md)
- **Contributing:** [contributing.md](contributing.md)
- **Testing:** [testing.md](testing.md)
- **Pipeline Overview:** [pipeline-overview.md](../02-architecture/pipeline-overview.md)
