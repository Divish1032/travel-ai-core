# Entity Lifecycle & Incremental Processing

## Overview

This document explains how entities are processed, merged, and updated when new video data arrives in Stage 3 processing.

---

## The Problem We're Solving

When you run Stage 3 multiple times with different videos:
- ❌ **OLD BEHAVIOR**: Entities duplicated, creating 644 → 1,288 → 1,932 entities
- ✅ **NEW BEHAVIOR**: Entities merged, maintaining stable ~644 entities with updated experiences

---

## Entity Lifecycle

### 1. First Run (Initial Processing)

```
New Videos (10 videos)
    ↓
Stage 2: Extract raw entities
    ↓
Stage 3: Deduplicate + Canonicalize
    ↓
Result: 644 canonical entities
    ↓
Save to S3: entities_all_20250127_120000.jsonl
```

**What gets saved:**
- Entity ID: `attraction_bangkok_001`
- Canonical name: `"Grand Palace"`
- Experiences: `[exp1, exp2, exp3]` (from 3 videos)
- Scores: Calculated from 3 experiences
- Source videos: `[video1, video2, video3]`

### 2. Second Run (Incremental Processing)

```
New Videos (5 more videos)
    ↓
Stage 2: Extract raw entities
    ↓
Stage 3 Incremental Mode:
    1. Load existing entities from S3 (644 entities)
    2. Load entity registry (tracking IDs and processed videos)
    3. Filter: Process only new videos
    4. Deduplicate new entities
    5. Canonicalize new entities
    6. MERGE with existing entities
    ↓
Result: Still ~644 entities (some merged, some new)
    ↓
Save to S3: entities_all_20250127_140000.jsonl (replaces old state)
```

**What happens to "Grand Palace":**
- Existing entity found via registry matching
- New experiences added: `[exp1, exp2, exp3, exp4]` (exp4 from new video)
- Scores RECALCULATED from all 4 experiences
- Source videos updated: `[video1, video2, video3, video4]`
- **Entity ID remains stable**: `attraction_bangkok_001`

---

## Merge Logic: Field-by-Field Processing

When new experiences arrive for an existing entity, here's what happens to each field:

### Core Identity (Immutable)
- `entity_id`: **PRESERVED** from existing entity (stable ID)
- `entity_type`: **PRESERVED** (unless explicitly changed via `change_entity_type()`)

### Names & Aliases (Union)
- `canonical_name`: **PRESERVED** from existing
- `aliases`: **UNION** of existing + new aliases
  - Example: `["Grand Palace", "Phra Borom Maha Ratcha Wang"]` + `["Palace"]` → `["Grand Palace", "Palace", "Phra Borom Maha Ratcha Wang"]`

### Location (Highest Confidence Wins)
- `city`, `country`, `location`: **PRESERVED** from existing (more stable)
- `coordinates`: **HIGHEST CONFIDENCE WINS**
  ```python
  # If new coordinates have higher confidence
  if new['coordinates']['confidence'] > existing['coordinates']['confidence']:
      merged['coordinates'] = new['coordinates']
  else:
      merged['coordinates'] = existing['coordinates']
  ```

### Experiences (Append + Deduplicate)
- `experiences`: **APPEND** new experiences, **DEDUPLICATE** by hash
  ```python
  # Hash function: f"{video_id}||{content_hash}"
  # Prevents same video from adding duplicate experiences
  ```
- `experience_count`: **RECALCULATED** from merged experiences
- `source_video_ids`: **UNION** of all video IDs

### Temporal Information (Union)
- `temporal_info.best_seasons`: **UNION** of seasons from all experiences
  ```json
  {
    "best_seasons": ["winter", "spring", "summer"],  // Union
    "average_confidence": 0.85,  // Recalculated
    "source": "merged"  // Marked as merged
  }
  ```

### Practical Information (Newer Wins)
- `practical_tips.opening_hours`: **NEWER WINS** (prices/hours change over time)
- `practical_tips.entrance_fee`: **NEWER WINS**
  ```python
  # Use newer data as it's more likely to be current
  if new_timestamp > existing_timestamp:
      merged['practical_tips'] = new['practical_tips']
  ```

### Scores (FULLY RECALCULATED)

This is critical! All scores are **recalculated** from the merged experience set:

