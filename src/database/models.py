"""
Database models for TravelAI core project.

This module imports models from webapp/backend/app/models for now,
but provides a stable import path for CLI tools. When the webapp
is separated, these models can be moved to src/database/models/
as independent definitions.
"""

import sys
from pathlib import Path

# Add webapp backend to path for model imports
webapp_backend = Path(__file__).parent.parent.parent / "webapp" / "backend"
if str(webapp_backend) not in sys.path:
    sys.path.insert(0, str(webapp_backend))

# Import all models from webapp
try:
    from app.models import (
        # Core models
        Video,
        Transcript,
        VideoTravelerProfile,
        ExtractedEntity,
        CanonicalEntity,
        EntityExperience,
        Insight,
        InsightMention,
        InsightRelatedEntity,

        # Enums
        StageStatus,
        EntityType,
        Sentiment,
    )
except ImportError as e:
    raise ImportError(
        f"Failed to import models from webapp.backend.app.models: {e}\n"
        "Make sure the webapp/backend directory structure is intact."
    )

# Re-export all models
__all__ = [
    # Models
    'Video',
    'Transcript',
    'VideoTravelerProfile',
    'ExtractedEntity',
    'CanonicalEntity',
    'EntityExperience',
    'Insight',
    'InsightMention',
    'InsightRelatedEntity',

    # Enums
    'StageStatus',
    'EntityType',
    'Sentiment',
]
