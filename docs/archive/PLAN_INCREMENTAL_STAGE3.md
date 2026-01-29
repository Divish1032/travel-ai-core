# Plan: Incremental Stage 3 Processing

**Status: ✅ FULLY IMPLEMENTED (All 5 Phases)**

---

## Implementation Status

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1: Entity Registry | Persistent registry with stable IDs | ✅ Complete |
| Phase 2: Experience Dedup | Hash-based deduplication | ✅ Complete |
| Phase 3: Incremental Mode | Process only new, merge with existing | ✅ Complete |
| Phase 4: Smart Merging | Conflict resolution rules for all metadata | ✅ Complete |
| Phase 5: Score History | Track score evolution over time | ✅ Complete |

### Files Created/Modified

- `src/storage/entity_registry.py` - **NEW**: Entity registry with stable IDs
- `src/storage/score_history.py` - **NEW**: Score history tracking for trends
- `src/processors/entity_merger.py` - **NEW**: Complete merge logic with score recalculation
- `src/processors/canonicalization.py` - **MODIFIED**: Added experience deduplication
- `cli/process_stage3.py` - **MODIFIED**: Added `--mode` flag, score history recording

### Usage

```bash
# Incremental processing (default - merge new with existing)
./crawl.sh process-stage3

# Full reprocessing (recreate all entities)
./crawl.sh process-stage3 --mode full
```

---

## Problem Statement

Current Stage 3 processes ALL Stage 2 entities as a fresh batch each run:
- No concept of "existing" canonical entities
- Entity IDs regenerated each run (unstable)
- Same video can add duplicate experiences on re-run
- Cannot incrementally add new video data to existing entities

## Goals

1. **Incremental Processing**: Process only NEW Stage 2 files, merge into existing canonical entities
2. **Stable Entity IDs**: Maintain consistent IDs across runs
3. **Experience Deduplication**: Avoid duplicate experiences from same video
4. **Score Evolution**: Track how scores change over time

---

## Implementation Plan

### Phase 1: Entity Registry & Stable IDs (Critical)

**Purpose**: Create a persistent registry to track canonical entities with stable IDs

**Files to create/modify**:
- `src/storage/entity_registry.py` (NEW)
- `src/processors/canonicalization.py` (MODIFY)

**Entity Registry Structure**:
```python
{
    "registry_version": "1.0",
    "last_updated": "2026-01-26T12:00:00Z",
    "entities": {
        "attraction_bangkok_001": {
            "canonical_name": "Wat Pho",
            "aliases": ["Wat Phra Chetuphon", "Temple of Reclining Buddha"],
            "entity_type": "attraction",
            "city": "Bangkok",
            "country": "Thailand",
            "created_at": "2026-01-20T10:00:00Z",
            "last_updated": "2026-01-26T12:00:00Z",
            "source_video_ids": ["youtube_abc123", "youtube_def456"],
            "experience_count": 5,
            "name_signature": "wat_pho||bangkok||attraction"  # For matching
        }
    },
    "name_index": {
        "wat_pho||bangkok||attraction": "attraction_bangkok_001",
        "wat_phra_chetuphon||bangkok||attraction": "attraction_bangkok_001"
    },
    "next_sequence": {
        "attraction_bangkok": 15,
        "restaurant_chiang_mai": 8
    }
}
```

**Key Functions**:
```python
class EntityRegistry:
    def load_registry(self) -> Dict
    def save_registry(self) -> None
    def find_matching_entity(self, name, city, entity_type) -> Optional[str]
    def register_new_entity(self, entity) -> str  # Returns stable ID
    def update_entity_metadata(self, entity_id, updates) -> None
    def get_next_sequence(self, entity_type, city) -> int
```

**Matching Logic**:
1. Exact match on `name_signature` (normalized name + city + type)
2. Fuzzy match on aliases (threshold 0.90)
3. If no match found, create new entity with next available ID

---

### Phase 2: Experience Deduplication (Critical)

**Purpose**: Prevent duplicate experiences from same video

**Files to modify**:
- `src/processors/canonicalization.py`
- `src/processors/stage3_enrichment.py`

**Deduplication Strategy**:
```python
def dedupe_experiences(experiences: List[Dict]) -> List[Dict]:
    """Remove duplicate experiences from same video."""
    seen = set()
    unique = []

    for exp in experiences:
        # Create unique key: video_id + experience_hash
        exp_hash = hashlib.md5(exp['experience'].encode()).hexdigest()[:8]
        key = f"{exp['source_video_id']}_{exp_hash}"

        if key not in seen:
            seen.add(key)
            unique.append(exp)

    return unique
```

**Where to apply**:
1. During canonicalization (when merging entity groups)
2. During incremental merge (when adding new experiences to existing entity)

---

### Phase 3: Incremental Processing Mode (Critical)

**Purpose**: Process only new Stage 2 files, merge with existing entities

**Files to modify**:
- `cli/process_stage3.py`
- `src/processors/stage3_loader.py`

**New CLI Flag**:
```bash
# Full reprocess (current behavior)
python cli/process_stage3.py --mode full

# Incremental (default, new behavior)
python cli/process_stage3.py --mode incremental

# Force reprocess specific videos
python cli/process_stage3.py --reprocess-videos video1,video2
```

