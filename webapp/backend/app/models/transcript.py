"""
Transcript model for storing video transcript segments.

Each video has multiple transcript segments with timestamps.
Enables full-text search and temporal queries.
"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import TSVECTOR

from app.database import Base


class Transcript(Base):
    """
    Individual transcript segment from video.

    Stores segment-by-segment transcription with timestamps.
    Supports full-text search on corrected text.
    """
    __tablename__ = "transcripts"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign key
    video_id = Column(String(255), ForeignKey('videos.video_id', ondelete='CASCADE'), nullable=False, index=True)

    # Segment metadata
    segment_index = Column(Integer, nullable=False)  # 0-indexed
    start_time = Column(Float, nullable=True)  # seconds
    end_time = Column(Float, nullable=True)  # seconds

    # Text content
    original_text = Column(Text, nullable=True)  # Before Thai place name correction
    corrected_text = Column(Text, nullable=True)  # After correction
    language = Column(String(10), nullable=True)  # Language code

    # Whisper metadata
    confidence = Column(Float, nullable=True)  # Whisper confidence score

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    video = relationship("Video", back_populates="transcripts")

    # Indexes
    __table_args__ = (
        # Unique constraint: one segment per video
        Index('idx_video_segment', 'video_id', 'segment_index', unique=True),
    )

    def __repr__(self):
        text_preview = self.corrected_text[:50] if self.corrected_text else self.original_text[:50] if self.original_text else ""
        return f"<Transcript(video_id='{self.video_id}', segment={self.segment_index}, text='{text_preview}...')>"

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            'id': self.id,
            'video_id': self.video_id,
            'segment_index': self.segment_index,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'original_text': self.original_text,
            'corrected_text': self.corrected_text,
            'language': self.language,
            'confidence': self.confidence,
        }
