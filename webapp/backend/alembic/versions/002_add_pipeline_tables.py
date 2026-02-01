"""Add pipeline tables for Stage 1-3 processing

Revision ID: 002_add_pipeline_tables
Revises: 286a9a2a6607
Create Date: 2026-02-02

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_add_pipeline_tables'
down_revision = '286a9a2a6607_add_itineraries_favorites_collections'
branch_labels = None
depends_on = None


def upgrade():
    """Create pipeline tables for storing Stage 1-3 processing data."""

    # Create enum types
    op.execute("""
        CREATE TYPE stagestatus AS ENUM ('not_started', 'pending', 'complete', 'failed');
        CREATE TYPE entitytype AS ENUM ('destination', 'restaurant', 'hotel', 'activity', 'attraction', 'transportation', 'shopping', 'unknown');
        CREATE TYPE sentiment AS ENUM ('positive', 'negative', 'neutral', 'mixed');
    """)

    # ===== TABLE 1: videos =====
    op.create_table(
        'videos',
        sa.Column('video_id', sa.String(255), primary_key=True),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('source_url', sa.Text, nullable=True),
        sa.Column('title', sa.Text, nullable=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('channel_name', sa.String(255), nullable=True),
        sa.Column('published_at', sa.DateTime, nullable=True),
        sa.Column('duration_seconds', sa.Integer, nullable=True),
        sa.Column('view_count', sa.Integer, nullable=True),
        sa.Column('language', sa.String(10), nullable=True),

        # Stage 1
        sa.Column('stage_1_status', sa.Enum('not_started', 'pending', 'complete', 'failed', name='stagestatus'), server_default='not_started'),
        sa.Column('stage_1_completed_at', sa.DateTime, nullable=True),
        sa.Column('stage_1_error', sa.Text, nullable=True),
        sa.Column('stage_1_cost_usd', sa.Float, server_default='0.0'),

        # Stage 2
        sa.Column('stage_2_status', sa.Enum('not_started', 'pending', 'complete', 'failed', name='stagestatus'), server_default='not_started'),
        sa.Column('stage_2_completed_at', sa.DateTime, nullable=True),
        sa.Column('stage_2_error', sa.Text, nullable=True),
        sa.Column('stage_2_entities_extracted', sa.Integer, server_default='0'),
        sa.Column('stage_2_cost_usd', sa.Float, server_default='0.0'),
        sa.Column('stage_2_llm_model', sa.String(100), nullable=True),
        sa.Column('stage_2_tokens_used', sa.Integer, server_default='0'),

        # Stage 3
        sa.Column('stage_3_status', sa.Enum('not_started', 'pending', 'complete', 'failed', name='stagestatus'), server_default='not_started'),
        sa.Column('stage_3_completed_at', sa.DateTime, nullable=True),
        sa.Column('stage_3_error', sa.Text, nullable=True),
        sa.Column('stage_3_canonical_entities', sa.Integer, server_default='0'),
        sa.Column('stage_3_cost_usd', sa.Float, server_default='0.0'),

        # S3 paths
        sa.Column('s3_audio_path', sa.Text, nullable=True),
        sa.Column('s3_raw_data_path', sa.Text, nullable=True),

        # Quality
        sa.Column('extraction_quality', sa.String(50), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Indexes for videos
    op.create_index('idx_videos_source', 'videos', ['source'])
    op.create_index('idx_videos_stage_1_status', 'videos', ['stage_1_status'])
    op.create_index('idx_videos_stage_2_status', 'videos', ['stage_2_status'])
    op.create_index('idx_videos_stage_3_status', 'videos', ['stage_3_status'])

    # ===== TABLE 2: transcripts =====
    op.create_table(
        'transcripts',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('video_id', sa.String(255), sa.ForeignKey('videos.video_id', ondelete='CASCADE'), nullable=False),
        sa.Column('segment_index', sa.Integer, nullable=False),
        sa.Column('start_time', sa.Float, nullable=True),
        sa.Column('end_time', sa.Float, nullable=True),
        sa.Column('original_text', sa.Text, nullable=True),
        sa.Column('corrected_text', sa.Text, nullable=True),
        sa.Column('language', sa.String(10), nullable=True),
        sa.Column('confidence', sa.Float, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )

    # Indexes for transcripts
    op.create_index('idx_transcripts_video_id', 'transcripts', ['video_id'])
    op.create_index('idx_video_segment', 'transcripts', ['video_id', 'segment_index'], unique=True)

    # Full-text search index on corrected_text
    op.execute("""
        CREATE INDEX idx_transcripts_text_fts ON transcripts
        USING GIN(to_tsvector('english', COALESCE(corrected_text, '')));
    """)

    # ===== TABLE 3: video_traveler_profiles =====
    op.create_table(
        'video_traveler_profiles',
        sa.Column('video_id', sa.String(255), sa.ForeignKey('videos.video_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('traveler_type', sa.String(50), nullable=True),
        sa.Column('age_range', sa.String(20), nullable=True),
        sa.Column('budget_tier', sa.String(50), nullable=True),
        sa.Column('travel_style', postgresql.ARRAY(sa.String), nullable=True),
        sa.Column('confidence_score', sa.Float, nullable=True),
        sa.Column('llm_model', sa.String(100), nullable=True),
        sa.Column('extracted_at', sa.DateTime, server_default=sa.func.now()),
    )

    # ===== TABLE 4: extracted_entities =====
    op.create_table(
        'extracted_entities',
        sa.Column('entity_id', sa.String(255), primary_key=True),
        sa.Column('video_id', sa.String(255), sa.ForeignKey('videos.video_id', ondelete='CASCADE'), nullable=False),
        sa.Column('entity_type', sa.Enum('destination', 'restaurant', 'hotel', 'activity', 'attraction', 'transportation', 'shopping', 'unknown', name='entitytype'), nullable=False),
        sa.Column('entity_name', sa.String(500), nullable=False),
        sa.Column('location', sa.String(500), nullable=True),
        sa.Column('city', sa.String(255), nullable=True),
        sa.Column('country', sa.String(255), nullable=True),
        sa.Column('experience', sa.Text, nullable=True),
        sa.Column('sentiment', sa.Enum('positive', 'negative', 'neutral', 'mixed', name='sentiment'), nullable=True),
        sa.Column('rating', sa.Float, nullable=True),
        sa.Column('cost_mentioned', sa.String(100), nullable=True),
        sa.Column('timestamp_start', sa.Float, nullable=True),
        sa.Column('timestamp_end', sa.Float, nullable=True),
        sa.Column('tags', postgresql.ARRAY(sa.String), nullable=True),
        sa.Column('confidence_score', sa.Float, nullable=True),
        sa.Column('llm_model', sa.String(100), nullable=True),
        sa.Column('extracted_at', sa.DateTime, nullable=True),
        sa.Column('context', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )

    # Indexes for extracted_entities
    op.create_index('idx_extracted_entities_video_id', 'extracted_entities', ['video_id'])
    op.create_index('idx_extracted_entities_type', 'extracted_entities', ['entity_type'])
    op.create_index('idx_extracted_entities_name', 'extracted_entities', ['entity_name'])
    op.create_index('idx_extracted_entities_city', 'extracted_entities', ['city'])
    op.create_index('idx_entity_name_type', 'extracted_entities', ['entity_name', 'entity_type'])
    op.create_index('idx_entity_name_city_type', 'extracted_entities', ['entity_name', 'city', 'entity_type'])

    # ===== TABLE 5: canonical_entities =====
    op.create_table(
        'canonical_entities',
        sa.Column('entity_id', sa.String(255), primary_key=True),
        sa.Column('canonical_name', sa.String(500), nullable=False),
        sa.Column('aliases', postgresql.ARRAY(sa.String), nullable=True),
        sa.Column('entity_type', sa.Enum('destination', 'restaurant', 'hotel', 'activity', 'attraction', 'transportation', 'shopping', 'unknown', name='entitytype'), nullable=False),
        sa.Column('city', sa.String(255), nullable=True),
        sa.Column('country', sa.String(255), nullable=True),
        sa.Column('location_description', sa.Text, nullable=True),
        sa.Column('latitude', sa.Float, nullable=True),
        sa.Column('longitude', sa.Float, nullable=True),
        sa.Column('geocoded_at', sa.DateTime, nullable=True),
        sa.Column('geocoding_source', sa.String(50), nullable=True),
        sa.Column('total_mentions', sa.Integer, server_default='1'),
        sa.Column('confidence_score', sa.Float, nullable=True),
        sa.Column('source_video_count', sa.Integer, server_default='1'),
        sa.Column('consensus', postgresql.JSONB, nullable=True),
        sa.Column('temporal_info', postgresql.JSONB, nullable=True),
        sa.Column('logistics_info', postgresql.JSONB, nullable=True),
        sa.Column('practical_tips', postgresql.ARRAY(sa.String), nullable=True),
        sa.Column('popularity_score', sa.Float, nullable=True),
        sa.Column('freshness_score', sa.Float, nullable=True),
        sa.Column('fame_score', sa.Float, nullable=True),
        sa.Column('first_seen_video_id', sa.String(255), nullable=True),
        sa.Column('last_seen_video_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Indexes for canonical_entities
    op.create_index('idx_canonical_entities_type', 'canonical_entities', ['entity_type'])
    op.create_index('idx_canonical_entities_city', 'canonical_entities', ['city'])
    op.create_index('idx_canonical_entities_name', 'canonical_entities', ['canonical_name'])
    op.create_index('idx_canonical_city_type', 'canonical_entities', ['city', 'entity_type'])
    op.create_index('idx_canonical_coordinates', 'canonical_entities', ['latitude', 'longitude'])
    op.create_index('idx_canonical_popularity', 'canonical_entities', ['popularity_score'])
    op.create_index('idx_canonical_fame', 'canonical_entities', ['fame_score'])

    # Full-text search index on canonical_name
    op.execute("""
        CREATE INDEX idx_canonical_name_fts ON canonical_entities
        USING GIN(to_tsvector('english', canonical_name));
    """)

    # ===== TABLE 6: entity_experiences =====
    op.create_table(
        'entity_experiences',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('canonical_entity_id', sa.String(255), sa.ForeignKey('canonical_entities.entity_id', ondelete='CASCADE'), nullable=False),
        sa.Column('extracted_entity_id', sa.String(255), sa.ForeignKey('extracted_entities.entity_id', ondelete='CASCADE'), nullable=False),
        sa.Column('video_id', sa.String(255), sa.ForeignKey('videos.video_id', ondelete='CASCADE'), nullable=False),
        sa.Column('mention_count', sa.Integer, server_default='1'),
        sa.Column('sentiment', sa.String(50), nullable=True),
        sa.Column('rating', sa.Float, nullable=True),
        sa.Column('context', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )

    # Indexes for entity_experiences
    op.create_index('idx_experiences_canonical', 'entity_experiences', ['canonical_entity_id'])
    op.create_index('idx_experiences_extracted', 'entity_experiences', ['extracted_entity_id'])
    op.create_index('idx_experience_video', 'entity_experiences', ['video_id'])
    op.create_index('idx_unique_canonical_extracted', 'entity_experiences', ['canonical_entity_id', 'extracted_entity_id'], unique=True)

    # ===== TABLE 7: insights =====
    op.create_table(
        'insights',
        sa.Column('insight_id', sa.String(255), primary_key=True),
        sa.Column('category', sa.String(100), nullable=False),
        sa.Column('scope', sa.String(100), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('tags', postgresql.ARRAY(sa.String), nullable=True),
        sa.Column('source_video_count', sa.Integer, server_default='1'),
        sa.Column('total_mentions', sa.Integer, server_default='1'),
        sa.Column('confidence_score', sa.Float, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Indexes for insights
    op.create_index('idx_insights_category', 'insights', ['category'])
    op.create_index('idx_insights_scope', 'insights', ['scope'])
    op.create_index('idx_insight_category_scope', 'insights', ['category', 'scope'])

    # Full-text search index on content
    op.execute("""
        CREATE INDEX idx_insight_content_fts ON insights
        USING GIN(to_tsvector('english', content));
    """)

    # ===== TABLE 8: insight_mentions =====
    op.create_table(
        'insight_mentions',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('insight_id', sa.String(255), sa.ForeignKey('insights.insight_id', ondelete='CASCADE'), nullable=False),
        sa.Column('video_id', sa.String(255), sa.ForeignKey('videos.video_id', ondelete='CASCADE'), nullable=False),
        sa.Column('source_type', sa.String(50), nullable=True),
        sa.Column('source_entity_id', sa.String(255), nullable=True),
        sa.Column('context', sa.Text, nullable=True),
        sa.Column('mentioned_at', sa.DateTime, server_default=sa.func.now()),
    )

    # Indexes for insight_mentions
    op.create_index('idx_insight_mentions_insight', 'insight_mentions', ['insight_id'])
    op.create_index('idx_insight_mentions_video', 'insight_mentions', ['video_id'])

    # ===== TABLE 9: insight_related_entities =====
    op.create_table(
        'insight_related_entities',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('insight_id', sa.String(255), sa.ForeignKey('insights.insight_id', ondelete='CASCADE'), nullable=False),
        sa.Column('entity_id', sa.String(255), sa.ForeignKey('canonical_entities.entity_id', ondelete='CASCADE'), nullable=False),
        sa.Column('relationship_type', sa.String(50), nullable=True),
    )

    # Indexes for insight_related_entities
    op.create_index('idx_insight_related_insight', 'insight_related_entities', ['insight_id'])
    op.create_index('idx_insight_related_entity', 'insight_related_entities', ['entity_id'])
    op.create_index('idx_insight_entity', 'insight_related_entities', ['insight_id', 'entity_id'], unique=True)


def downgrade():
    """Drop all pipeline tables."""
    op.drop_table('insight_related_entities')
    op.drop_table('insight_mentions')
    op.drop_table('insights')
    op.drop_table('entity_experiences')
    op.drop_table('canonical_entities')
    op.drop_table('extracted_entities')
    op.drop_table('video_traveler_profiles')
    op.drop_table('transcripts')
    op.drop_table('videos')

    # Drop enum types
    op.execute("DROP TYPE stagestatus;")
    op.execute("DROP TYPE entitytype;")
    op.execute("DROP TYPE sentiment;")