**Processing Flow (Incremental)**:
```
1. Load existing canonical entities from S3
2. Build entity registry from existing entities
3. Load NEW Stage 2 files only (check processed_videos.json)
4. For each new entity:
   a. Match against registry (exact + fuzzy)
   b. If match found:
      - Load existing canonical entity
      - Merge new experiences (dedupe)
      - Recalculate scores
      - Update registry metadata
   c. If no match:
      - Run normal deduplication within new batch
      - Create new canonical entity with registry ID
      - Add to registry
5. Save updated entities + registry
6. Mark Stage 2 files as processed
```

**Processed Videos Tracker**:
```json
{
    "version": "1.0",
    "processed_videos": {
        "youtube_abc123": {
            "processed_at": "2026-01-20T10:00:00Z",
            "stage3_run_id": "run_20260120_100000",
            "entities_created": ["attraction_bangkok_001", "restaurant_bangkok_005"]
        }
    }
}
```

---

### Phase 4: Smart Merging Logic (Medium Priority)

**Purpose**: Intelligently merge new data with existing entities

**Files to create/modify**:
- `src/processors/entity_merger.py` (NEW)

**Merge Rules**:

| Field | Merge Strategy |
|-------|---------------|
| `canonical_name` | Keep existing (most validated) |
| `aliases` | Union of all aliases (dedupe) |
| `experiences` | Append new, dedupe by video+hash |
| `total_mentions` | Recalculate from experiences |
| `source_video_ids` | Union of all video IDs |
| `coordinates` | Keep highest confidence |
| `city`, `country` | Keep if existing valid, else update |
| `temporal_info` | Re-aggregate from all experiences |
| `logistics_info` | Re-aggregate from all experiences |
| `practical_tips` | Merge with conflict resolution |
| `popularity_score` | Recalculate from merged data |
| `data_freshness` | Recalculate from all experiences |
| `enhanced_rating` | Recalculate from all experiences |

**Conflict Resolution**:
```python
def merge_practical_tips(existing: Dict, new: Dict) -> Dict:
    """Merge practical tips with recency preference."""
    merged = existing.copy()

    for key, value in new.items():
        if key not in merged or not merged[key]:
            merged[key] = value
        elif value:
            # Keep more recent if different
            # Could add source tracking for tie-breaking
            merged[key] = value

    return merged
```

---

### Phase 5: Score Evolution Tracking (Low Priority)

**Purpose**: Track how entity scores change over time

**Files to create**:
- `src/storage/score_history.py` (NEW)

**Score History Structure**:
```json
{
    "entity_id": "attraction_bangkok_001",
    "history": [
        {
            "timestamp": "2026-01-20T10:00:00Z",
            "run_id": "run_20260120",
            "scores": {
                "popularity_score": 0.45,
                "freshness_score": 1.0,
                "enhanced_rating": 4.2,
                "total_mentions": 3,
                "experience_count": 3
            }
        },
        {
            "timestamp": "2026-01-26T12:00:00Z",
            "run_id": "run_20260126",
            "scores": {
                "popularity_score": 0.65,
                "freshness_score": 1.0,
                "enhanced_rating": 4.4,
                "total_mentions": 5,
                "experience_count": 5
            }
        }
    ]
}
```

**Use Cases**:
- Detect trending entities (rapid score increase)
- Identify declining entities (score drop)
- Quality monitoring (score stability)

---

## Implementation Order

| Phase | Priority | Effort | Dependencies |
|-------|----------|--------|--------------|
| Phase 1: Entity Registry | Critical | 1-2 days | None |
| Phase 2: Experience Deduplication | Critical | 0.5 day | None |
| Phase 3: Incremental Processing | Critical | 2-3 days | Phase 1, 2 |
| Phase 4: Smart Merging | Medium | 1-2 days | Phase 1, 3 |
| Phase 5: Score History | Low | 1 day | Phase 3 |

**Recommended Start**: Phase 1 + 2 together, then Phase 3

---

## Migration Strategy

1. **Backup Current Data**: Save current canonical entities before changes
2. **Generate Initial Registry**: Create registry from existing canonical entities
3. **Test Incremental Mode**: Run with `--dry-run` first
4. **Gradual Rollout**: Process small batch first, verify results
5. **Full Deployment**: Enable incremental as default

---

## Testing Strategy

1. **Unit Tests**:
   - Entity registry CRUD operations
   - Experience deduplication logic
   - Merge conflict resolution

2. **Integration Tests**:
   - Full incremental processing flow
   - Re-running on same data (should be idempotent)
   - Adding new video to existing entity

3. **Regression Tests**:
   - Compare output quality vs full reprocess
   - Verify no data loss during merging

---

## Rollback Plan

If issues arise:
1. Switch back to `--mode full`
2. Registry can be regenerated from canonical entities
3. Full reprocess always available as fallback

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Processing time (incremental vs full) | 80% faster for small additions |
| Entity ID stability | 100% (IDs never change) |
| Experience deduplication | 0 duplicates from same video |
| Data quality | Equal or better than full reprocess |

---

## Questions to Confirm

1. Should we allow manual entity ID overrides (for important landmarks)?
2. How to handle entity type changes (e.g., "attraction" → "destination")?
3. Should alias matching be bidirectional (new entity matches existing alias)?
4. Retention policy for score history (keep forever vs last N runs)?

---

*Plan created: 2026-01-26*
*Status: Pending approval*