#### Popularity Score
```python
# Based on mention frequency across all experiences
popularity_score = calculate_popularity_score(all_experiences)

# More mentions = higher popularity
# Ranges from 0.0 to 1.0
```

#### Freshness Score
```python
# Based on recency of experiences
freshness_score = calculate_freshness_score(all_experiences)

# Newer experiences boost freshness
# Older-only experiences → lower freshness
```

#### Rating Score
```python
# Based on sentiment analysis across all experiences
rating_score = calculate_rating_score(all_experiences)

# Average sentiment from all experiences
# Ranges from 0.0 to 1.0
```

#### Example:
```
Initial (3 experiences):
  popularity: 0.60
  freshness: 0.45
  rating: 0.75

After merge (4 experiences, 1 new):
  popularity: 0.70 ↑ (more mentions)
  freshness: 0.85 ↑ (newer experience added)
  rating: 0.80 ↑ (new positive experience)
```

### Themes & Categories (Union)
- `themes`: **UNION** of all themes, deduplicated
- `activities`: **UNION** of all activities

### Consensus Fields (Recalculated)
- `consensus_description`: Regenerated from all experiences
- `consensus_highlights`: Regenerated from all experiences

---

## Registry Matching Logic

When a new entity arrives, we find existing matches using a 4-tier approach:

### 1. Exact Signature Match
```python
signature = f"{normalized_name}||{normalized_city}||{entity_type}"
# "grandpalace||bangkok||attraction"
```

### 2. Alias Signature Match
```python
# Check if new entity's name matches any existing alias
for alias in existing_aliases:
    alias_sig = f"{normalize(alias)}||{city}||{type}"
    if alias_sig == new_signature:
        return matched_entity_id
```

### 3. Reverse Alias Match
```python
# Check if new entity's alias matches existing canonical name
for new_alias in new_entity_aliases:
    if normalize(new_alias) == normalize(existing_name):
        return matched_entity_id
```

### 4. Type-Flexible Match (Optional)
```python
# Match by name+city, ignore type (for entity type changes)
if allow_type_mismatch:
    if normalize(name) == normalize(existing_name):
        if normalize(city) == normalize(existing_city):
            return matched_entity_id
```

---

## Storage Strategy

### File Versioning
Every Stage 3 run creates timestamped files:
- `entities_all_20250127_120000.jsonl`
- `entities_all_20250127_140000.jsonl`
- `entities_all_20250127_160000.jsonl`

### Loading Strategy (CRITICAL FIX)
**Before fix:**
```python
# Loaded ALL files → duplicates!
for file in all_entity_files:
    load_entities(file)
```

**After fix:**
```python
# Load ONLY the most recent file
latest_file = max(entity_files, key=lambda x: x['last_modified'])
load_entities(latest_file)
```

Old files are kept for:
- Version history
- Rollback capability
- Audit trail

---

## Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ Stage 3 Incremental Processing                              │
└─────────────────────────────────────────────────────────────┘

1. LOAD EXISTING STATE
   ├─ Load latest entities_all_*.jsonl from S3
   ├─ Load entity registry (ID mappings, processed videos)
   └─ Build entity_type → entity_id → entity mapping

2. FILTER NEW VIDEOS
   ├─ Check each Stage 2 entity's video_id
   ├─ Skip if video already processed (in registry)
   └─ Process only entities from new videos

3. DEDUPLICATE & CANONICALIZE
   ├─ Fuzzy matching (Levenshtein)
   ├─ Semantic matching (embeddings)
   ├─ LLM verification
   └─ Create canonical entities from new data

4. MERGE WITH EXISTING
   For each new canonical entity:
   ├─ Match with existing via registry (4-tier matching)
   │
   ├─ IF MATCHED:
   │  ├─ Merge experiences (append + dedupe)
   │  ├─ Union aliases
   │  ├─ Preserve entity_id
   │  ├─ Recalculate all scores
   │  ├─ Update registry metadata
   │  └─ Add to final list
   │
   └─ IF NEW:
      ├─ Generate stable entity_id
      ├─ Register in registry
      └─ Add to final list

   Add unchanged entities (no new data) to final list

5. CONSENSUS & ENRICHMENT
   ├─ Calculate consensus descriptions
   ├─ Extract themes
   ├─ Add temporal/logistics info
   └─ Geocode (cache existing coordinates)

6. SAVE TO S3
   ├─ Save with new timestamp
   ├─ Record in score history
   ├─ Update registry with processed videos
   └─ Keep old files for versioning

