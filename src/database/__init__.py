"""
Core database module for TravelAI CLI tools.

This module provides standalone database access for CLI scripts,
independent of the webapp backend structure.
"""

from src.database.connection import (
    SessionLocal,
    engine,
    Base,
    get_db
)

__all__ = [
    'SessionLocal',
    'engine',
    'Base',
    'get_db'
]
