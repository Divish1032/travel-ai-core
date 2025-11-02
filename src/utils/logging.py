"""
Logging configuration for Travel AI project using Loguru.

Sets up structured logging to both console and rotating log files with
different outputs for general logs, errors, and crawler-specific activity.

Usage:
    from src.utils.logging import setup_logging, get_logger

    # Initialize logging (call once at app startup)
    setup_logging()

    # Get logger for your module
    logger = get_logger(__name__)

    # Use logger
    logger.info("Processing video")
    logger.error("Failed to fetch", error=str(e))

    # Log crawler statistics
    from src.utils.logging import log_crawler_stats
    log_crawler_stats(total=100, success=95, failed=3, skipped=2)
"""
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from loguru import logger
from rich.console import Console


# Rich console for beautiful output
console = Console()

# Track if logging has been initialized
_initialized = False


def setup_logging(log_level: Optional[str] = None) -> None:
    """
    Initialize logging configuration for the entire application.

    Sets up multiple log outputs:
    - Console: Colored, formatted output for human readability
    - app_*.log: General application logs (all levels)
    - errors_*.log: Error-level logs only
    - crawler_*.log: Crawler-specific logs

    Args:
        log_level: Optional log level override. If not provided, uses config.LOG_LEVEL

    Example:
        >>> setup_logging()
        >>> logger.info("Application started")
    """
    global _initialized

    if _initialized:
        logger.debug("Logging already initialized, skipping setup")
        return

    # Remove default handler
    logger.remove()

    # Determine log level
    if log_level is None:
        try:
            from src.utils.config import config
            log_level = config.LOG_LEVEL if config else "INFO"
        except Exception:
            log_level = "INFO"

    # Ensure logs directory exists
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    # Current date for log file naming
    today = datetime.now().strftime("%Y-%m-%d")

    # Console Handler - Colored and formatted for readability
    logger.add(
        sys.stdout,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<level>{message}</level>"
        ),
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # General Application Log - All logs
    logger.add(
        logs_dir / f"app_{today}.log",
        level=log_level,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}"
        ),
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        backtrace=True,
        diagnose=True,
        enqueue=True,  # Thread-safe
    )

    # Error Log - Errors only
    logger.add(
        logs_dir / f"errors_{today}.log",
        level="ERROR",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}\n"
            "{exception}"
        ),
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        backtrace=True,
        diagnose=True,
        enqueue=True,
    )

    # Crawler Log - Crawler-specific logs
    logger.add(
        logs_dir / f"crawler_{today}.log",
        level=log_level,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}"
        ),
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        filter=lambda record: "crawler" in record["name"].lower(),
        backtrace=True,
        diagnose=True,
        enqueue=True,
    )

    _initialized = True
    logger.info(f"Logging initialized at {log_level} level")
    logger.debug(f"Log files location: {logs_dir.absolute()}")


def get_logger(name: str):
    """
    Get a logger instance for a specific module.

    Args:
        name: The module name (typically __name__)

    Returns:
        loguru.Logger: Configured logger instance

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Module initialized")
    """
    # Ensure logging is set up
    if not _initialized:
        setup_logging()

    # Loguru uses a single logger instance, but we bind the name for context
    return logger.bind(name=name)


def log_crawler_stats(
    total: int,
    success: int,
    failed: int,
    skipped: int = 0,
    duration_seconds: Optional[float] = None
) -> None:
    """
    Log crawler statistics in a formatted summary.

    Args:
        total: Total number of items processed
        success: Number of successful operations
        failed: Number of failed operations
        skipped: Number of skipped items (default: 0)
        duration_seconds: Optional duration in seconds

    Example:
        >>> log_crawler_stats(
        ...     total=100,
        ...     success=95,
        ...     failed=3,
        ...     skipped=2,
        ...     duration_seconds=120.5
        ... )
    """
    success_rate = (success / total * 100) if total > 0 else 0

    stats_msg = "\n" + "=" * 60 + "\n"
    stats_msg += "CRAWLER STATISTICS\n"
    stats_msg += "=" * 60 + "\n"
    stats_msg += f"Total Processed:  {total}\n"
    stats_msg += f"Successful:       {success} ({success_rate:.1f}%)\n"
    stats_msg += f"Failed:           {failed}\n"

    if skipped > 0:
        stats_msg += f"Skipped:          {skipped}\n"

    if duration_seconds is not None:
        mins, secs = divmod(duration_seconds, 60)
        stats_msg += f"Duration:         {int(mins)}m {secs:.1f}s\n"

        if duration_seconds > 0 and total > 0:
            rate = total / duration_seconds
            stats_msg += f"Rate:             {rate:.2f} items/second\n"

    stats_msg += "=" * 60

    if failed > 0:
        logger.warning(stats_msg)
    else:
        logger.info(stats_msg)


def log_function_call(func_name: str, **kwargs) -> None:
    """
    Log a function call with its parameters.

    Args:
        func_name: Name of the function being called
        **kwargs: Function parameters to log

    Example:
        >>> log_function_call("fetch_video", video_id="abc123", quality="720p")
    """
    params = ", ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.debug(f"Calling {func_name}({params})")


def log_api_request(method: str, url: str, status_code: Optional[int] = None) -> None:
    """
    Log an API request with method, URL, and optional status code.

    Args:
        method: HTTP method (GET, POST, etc.)
        url: The URL being requested
        status_code: Optional HTTP status code of the response

    Example:
        >>> log_api_request("GET", "https://youtube.com/watch?v=abc", 200)
    """
    if status_code:
        logger.info(f"{method} {url} -> {status_code}")
    else:
        logger.debug(f"{method} {url}")


def log_data_operation(
    operation: str,
    path: str,
    size_bytes: Optional[int] = None,
    success: bool = True
) -> None:
    """
    Log a data operation (save, load, delete, etc.).

    Args:
        operation: Type of operation (save, load, delete, etc.)
        path: File path or S3 key
        size_bytes: Optional size of data in bytes
        success: Whether operation succeeded

    Example:
        >>> log_data_operation("save", "s3://bucket/data.json", 1024, True)
    """
    if size_bytes:
        size_mb = size_bytes / (1024 * 1024)
        msg = f"{operation.upper()} {path} ({size_mb:.2f} MB)"
    else:
        msg = f"{operation.upper()} {path}"

    if success:
        logger.info(msg)
    else:
        logger.error(f"Failed to {msg}")


def log_exception(exc: Exception, context: str = "") -> None:
    """
    Log an exception with full traceback.

    Args:
        exc: The exception to log
        context: Optional context about where the exception occurred

    Example:
        >>> try:
        ...     risky_operation()
        ... except Exception as e:
        ...     log_exception(e, "During video processing")
    """
    if context:
        logger.exception(f"{context}: {exc}")
    else:
        logger.exception(f"Exception occurred: {exc}")


# Example usage and testing
if __name__ == "__main__":
    # Initialize logging
    setup_logging("DEBUG")

    # Test different log levels
    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")

    # Test crawler stats
    log_crawler_stats(
        total=100,
        success=95,
        failed=3,
        skipped=2,
        duration_seconds=120.5
    )

    # Test function call logging
    log_function_call("fetch_video", video_id="abc123", quality="720p")

    # Test API request logging
    log_api_request("GET", "https://youtube.com/watch?v=abc123", 200)

    # Test data operation logging
    log_data_operation("save", "data/raw/video_abc123.json", 2048, True)

    # Test exception logging
    try:
        raise ValueError("Test exception")
    except Exception as e:
        log_exception(e, "During testing")

    print("\nCheck the logs/ directory for output files!")