7. REGISTRY UPDATES
   └─ Mark all processed videos
   └─ Save updated registry to S3
```

---

## Example: Real Entity Evolution

### Run 1 (3 videos)
```json
{
  "entity_id": "attraction_bangkok_001",
  "canonical_name": "Grand Palace",
  "experience_count": 3,
  "source_video_ids": ["vid1", "vid2", "vid3"],
  "scores": {
    "popularity": 0.60,
    "freshness": 0.45,
    "rating": 0.75
  },
  "temporal_info": {
    "best_seasons": ["winter", "spring"]
  }
}
```

### Run 2 (+2 new videos mentioning Grand Palace)
```json
{
  "entity_id": "attraction_bangkok_001",  // SAME ID
  "canonical_name": "Grand Palace",
  "experience_count": 5,  // 3 + 2
  "source_video_ids": ["vid1", "vid2", "vid3", "vid4", "vid5"],
  "scores": {
    "popularity": 0.72,  // ↑ More mentions
    "freshness": 0.85,   // ↑ Newer videos
    "rating": 0.78       // ↑ More positive reviews
  },
  "temporal_info": {
    "best_seasons": ["winter", "spring", "summer"]  // Added summer
  }
}
```

### Run 3 (+5 videos, 0 mentioning Grand Palace)
```json
{
  "entity_id": "attraction_bangkok_001",  // SAME ID
  "canonical_name": "Grand Palace",
  "experience_count": 5,  // UNCHANGED
  "source_video_ids": ["vid1", "vid2", "vid3", "vid4", "vid5"],
  "scores": {
    "popularity": 0.72,  // UNCHANGED
    "freshness": 0.65,   // ↓ Decaying (no new mentions)
    "rating": 0.78       // UNCHANGED
  },
  "temporal_info": {
    "best_seasons": ["winter", "spring", "summer"]  // UNCHANGED
  }
}
```

---

## Score History Tracking

Every time an entity's scores are updated, we record a snapshot:

```python
{
  "entity_id": "attraction_bangkok_001",
  "history": [
    {
      "timestamp": "2025-01-27T12:00:00Z",
      "run_id": "run_20250127_120000",
      "scores": {"popularity": 0.60, "freshness": 0.45, "rating": 0.75},
      "experience_count": 3
    },
    {
      "timestamp": "2025-01-27T14:00:00Z",
      "run_id": "run_20250127_140000",
      "scores": {"popularity": 0.72, "freshness": 0.85, "rating": 0.78},
      "experience_count": 5
    }
  ]
}
```

This enables:
- Trend detection (trending/declining entities)
- Historical analysis
- Score anomaly detection

---

## Key Improvements Made

### 1. Fixed Duplicate Loading
**Issue**: Loaded all versioned files, causing duplicates
**Fix**: Load only the latest file by timestamp

### 2. Improved Merge Logic
**Issue**: Used inefficient `if entity not in list` check
**Fix**: Track processed entity IDs with a set

### 3. Explicit Score Recalculation
**Issue**: Unclear if scores were updated after merge
**Fix**: Always recalculate scores from merged experiences

### 4. Better Logging
**Issue**: Hard to see what's merged vs new vs unchanged
**Fix**: Log all three categories with counts

---

## Testing Your Setup

To verify incremental processing works:

```bash
# Run 1: Process 10 videos
./crawl.sh process-stage3
# Expected: ~644 entities

# Run 2: Process 5 more videos (some overlap in locations)
./crawl.sh process-stage3
# Expected: ~700 entities (some merged, some new)
# Should NOT be 1,288 entities!

# Check logs for:
# - "Merged with existing: X"
# - "New entities: Y"
# - "Unchanged entities: Z"
# - Total = X + Y + Z (not doubled)
```

---

## Summary

**When new experiences arrive for an existing entity:**

1. ✅ Entity ID stays stable
2. ✅ Experiences are appended (deduplicated)
3. ✅ Aliases are unioned
4. ✅ Scores are FULLY recalculated from all experiences
5. ✅ Temporal info is merged (union for lists, newer-wins for changing data)
6. ✅ Practical tips use newer data
7. ✅ Coordinates use highest confidence
8. ✅ Score history records the changes
9. ✅ Registry tracks processed videos to avoid reprocessing

**The result:** Entities grow richer over time without duplicating!
