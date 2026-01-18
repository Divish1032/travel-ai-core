"""
Configuration management for Travel AI project.

Loads and validates environment variables using Pydantic Settings.
Provides type-safe access to configuration values throughout the application.

Usage:
    from src.utils.config import config

    # Access configuration values
    print(config.AWS_REGION)
    print(config.S3_BUCKET_NAME)
    print(config.LOG_LEVEL)

    # Configuration is validated on import
    # Missing required variables will raise clear errors
"""
from typing import Optional
from pathlib import Path
from pydantic import Field, field_validator, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from loguru import logger


class Config(BaseSettings):
    """
    Application configuration loaded from environment variables.

    Required environment variables:
        - AWS_ACCESS_KEY_ID: AWS access key for S3
        - AWS_SECRET_ACCESS_KEY: AWS secret key for S3
        - AWS_REGION: AWS region (e.g., us-east-1)
        - S3_BUCKET_NAME: S3 bucket name for storing data

    Optional environment variables (with defaults):
        - YOUTUBE_API_KEY: YouTube Data API v3 key (optional, for metadata)
        - LOG_LEVEL: Logging level (default: INFO)
        - CRAWLER_RATE_LIMIT: Seconds between requests (default: 2)
        - MAX_RETRIES: Maximum retry attempts (default: 3)
    """

    # Required AWS Configuration
    AWS_ACCESS_KEY_ID: str = Field(
        ...,
        description="AWS access key ID for S3 access"
    )
    AWS_SECRET_ACCESS_KEY: str = Field(
        ...,
        description="AWS secret access key for S3 access"
    )
    AWS_REGION: str = Field(
        ...,
        description="AWS region for S3 bucket (e.g., us-east-1)"
    )
    S3_BUCKET_NAME: str = Field(
        ...,
        description="S3 bucket name for storing crawled data"
    )

    # YouTube API Configuration
    YOUTUBE_API_KEY: Optional[str] = Field(
        default=None,
        description="YouTube Data API v3 key for fetching video metadata (get from Google Cloud Console)"
    )

    # LLM Provider Configuration (Required for Stage 2)
    LLM_PROVIDER: str = Field(
        default="gemini",
        description="LLM provider for entity extraction (openai, deepseek, or gemini)"
    )

    # OpenAI API Configuration
    OPENAI_API_KEY: Optional[str] = Field(
        default=None,
        description="OpenAI API key for entity extraction (get from platform.openai.com)"
    )

    # DeepSeek API Configuration
    DEEPSEEK_API_KEY: Optional[str] = Field(
        default=None,
        description="DeepSeek API key for entity extraction (get from platform.deepseek.com)"
    )
    DEEPSEEK_MODEL: str = Field(
        default="deepseek-chat",
        description="DeepSeek model to use (deepseek-chat or deepseek-reasoner)"
    )

    # Google Gemini API Configuration
    GEMINI_API_KEY: Optional[str] = Field(
        default=None,
        description="Google Gemini API key for entity extraction (get from aistudio.google.com)"
    )
    GEMINI_MODEL: str = Field(
        default="gemini-2.5-flash-lite",
        description="Gemini model to use (gemini-2.5-flash-lite or gemini-1.5-pro)"
    )

    # Optional Application Configuration
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    CRAWLER_RATE_LIMIT: int = Field(
        default=2,
        description="Seconds to wait between crawler requests",
        ge=1
    )
    MAX_RETRIES: int = Field(
        default=3,
        description="Maximum number of retry attempts for failed operations",
        ge=0
    )

    # Pydantic Settings Configuration
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent.parent / ".env"),  # Look for .env in project root
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"  # Ignore extra environment variables
    )

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate that LOG_LEVEL is a valid logging level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(
                f"LOG_LEVEL must be one of {valid_levels}, got '{v}'"
            )
        return v_upper

    @field_validator("AWS_REGION")
    @classmethod
    def validate_aws_region(cls, v: str) -> str:
        """Validate AWS region format."""
        if not v or len(v) < 3:
            raise ValueError(
                f"AWS_REGION appears invalid: '{v}'. "
                "Expected format like 'us-east-1'"
            )
        return v

    @field_validator("S3_BUCKET_NAME")
    @classmethod
    def validate_s3_bucket_name(cls, v: str) -> str:
        """Validate S3 bucket name follows AWS naming rules."""
        if not v:
            raise ValueError("S3_BUCKET_NAME cannot be empty")
        if len(v) < 3 or len(v) > 63:
            raise ValueError(
                f"S3_BUCKET_NAME must be between 3 and 63 characters, got {len(v)}"
            )
        # Basic validation - no uppercase, no underscores
        if v != v.lower():
            raise ValueError(
                "S3_BUCKET_NAME must be lowercase"
            )
        if "_" in v:
            raise ValueError(
                "S3_BUCKET_NAME cannot contain underscores"
            )
        return v

    def get_project_root(self) -> Path:
        """Get the project root directory."""
        return Path(__file__).parent.parent.parent

    def get_data_dir(self, subdir: Optional[str] = None) -> Path:
        """
        Get the data directory path.

        Args:
            subdir: Optional subdirectory (e.g., 'raw', 'processed', 'cache')

        Returns:
            Path to the data directory or subdirectory
        """
        data_dir = self.get_project_root() / "data"
        if subdir:
            return data_dir / subdir
        return data_dir

    def get_logs_dir(self) -> Path:
        """Get the logs directory path."""
        return self.get_project_root() / "logs"

    def model_post_init(self, __context) -> None:
        """Log configuration after initialization (without exposing secrets)."""
        logger.debug("Configuration loaded successfully")
        logger.debug(f"AWS Region: {self.AWS_REGION}")
        logger.debug(f"S3 Bucket: {self.S3_BUCKET_NAME}")
        logger.debug(f"YouTube API Key: {'Set' if self.YOUTUBE_API_KEY else 'Not set (will use fallback)'}")
        logger.debug(f"Log Level: {self.LOG_LEVEL}")
        logger.debug(f"Crawler Rate Limit: {self.CRAWLER_RATE_LIMIT}s")
        logger.debug(f"Max Retries: {self.MAX_RETRIES}")


# Singleton instance
_config: Optional[Config] = None


def get_config() -> Config:
    """
    Get the singleton configuration instance.

    Returns:
        Config: The application configuration

    Raises:
        ValidationError: If required environment variables are missing
            or validation fails
        FileNotFoundError: If .env file is not found (with helpful message)
    """
    global _config

    if _config is None:
        try:
            _config = Config()
        except ValidationError as e:
            # Provide helpful error message
            error_msg = "\n❌ Configuration Error: Missing or invalid environment variables\n\n"
            error_msg += "Please ensure you have:\n"
            error_msg += "1. Copied .env.example to .env\n"
            error_msg += "2. Filled in all required values in .env\n\n"
            error_msg += "Validation errors:\n"

            for error in e.errors():
                field = error['loc'][0] if error['loc'] else 'unknown'
                msg = error['msg']
                error_msg += f"  - {field}: {msg}\n"

            logger.error(error_msg)
            raise ValueError(error_msg) from e

    return _config


# Create singleton instance on module import
# This will fail fast if configuration is invalid
try:
    config = get_config()
except Exception as e:
    # Allow import to succeed even if .env doesn't exist
    # This is useful for testing and initial setup
    logger.warning(
        "Failed to load configuration. "
        "Please ensure .env file exists with required variables."
    )
    logger.debug(f"Configuration error: {e}")
    # Create a placeholder - will fail on actual use
    config = None  # type: ignore
