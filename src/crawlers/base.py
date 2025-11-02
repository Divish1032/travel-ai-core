"""
Base crawler class for all content crawlers.
Defines the interface and common error handling.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from loguru import logger


class CrawlerError(Exception):
    """Base exception for crawler errors."""
    pass


class FetchError(CrawlerError):
    """Raised when fetching content fails."""
    pass


class ParseError(CrawlerError):
    """Raised when parsing content fails."""
    pass


class SaveError(CrawlerError):
    """Raised when saving content fails."""
    pass


class BaseCrawler(ABC):
    """
    Abstract base class for all crawlers.

    All crawlers must implement fetch(), parse(), and save() methods.
    This ensures a consistent interface across different content sources.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the crawler with optional configuration.

        Args:
            config: Dictionary containing crawler-specific configuration
        """
        self.config = config or {}
        self.rate_limit = self.config.get('rate_limit', 2)
        self.max_retries = self.config.get('max_retries', 3)
        logger.info(f"Initialized {self.__class__.__name__} with config: {self.config}")

    @abstractmethod
    def fetch(self, url: str) -> Dict[str, Any]:
        """
        Fetch content from the given URL.

        Args:
            url: The URL to fetch content from

        Returns:
            Dictionary containing raw fetched data

        Raises:
            FetchError: If fetching fails after retries
        """
        pass

    @abstractmethod
    def parse(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse raw data into structured format.

        Args:
            raw_data: Raw data returned from fetch()

        Returns:
            Dictionary containing parsed, structured data

        Raises:
            ParseError: If parsing fails
        """
        pass

    @abstractmethod
    def save(self, parsed_data: Dict[str, Any], destination: str) -> bool:
        """
        Save parsed data to the specified destination.

        Args:
            parsed_data: Parsed data from parse()
            destination: Where to save the data (file path, S3 key, etc.)

        Returns:
            True if save was successful

        Raises:
            SaveError: If saving fails
        """
        pass

    def crawl(self, url: str, destination: str) -> bool:
        """
        Complete crawl workflow: fetch, parse, and save.

        Args:
            url: URL to crawl
            destination: Where to save the parsed data

        Returns:
            True if entire process succeeds

        Raises:
            CrawlerError: If any step fails
        """
        try:
            logger.info(f"Starting crawl for URL: {url}")

            # Fetch raw data
            raw_data = self.fetch(url)
            logger.debug(f"Fetched data for {url}")

            # Parse into structured format
            parsed_data = self.parse(raw_data)
            logger.debug(f"Parsed data for {url}")

            # Save to destination
            success = self.save(parsed_data, destination)

            if success:
                logger.info(f"Successfully crawled and saved: {url}")
            else:
                logger.warning(f"Crawl completed but save returned False: {url}")

            return success

        except FetchError as e:
            logger.error(f"Failed to fetch {url}: {e}")
            raise
        except ParseError as e:
            logger.error(f"Failed to parse data from {url}: {e}")
            raise
        except SaveError as e:
            logger.error(f"Failed to save data from {url}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during crawl of {url}: {e}")
            raise CrawlerError(f"Crawl failed: {e}") from e
