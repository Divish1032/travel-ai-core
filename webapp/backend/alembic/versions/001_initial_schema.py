"""Initial schema with User and TravelerProfile tables

Revision ID: 001
Revises:
Create Date: 2026-01-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create User and TravelerProfile tables."""

    # Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('firebase_uid', sa.String(128), nullable=False, unique=True, index=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('display_name', sa.String(255), nullable=True),
        sa.Column('photo_url', sa.String(512), nullable=True),
        sa.Column('preferences', postgresql.JSON, nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
    )

    # Create traveler_profiles table
    op.create_table(
        'traveler_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column('traveler_type', sa.String(50), nullable=False, server_default='solo'),
        sa.Column('budget_tier', sa.String(50), nullable=False, server_default='mid-range'),
        sa.Column('travel_style', postgresql.ARRAY(sa.String), nullable=False, server_default='{}'),
        sa.Column('interests', postgresql.ARRAY(sa.String), nullable=False, server_default='{}'),
        sa.Column('age_range', sa.String(20), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )

    # Note: Indexes are automatically created by unique=True and index=True parameters above


def downgrade() -> None:
    """Drop User and TravelerProfile tables."""
    op.drop_table('traveler_profiles')
    op.drop_table('users')
