"""
Database connection and session management for TravelAI core project.

This module is independent of the webapp backend and uses the core
project's configuration system.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from typing import Generator
import sys
from pathlib import Path

from src.utils.config import config
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Get database URL from core config
DATABASE_URL = config.DATABASE_URL if config else None

if not DATABASE_URL:
    error_msg = (
        "\n❌ DATABASE_URL not configured\n\n"
        "PostgreSQL database URL is required for CLI tools.\n"
        "Please add it to your .env file:\n\n"
        "DATABASE_URL=postgresql://user:password@localhost:5432/travelai\n\n"
        "Example:\n"
        "DATABASE_URL=postgresql://travelai:password@localhost:5432/travelai\n"
    )
    logger.error(error_msg)
    print(error_msg, file=sys.stderr)
    sys.exit(1)

# Create SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=5,
    max_overflow=10
)

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Import Base from webapp to ensure models are registered with the same Base
# Add webapp backend to path
webapp_backend = Path(__file__).parent.parent.parent / "webapp" / "backend"
if str(webapp_backend) not in sys.path:
    sys.path.insert(0, str(webapp_backend))

from app.database import Base


def get_db() -> Generator:
    """
    Dependency function to get database session.

    Usage in CLI scripts:
        db = next(get_db())
        try:
            # Use db
            ...
        finally:
            db.close()

    Or simply:
        db = SessionLocal()
        try:
            # Use db
        finally:
            db.close()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_connection() -> bool:
    """
    Verify database connection is working.

    Returns:
        True if connection successful, False otherwise
    """
    try:
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        logger.info("Database connection verified")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False
