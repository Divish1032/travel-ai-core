"""
Video model for Stage 1 crawled data tracking.

Replaces MetadataTracker S3 JSON file with relational database.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Integer, Float, Text, DateTime, Boolean, Enum
from sqlalchemy.orm import relationship
import enum

from app.database import Base


class StageStatus(str, enum.Enum):
    """Processing stage status enum."""
    NOT_STARTED = "not_started"
    PENDING = "pending"
    COMPLETE = "complete"
    FAILED = "failed"


class Video(Base):
    """
    Video metadata and processing status tracker.

    Replaces the MetadataTracker JSON file from S3.
    Tracks video crawling, extraction, and canonicalization progress.
    """
    __tablename__ = "videos"

    # Primary key
    video_id = Column(String(255), primary_key=True, index=True)  # e.g., 'youtube_abc123'

    # Source metadata
    source = Column(String(50), nullable=False, index=True)  # 'youtube', 'tiktok'
    source_url = Column(Text, nullable=True)
    title = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    channel_name = Column(String(255), nullable=True)
    published_at = Column(DateTime, nullable=True)

    # Video properties
    duration_seconds = Column(Integer, nullable=True)
    view_count = Column(Integer, nullable=True)
    language = Column(String(10), nullable=True)  # ISO 639-1 code

    # Stage 1: Crawl & Transcribe
    stage_1_status = Column(Enum(StageStatus), default=StageStatus.NOT_STARTED, index=True)
    stage_1_completed_at = Column(DateTime, nullable=True)
    stage_1_error = Column(Text, nullable=True)
    stage_1_cost_usd = Column(Float, default=0.0)

    # Stage 2: Entity Extraction
    stage_2_status = Column(Enum(StageStatus), default=StageStatus.NOT_STARTED, index=True)
    stage_2_completed_at = Column(DateTime, nullable=True)
    stage_2_error = Column(Text, nullable=True)
    stage_2_entities_extracted = Column(Integer, default=0)
    stage_2_cost_usd = Column(Float, default=0.0)
    stage_2_llm_model = Column(String(100), nullable=True)
    stage_2_tokens_used = Column(Integer, default=0)

    # Stage 3: Canonicalization
    stage_3_status = Column(Enum(StageStatus), default=StageStatus.NOT_STARTED, index=True)
    stage_3_completed_at = Column(DateTime, nullable=True)
    stage_3_error = Column(Text, nullable=True)
    stage_3_canonical_entities = Column(Integer, default=0)
    stage_3_cost_usd = Column(Float, default=0.0)

    # S3 paths (only for Stage 1 blobs)
    s3_audio_path = Column(Text, nullable=True)  # Audio file location
    s3_raw_data_path = Column(Text, nullable=True)  # Raw JSONL with transcript

    # Quality metrics
    extraction_quality = Column(String(50), nullable=True)  # 'high', 'medium', 'low'

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    transcripts = relationship("Transcript", back_populates="video", cascade="all, delete-orphan")
    extracted_entities = relationship("ExtractedEntity", back_populates="video", cascade="all, delete-orphan")
    traveler_profile = relationship("TravelerProfile", back_populates="video", uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Video(video_id='{self.video_id}', title='{self.title[:50] if self.title else None}')>"

    @property
    def total_cost_usd(self) -> float:
        """Calculate total cost across all stages."""
        return (self.stage_1_cost_usd or 0) + (self.stage_2_cost_usd or 0) + (self.stage_3_cost_usd or 0)

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            'video_id': self.video_id,
            'source': self.source,
            'title': self.title,
            'duration_seconds': self.duration_seconds,
            'language': self.language,
            'stage_1_status': self.stage_1_status.value if self.stage_1_status else None,
            'stage_2_status': self.stage_2_status.value if self.stage_2_status else None,
            'stage_3_status': self.stage_3_status.value if self.stage_3_status else None,
            'stage_2_entities_extracted': self.stage_2_entities_extracted,
            'stage_3_canonical_entities': self.stage_3_canonical_entities,
            'total_cost_usd': self.total_cost_usd,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
