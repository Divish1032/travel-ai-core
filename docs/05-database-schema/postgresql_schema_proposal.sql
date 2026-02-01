-- TravelAI PostgreSQL Schema Proposal
-- Replaces S3-based entity storage with structured relational database
-- Same PostgreSQL instance as FastAPI backend (webapp/backend)

-- ==============================================================================
-- 1. Videos Table - Replaces MetadataTracker
-- ==============================================================================

CREATE TABLE videos (
    -- Primary key
    video_id VARCHAR(255) PRIMARY KEY,  -- e.g., 'youtube_ABC123'

    -- Source metadata
    source VARCHAR(50) NOT NULL,  -- 'youtube', 'tiktok', etc.
    source_url TEXT,
    title TEXT,
    description TEXT,
    duration_seconds INTEGER,
    published_at TIMESTAMP,

    -- Processing status (replaces stages in MetadataTracker)
    stage_1_status VARCHAR(50) DEFAULT 'not_started',  -- 'pending', 'complete', 'failed'
    stage_1_completed_at TIMESTAMP,
    stage_1_error TEXT,

    stage_2_status VARCHAR(50) DEFAULT 'not_started',
    stage_2_completed_at TIMESTAMP,
    stage_2_error TEXT,
    stage_2_entities_extracted INTEGER DEFAULT 0,

    stage_3_status VARCHAR(50) DEFAULT 'not_started',
    stage_3_completed_at TIMESTAMP,
    stage_3_error TEXT,
    stage_3_canonical_entities INTEGER DEFAULT 0,

    -- Cost tracking
    stage_1_cost_usd DECIMAL(10, 6) DEFAULT 0,
    stage_2_cost_usd DECIMAL(10, 6) DEFAULT 0,
    stage_3_cost_usd DECIMAL(10, 6) DEFAULT 0,
    total_cost_usd DECIMAL(10, 6) GENERATED ALWAYS AS (
        stage_1_cost_usd + stage_2_cost_usd + stage_3_cost_usd
    ) STORED,

    -- S3 paths for blobs
    s3_audio_path TEXT,  -- Audio file location
    s3_transcript_path TEXT,  -- Raw transcript JSON

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX idx_videos_stage_2_status ON videos(stage_2_status);
CREATE INDEX idx_videos_stage_3_status ON videos(stage_3_status);
CREATE INDEX idx_videos_created_at ON videos(created_at);
CREATE INDEX idx_videos_source ON videos(source);

-- ==============================================================================
-- 2. Transcripts Table - Queryable Transcript Segments
-- ==============================================================================

CREATE TABLE transcripts (
    id SERIAL PRIMARY KEY,
    video_id VARCHAR(255) NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,

    -- Segment data
    segment_index INTEGER NOT NULL,
    start_time DECIMAL(10, 2),  -- seconds
    end_time DECIMAL(10, 2),

    -- Text content
    original_text TEXT,  -- Before correction
    corrected_text TEXT,  -- After Thai place name correction
    language VARCHAR(10),  -- 'th', 'en', etc.

    -- Metadata
    speaker VARCHAR(255),  -- Optional
    confidence DECIMAL(4, 3),  -- Whisper confidence

    created_at TIMESTAMP DEFAULT NOW(),

    -- Unique constraint: one segment per video
    UNIQUE(video_id, segment_index)
);

-- Indexes for transcript search
CREATE INDEX idx_transcripts_video_id ON transcripts(video_id);
CREATE INDEX idx_transcripts_text ON transcripts USING GIN(to_tsvector('english', corrected_text));  -- Full-text search

-- ==============================================================================
-- 3. Extracted Entities Table - Stage 2 Output (Raw, Before Deduplication)
-- ==============================================================================

CREATE TABLE extracted_entities (
    -- Primary key
    entity_id VARCHAR(255) PRIMARY KEY,  -- e.g., 'youtube_ABC123_entity_001'

    -- Foreign keys
    video_id VARCHAR(255) NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,

    -- Entity classification
    entity_type VARCHAR(100) NOT NULL,  -- 'attraction', 'restaurant', 'hotel', etc.

    -- Core attributes
    name VARCHAR(500) NOT NULL,
    location VARCHAR(500),  -- City or area mentioned
    city VARCHAR(255),  -- Normalized city name
    country VARCHAR(255),  -- Normalized country

    -- Extracted data
    mentions INTEGER DEFAULT 1,
    sentiment VARCHAR(50),  -- 'positive', 'negative', 'neutral'
    avg_rating DECIMAL(3, 2),  -- If mentioned in transcript

    -- Context from transcript
    context JSONB,  -- {
                    --   "mention_timestamps": [120.5, 450.2],
                    --   "quotes": ["amazing food", "must visit"],
                    --   "mentioned_themes": ["food", "nightlife"],
                    --   "traveler_profile": {"type": "solo", "budget": "budget"}
                    -- }

    -- LLM extraction metadata
    extraction_confidence DECIMAL(4, 3),
    llm_model VARCHAR(100),
    extracted_at TIMESTAMP DEFAULT NOW(),

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for Stage 3 deduplication and queries
CREATE INDEX idx_extracted_entities_video_id ON extracted_entities(video_id);
CREATE INDEX idx_extracted_entities_type ON extracted_entities(entity_type);
CREATE INDEX idx_extracted_entities_name ON extracted_entities(name);
CREATE INDEX idx_extracted_entities_city ON extracted_entities(city);
CREATE INDEX idx_extracted_entities_name_type ON extracted_entities(name, entity_type);  -- Composite for deduplication

-- ==============================================================================
-- 4. Canonical Entities Table - Stage 3 Output (Deduplicated with Consensus)
-- ==============================================================================

CREATE TABLE canonical_entities (
    -- Primary key (stable ID across runs)
    entity_id VARCHAR(255) PRIMARY KEY,  -- e.g., 'attraction_bangkok_001'

    -- Canonical attributes
    canonical_name VARCHAR(500) NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    aliases TEXT[],  -- Array of alternative names

    -- Location
    city VARCHAR(255),
    country VARCHAR(255),
    location_description TEXT,

    -- Geolocation
    latitude DECIMAL(10, 7),
    longitude DECIMAL(10, 7),
    geocoded_at TIMESTAMP,
    geocoding_source VARCHAR(50),  -- 'google_maps', 'nominatim'

    -- Aggregate statistics
    total_mentions INTEGER DEFAULT 1,
    confidence_score DECIMAL(4, 3),
    source_video_count INTEGER DEFAULT 1,  -- How many videos mention this

    -- Consensus data (LLM-generated)
    consensus JSONB,  -- {
                      --   "avg_rating": 4.5,
                      --   "avg_cost": "$$",
                      --   "themes": ["food", "romantic", "nightlife"],
                      --   "best_for": ["couples", "solo"],
                      --   "top_experiences": ["rooftop bar", "sunset view"],
                      --   "traveler_profiles": [...]
                      -- }

    -- Enrichment data (LLM + transcript hybrid)
    temporal_info JSONB,  -- {
                          --   "opening_hours": "10:00-22:00",
                          --   "best_time_to_visit": "sunset",
                          --   "seasonal_info": "peak in Dec-Feb",
                          --   "source": "llm_inferred",
                          --   "confidence": 0.85
                          -- }

    logistics_info JSONB,  -- {
                           --   "typical_duration": "2-3 hours",
                           --   "cost_range": "500-1000 THB",
                           --   "booking_required": true,
                           --   "source": "transcript_extracted",
                           --   "confidence": 0.95
                           -- }

    practical_tips JSONB,  -- {
                           --   "tips": ["Arrive early", "Bring cash"],
                           --   "source": "llm_inferred"
                           -- }

    -- Computed scores
    popularity_score DECIMAL(4, 3),  -- Calculated from mentions, recency
    freshness_score DECIMAL(4, 3),  -- Recency of mentions
    fame_score DECIMAL(4, 3),  -- Combination of popularity + confidence

    -- Registry tracking
    first_seen_video_id VARCHAR(255),  -- First video that mentioned this
    last_seen_video_id VARCHAR(255),  -- Most recent video

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for backend API queries
CREATE INDEX idx_canonical_entities_type ON canonical_entities(entity_type);
CREATE INDEX idx_canonical_entities_city ON canonical_entities(city);
CREATE INDEX idx_canonical_entities_city_type ON canonical_entities(city, entity_type);  -- For "attractions in Bangkok"
CREATE INDEX idx_canonical_entities_coordinates ON canonical_entities(latitude, longitude);  -- For geospatial queries
CREATE INDEX idx_canonical_entities_popularity ON canonical_entities(popularity_score DESC);
CREATE INDEX idx_canonical_entities_name ON canonical_entities(canonical_name);

-- Full-text search on canonical names
CREATE INDEX idx_canonical_entities_name_fts ON canonical_entities USING GIN(to_tsvector('english', canonical_name));

-- ==============================================================================
-- 5. Entity Experiences Table - Links Canonical ↔ Extracted (Many-to-Many)
-- ==============================================================================

CREATE TABLE entity_experiences (
    id SERIAL PRIMARY KEY,

    -- Foreign keys
    canonical_entity_id VARCHAR(255) NOT NULL REFERENCES canonical_entities(entity_id) ON DELETE CASCADE,
    extracted_entity_id VARCHAR(255) NOT NULL REFERENCES extracted_entities(entity_id) ON DELETE CASCADE,
    video_id VARCHAR(255) NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,

    -- Experience-specific data (from this video's mention)
    mention_count INTEGER DEFAULT 1,
    sentiment VARCHAR(50),
    rating DECIMAL(3, 2),
    context JSONB,  -- Specific context from this video

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),

    -- Ensure no duplicate experiences
    UNIQUE(canonical_entity_id, extracted_entity_id)
);

-- Indexes for experience queries
CREATE INDEX idx_experiences_canonical ON entity_experiences(canonical_entity_id);
CREATE INDEX idx_experiences_extracted ON entity_experiences(extracted_entity_id);
CREATE INDEX idx_experiences_video ON entity_experiences(video_id);

-- ==============================================================================
-- 6. Entity Registry Table - Tracks Entity-Name Mappings for Deduplication
-- ==============================================================================

CREATE TABLE entity_registry (
    id SERIAL PRIMARY KEY,

    -- Entity identification
    entity_id VARCHAR(255) NOT NULL,  -- Points to canonical_entities.entity_id
    name_variant VARCHAR(500) NOT NULL,  -- Alternative name/alias
    entity_type VARCHAR(100) NOT NULL,
    city VARCHAR(255),

    -- Tracking
    first_seen_at TIMESTAMP DEFAULT NOW(),
    last_seen_at TIMESTAMP DEFAULT NOW(),
    use_count INTEGER DEFAULT 1,  -- How many times this name variant appeared

    -- Unique constraint: one name variant per entity
    UNIQUE(name_variant, entity_type, city)
);

-- Indexes for fast lookups during deduplication
CREATE INDEX idx_registry_name_type_city ON entity_registry(name_variant, entity_type, city);
CREATE INDEX idx_registry_entity_id ON entity_registry(entity_id);

-- ==============================================================================
-- 7. Processing Runs Table - Track Each Processing Run
-- ==============================================================================

CREATE TABLE processing_runs (
    run_id VARCHAR(255) PRIMARY KEY,  -- e.g., 'run_20240115_143022'

    -- Run metadata
    run_type VARCHAR(50) NOT NULL,  -- 'full', 'incremental'
    stage VARCHAR(50) NOT NULL,  -- 'stage_2', 'stage_3'

    -- Counts
    videos_processed INTEGER DEFAULT 0,
    entities_created INTEGER DEFAULT 0,
    entities_merged INTEGER DEFAULT 0,

    -- Cost tracking
    total_cost_usd DECIMAL(10, 6) DEFAULT 0,
    llm_cost_usd DECIMAL(10, 6) DEFAULT 0,
    geocoding_cost_usd DECIMAL(10, 6) DEFAULT 0,

    -- Status
    status VARCHAR(50) DEFAULT 'running',  -- 'running', 'complete', 'failed'
    error_message TEXT,

    -- Timestamps
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

-- Index for recent runs
CREATE INDEX idx_processing_runs_started_at ON processing_runs(started_at DESC);

-- ==============================================================================
-- 8. Score History Table - Track Entity Score Changes Over Time
-- ==============================================================================

CREATE TABLE score_history (
    id SERIAL PRIMARY KEY,

    -- Entity reference
    entity_id VARCHAR(255) NOT NULL REFERENCES canonical_entities(entity_id) ON DELETE CASCADE,
    run_id VARCHAR(255) NOT NULL,

    -- Scores snapshot
    popularity_score DECIMAL(4, 3),
    freshness_score DECIMAL(4, 3),
    fame_score DECIMAL(4, 3),
    confidence_score DECIMAL(4, 3),
    total_mentions INTEGER,

    -- Timestamp
    recorded_at TIMESTAMP DEFAULT NOW(),

    -- Index for trend analysis
    INDEX idx_score_history_entity ON score_history(entity_id, recorded_at)
);

-- ==============================================================================
-- 9. Triggers - Auto-update timestamps
-- ==============================================================================

-- Function to update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for videos
CREATE TRIGGER update_videos_updated_at
BEFORE UPDATE ON videos
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- Trigger for canonical_entities
CREATE TRIGGER update_canonical_entities_updated_at
BEFORE UPDATE ON canonical_entities
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- ==============================================================================
-- 10. Useful Views for Backend API
-- ==============================================================================

-- View: Entities with experience counts
CREATE VIEW entities_with_stats AS
SELECT
    ce.*,
    COUNT(DISTINCT ee.video_id) as video_count,
    COUNT(ee.id) as experience_count,
    AVG(ee.rating) as avg_experience_rating
FROM canonical_entities ce
LEFT JOIN entity_experiences ee ON ce.entity_id = ee.canonical_entity_id
GROUP BY ce.entity_id;

-- View: Videos with processing summary
CREATE VIEW videos_processing_summary AS
SELECT
    v.video_id,
    v.title,
    v.source,
    v.duration_seconds,
    v.stage_1_status,
    v.stage_2_status,
    v.stage_3_status,
    v.total_cost_usd,
    COUNT(DISTINCT ee.canonical_entity_id) as canonical_entities_contributed
FROM videos v
LEFT JOIN entity_experiences ee ON v.video_id = ee.video_id
GROUP BY v.video_id;

-- ==============================================================================
-- Example Queries
-- ==============================================================================

-- Query 1: Get all attractions in Bangkok with rating > 4.0
-- SELECT * FROM canonical_entities
-- WHERE entity_type = 'attraction'
-- AND city = 'Bangkok'
-- AND (consensus->>'avg_rating')::float > 4.0
-- ORDER BY popularity_score DESC
-- LIMIT 20;

-- Query 2: Find videos that failed Stage 2
-- SELECT * FROM videos
-- WHERE stage_2_status = 'failed'
-- ORDER BY created_at DESC;

-- Query 3: Get all experiences for a canonical entity
-- SELECT
--     ce.canonical_name,
--     ee.*,
--     v.title as video_title
-- FROM canonical_entities ce
-- JOIN entity_experiences ee ON ce.entity_id = ee.canonical_entity_id
-- JOIN videos v ON ee.video_id = v.video_id
-- WHERE ce.entity_id = 'attraction_bangkok_001';

-- Query 4: Search entities by name
-- SELECT * FROM canonical_entities
-- WHERE to_tsvector('english', canonical_name) @@ to_tsquery('english', 'grand palace');

-- Query 5: Get processing cost breakdown
-- SELECT
--     stage,
--     SUM(total_cost_usd) as total_cost,
--     SUM(llm_cost_usd) as llm_cost,
--     SUM(geocoding_cost_usd) as geocoding_cost,
--     COUNT(*) as run_count
-- FROM processing_runs
-- WHERE status = 'complete'
-- GROUP BY stage;
