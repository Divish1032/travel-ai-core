#!/usr/bin/env python3
"""
Initialize PostgreSQL database with pipeline tables.

Creates all tables for Stage 1-3 processing, insights, and metadata tracking.
Uses Alembic migrations to ensure proper schema versioning.

Usage:
    python cli/init_postgres.py
"""

import sys
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import click
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from alembic.config import Config
from alembic import command

from webapp.backend.app.database import Base, engine
from webapp.backend.app.models import *  # Import all models
from webapp.backend.app.config import settings


@click.command()
@click.option('--drop', is_flag=True, help='Drop all tables before creating (DANGEROUS!)')
@click.option('--use-alembic/--no-alembic', default=True, help='Use Alembic migrations (recommended)')
def main(drop: bool, use_alembic: bool):
    """
    Initialize PostgreSQL database for TravelAI pipeline.

    Creates all tables for:
    - Videos (metadata tracking)
    - Transcripts
    - Extracted entities (Stage 2)
    - Canonical entities (Stage 3)
    - Insights
    - Entity relationships

    By default, uses Alembic migrations for version control.
    """
    click.echo("\n" + "="*70)
    click.echo("  PostgreSQL Database Initialization")
    click.echo("="*70 + "\n")

    click.echo(f"Database: {settings.DATABASE_URL.split('@')[-1]}")  # Hide credentials

    if drop:
        click.echo("\n⚠️  WARNING: --drop flag detected!")
        click.echo("⚠️  This will DELETE ALL DATA in the database!")
        if not click.confirm("\nAre you sure you want to continue?", default=False):
            click.echo("\n❌ Aborted.\n")
            sys.exit(0)

        click.echo("\n🗑️  Dropping all tables...")
        Base.metadata.drop_all(bind=engine)
        click.echo("✅ All tables dropped\n")

    if use_alembic:
        # Use Alembic migrations
        click.echo("📦 Running Alembic migrations...\n")

        try:
            # Configure Alembic
            alembic_cfg = Config(str(Path(__file__).parent.parent / "webapp" / "backend" / "alembic.ini"))
            alembic_cfg.set_main_option("script_location", str(Path(__file__).parent.parent / "webapp" / "backend" / "alembic"))

            # Run migrations
            command.upgrade(alembic_cfg, "head")

            click.echo("\n✅ Alembic migrations complete!")

        except Exception as e:
            click.echo(f"\n❌ Alembic migration failed: {e}")
            click.echo("\nFalling back to direct table creation...")
            use_alembic = False

    if not use_alembic:
        # Direct table creation (not recommended for production)
        click.echo("📦 Creating tables directly (no version control)...\n")

        Base.metadata.create_all(bind=engine)

        click.echo("✅ Tables created!")

    # Verify tables were created
    click.echo("\n🔍 Verifying tables...")

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        result = session.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN (
                'videos',
                'transcripts',
                'video_traveler_profiles',
                'extracted_entities',
                'canonical_entities',
                'entity_experiences',
                'insights',
                'insight_mentions',
                'insight_related_entities'
            )
            ORDER BY table_name;
        """))

        tables = [row[0] for row in result]

        click.echo(f"\n✅ Found {len(tables)} pipeline tables:")
        for table in tables:
            click.echo(f"   ✓ {table}")

        expected_tables = {
            'videos',
            'transcripts',
            'video_traveler_profiles',
            'extracted_entities',
            'canonical_entities',
            'entity_experiences',
            'insights',
            'insight_mentions',
            'insight_related_entities'
        }

        if set(tables) == expected_tables:
            click.echo("\n🎉 Database initialized successfully!")
        else:
            missing = expected_tables - set(tables)
            if missing:
                click.echo(f"\n⚠️  Missing tables: {missing}")

    except Exception as e:
        click.echo(f"\n❌ Verification failed: {e}")
        sys.exit(1)

    finally:
        session.close()

    click.echo("\n" + "="*70)
    click.echo("Next steps:")
    click.echo("  1. Run migration script: python cli/migrate_s3_to_postgres.py")
    click.echo("  2. Test Stage 2: python cli/process_stage2.py --limit 1")
    click.echo("  3. Test Stage 3: python cli/process_stage3.py --limit 1")
    click.echo("="*70 + "\n")


if __name__ == "__main__":
    main()
