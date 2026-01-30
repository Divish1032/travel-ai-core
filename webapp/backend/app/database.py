"""
Database configuration and session management.

This module sets up SQLAlchemy engine, sessionmaker, and base class for models.
It provides the database session dependency for FastAPI routes.
"""

from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from app.config import settings

# Create SQLAlchemy engine
# pool_pre_ping=True ensures connections are alive before using them
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=settings.DEBUG,  # Log SQL queries in debug mode
)

# Create SessionLocal class for database sessions
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base class for all ORM models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency function to get database session.

    Yields:
        Session: SQLAlchemy database session

    Usage:
        @app.get("/users")
        def get_users(db: Session = Depends(get_db)):
            return db.query(User).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """
    Create all tables in the database.

    Note: In production, use Alembic migrations instead.
    This is useful for testing or initial setup.
    """
    Base.metadata.create_all(bind=engine)


def drop_tables():
    """
    Drop all tables from the database.

    WARNING: This will delete all data. Use with caution!
    Only use in development/testing.
    """
    Base.metadata.drop_all(bind=engine)
