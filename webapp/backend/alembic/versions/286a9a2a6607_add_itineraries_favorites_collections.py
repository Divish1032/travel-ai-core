"""add_itineraries_favorites_collections

Revision ID: 286a9a2a6607
Revises: 001
Create Date: 2026-01-30 23:51:53.142182

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '286a9a2a6607'
down_revision: Union[str, Sequence[str], None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create saved_itineraries, favorites, and collections tables."""

    # Create saved_itineraries table
    op.create_table(
        'saved_itineraries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('title', sa.String(255), nullable=True),
        sa.Column('destination', sa.String(255), nullable=False, index=True),
        sa.Column('duration_days', sa.Integer, nullable=False),
        sa.Column('itinerary_data', postgresql.JSON, nullable=False),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('is_public', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('share_token', sa.String(64), nullable=True, unique=True, index=True),
        sa.Column('share_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), index=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )

    # Create favorites table
    op.create_table(
        'favorites',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('entity_id', sa.String(255), nullable=False, index=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('saved_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), index=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'entity_id', name='uq_user_entity_favorite'),
    )

    # Create collections table
    op.create_table(
        'collections',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('entity_ids', postgresql.ARRAY(sa.String), nullable=False, server_default='{}'),
        sa.Column('is_public', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), index=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )


def downgrade() -> None:
    """Drop saved_itineraries, favorites, and collections tables."""
    op.drop_table('collections')
    op.drop_table('favorites')
    op.drop_table('saved_itineraries')
