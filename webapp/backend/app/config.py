"""
Application configuration using Pydantic Settings.

This module manages all environment variables and application settings.
Settings are loaded from environment variables or .env file.
"""

import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

# Path to backend directory's .env file
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE_PATH = os.path.join(BACKEND_DIR, '.env')


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Application settings
    APP_NAME: str = "TravelAI Backend"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"
    API_V1_PREFIX: str = "/api"

    # Database
    DATABASE_URL: str

    # Firebase
    FIREBASE_CREDENTIALS_PATH: str

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # CORS (comma-separated origins)
    CORS_ORIGINS: str = "http://localhost:3000"

    # Security
    SECRET_KEY: str

    # TravelAI specific (existing from main project)
    CHROMADB_PATH: str = ""  # Optional - only needed for local ChromaDB
    OPENAI_API_KEY: str = ""
    GOOGLE_GENAI_API_KEY: str = ""

    # AWS (optional, for file uploads)
    AWS_S3_BUCKET: str = ""

    # Rate limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS_ORIGINS string into list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]


# Global settings instance
settings = Settings()
