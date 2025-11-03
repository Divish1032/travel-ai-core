"""
S3 storage manager for Travel AI project.

Handles all S3 operations including uploading JSONL files with structured paths,
downloading data, and managing file operations in AWS S3.

Path Structure:
    s3://bucket/raw/{source}/{data_type}/{YYYY-MM}/batch_{timestamp}.jsonl

    Example:
        s3://travel-ai-data/raw/youtube/videos/2024-11/batch_20241102_103045.jsonl

Usage:
    from src.storage.s3 import S3Storage

    # Initialize S3 storage
    storage = S3Storage()

    # Upload data
    videos = [video1.to_dict(), video2.to_dict()]
    s3_uri = storage.upload_jsonl(
        data=videos,
        source="youtube",
        data_type="videos"
    )
    print(f"Uploaded to: {s3_uri}")

    # Download data
    downloaded = storage.download_jsonl(s3_uri)

    # List files
    files = storage.list_files("raw/youtube/videos/")

    # Check if file exists
    exists = storage.file_exists(s3_uri)
"""
import json
# import io
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
# from pathlib import Path

import boto3
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError
from loguru import logger

from src.utils.config import config


class S3StorageError(Exception):
    """Base exception for S3 storage errors."""
    pass


class S3UploadError(S3StorageError):
    """Raised when S3 upload fails."""
    pass


class S3DownloadError(S3StorageError):
    """Raised when S3 download fails."""
    pass


class S3CredentialsError(S3StorageError):
    """Raised when AWS credentials are invalid or missing."""
    pass


class S3Storage:
    """
    Manages S3 operations for the Travel AI project.

    Provides methods to upload, download, and manage JSONL files in S3
    with automatic path structuring and error handling.
    """

    def __init__(self):
        """
        Initialize S3 storage client.

        Raises:
            S3CredentialsError: If AWS credentials are invalid or missing
        """
        try:
            self.bucket_name = config.S3_BUCKET_NAME
            self.region = config.AWS_REGION

            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=config.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
                region_name=self.region
            )

            # Verify credentials by checking if bucket is accessible
            try:
                self.s3_client.head_bucket(Bucket=self.bucket_name)
                logger.info(f"S3 storage initialized: bucket={self.bucket_name}, region={self.region}")
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == '404':
                    logger.warning(f"Bucket '{self.bucket_name}' does not exist. It will be created on first upload.")
                elif error_code == '403':
                    raise S3CredentialsError(
                        f"Access denied to bucket '{self.bucket_name}'. "
                        "Check your AWS credentials and permissions."
                    ) from e
                else:
                    raise S3CredentialsError(f"Error accessing S3 bucket: {e}") from e

        except (NoCredentialsError, PartialCredentialsError) as e:
            error_msg = (
                "AWS credentials not found or incomplete. "
                "Please ensure AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY "
                "are set in your .env file."
            )
            logger.error(error_msg)
            raise S3CredentialsError(error_msg) from e
        except Exception as e:
            logger.error(f"Failed to initialize S3 storage: {e}")
            raise S3StorageError(f"S3 initialization failed: {e}") from e

    def _generate_s3_path(self, source: str, data_type: str) -> str:
        """
        Generate S3 path with timestamp.

        Args:
            source: Data source (e.g., 'youtube')
            data_type: Type of data (e.g., 'videos', 'transcripts')

        Returns:
            S3 key path

        Example:
            raw/youtube/videos/2024-11/batch_20241102_103045.jsonl
        """
        now = datetime.now(timezone.utc)
        year_month = now.strftime("%Y-%m")
        timestamp = now.strftime("%Y%m%d_%H%M%S")

        path = f"raw/{source}/{data_type}/{year_month}/batch_{timestamp}.jsonl"
        return path

    def _generate_s3_uri(self, key: str) -> str:
        """
        Generate full S3 URI from bucket and key.

        Args:
            key: S3 object key

        Returns:
            Full S3 URI (s3://bucket/key)
        """
        return f"s3://{self.bucket_name}/{key}"

    def _parse_s3_uri(self, s3_uri: str) -> tuple[str, str]:
        """
        Parse S3 URI into bucket and key.

        Args:
            s3_uri: S3 URI (s3://bucket/key/path)

        Returns:
            Tuple of (bucket, key)

        Raises:
            ValueError: If URI format is invalid
        """
        if not s3_uri.startswith("s3://"):
            raise ValueError(f"Invalid S3 URI format: {s3_uri}. Expected s3://bucket/key")

        parts = s3_uri[5:].split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid S3 URI format: {s3_uri}. Expected s3://bucket/key")

        bucket, key = parts
        return bucket, key

    def _convert_to_jsonl(self, data: List[Dict[str, Any]]) -> str:
        """
        Convert list of dictionaries to JSONL format.

        Args:
            data: List of dictionaries

        Returns:
            JSONL formatted string (one JSON per line)
        """
        if not data:
            raise ValueError("Cannot convert empty data to JSONL")

        jsonl_lines = []
        for item in data:
            try:
                json_str = json.dumps(item, ensure_ascii=False)
                jsonl_lines.append(json_str)
            except (TypeError, ValueError) as e:
                logger.error(f"Failed to serialize item to JSON: {e}")
                raise ValueError(f"Invalid JSON data: {e}") from e

        return "\n".join(jsonl_lines)

    def _parse_jsonl(self, jsonl_content: str) -> List[Dict[str, Any]]:
        """
        Parse JSONL content to list of dictionaries.

        Args:
            jsonl_content: JSONL formatted string

        Returns:
            List of dictionaries
        """
        if not jsonl_content.strip():
            return []

        data = []
        for line_num, line in enumerate(jsonl_content.strip().split("\n"), 1):
            if not line.strip():
                continue

            try:
                item = json.loads(line)
                data.append(item)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse line {line_num}: {e}")
                continue

        return data

    def upload_jsonl(
        self,
        data: List[Dict[str, Any]],
        source: str,
        data_type: str,
        custom_path: Optional[str] = None
    ) -> str:
        """
        Upload data as JSONL file to S3.

        Args:
            data: List of dictionaries to upload
            source: Data source (e.g., 'youtube')
            data_type: Type of data (e.g., 'videos')
            custom_path: Optional custom S3 key path (overrides auto-generated path)

        Returns:
            S3 URI of uploaded file

        Raises:
            S3UploadError: If upload fails
            ValueError: If data is empty or invalid

        Example:
            >>> storage = S3Storage()
            >>> videos = [{"id": "1", "title": "Video 1"}]
            >>> uri = storage.upload_jsonl(videos, "youtube", "videos")
            >>> print(uri)
            s3://bucket/raw/youtube/videos/2024-11/batch_20241102_103045.jsonl
        """
        if not data:
            raise ValueError("Cannot upload empty data")

        try:
            # Convert to JSONL
            jsonl_content = self._convert_to_jsonl(data)

            # Generate path
            s3_key = custom_path if custom_path else self._generate_s3_path(source, data_type)
            s3_uri = self._generate_s3_uri(s3_key)

            logger.info(f"Uploading {len(data)} items to {s3_uri}")

            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=jsonl_content.encode('utf-8'),
                ContentType='application/x-ndjson',
                Metadata={
                    'source': source,
                    'data_type': data_type,
                    'item_count': str(len(data)),
                    'uploaded_at': datetime.now(timezone.utc).isoformat()
                }
            )

            logger.info(f"Successfully uploaded {len(data)} items to {s3_uri}")
            return s3_uri

        except ClientError as e:
            error_msg = f"Failed to upload to S3: {e}"
            logger.error(error_msg)
            raise S3UploadError(error_msg) from e
        except Exception as e:
            error_msg = f"Unexpected error during upload: {e}"
            logger.error(error_msg)
            raise S3UploadError(error_msg) from e

    def download_jsonl(self, s3_uri: str) -> List[Dict[str, Any]]:
        """
        Download JSONL file from S3 and parse to list of dictionaries.

        Args:
            s3_uri: Full S3 URI (s3://bucket/key/path)

        Returns:
            List of dictionaries from JSONL file

        Raises:
            S3DownloadError: If download fails
            ValueError: If URI format is invalid

        Example:
            >>> storage = S3Storage()
            >>> data = storage.download_jsonl("s3://bucket/raw/youtube/videos/file.jsonl")
            >>> print(len(data))
            100
        """
        try:
            bucket, key = self._parse_s3_uri(s3_uri)

            logger.info(f"Downloading from {s3_uri}")

            # Download from S3
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            content = response['Body'].read().decode('utf-8')

            # Parse JSONL
            data = self._parse_jsonl(content)

            logger.info(f"Successfully downloaded {len(data)} items from {s3_uri}")
            return data

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                error_msg = f"File not found: {s3_uri}"
            else:
                error_msg = f"Failed to download from S3: {e}"
            logger.error(error_msg)
            raise S3DownloadError(error_msg) from e
        except Exception as e:
            error_msg = f"Unexpected error during download: {e}"
            logger.error(error_msg)
            raise S3DownloadError(error_msg) from e

    def list_files(self, prefix: str, max_keys: int = 1000) -> List[str]:
        """
        List all files under a given S3 prefix.

        Args:
            prefix: S3 key prefix to search under
            max_keys: Maximum number of keys to return (default: 1000)

        Returns:
            List of S3 URIs

        Example:
            >>> storage = S3Storage()
            >>> files = storage.list_files("raw/youtube/videos/2024-11/")
            >>> for file in files:
            ...     print(file)
            s3://bucket/raw/youtube/videos/2024-11/batch_001.jsonl
            s3://bucket/raw/youtube/videos/2024-11/batch_002.jsonl
        """
        try:
            logger.debug(f"Listing files with prefix: {prefix}")

            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=max_keys
            )

            files = []
            if 'Contents' in response:
                for obj in response['Contents']:
                    s3_uri = self._generate_s3_uri(obj['Key'])
                    files.append(s3_uri)

            logger.info(f"Found {len(files)} files with prefix '{prefix}'")
            return files

        except ClientError as e:
            logger.error(f"Failed to list files: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error listing files: {e}")
            return []

    def file_exists(self, s3_uri: str) -> bool:
        """
        Check if a file exists in S3.

        Args:
            s3_uri: Full S3 URI (s3://bucket/key/path)

        Returns:
            True if file exists, False otherwise

        Example:
            >>> storage = S3Storage()
            >>> exists = storage.file_exists("s3://bucket/raw/youtube/videos/file.jsonl")
            >>> if exists:
            ...     print("File found!")
        """
        try:
            bucket, key = self._parse_s3_uri(s3_uri)

            self.s3_client.head_object(Bucket=bucket, Key=key)
            logger.debug(f"File exists: {s3_uri}")
            return True

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                logger.debug(f"File does not exist: {s3_uri}")
                return False
            else:
                logger.warning(f"Error checking file existence: {e}")
                return False
        except Exception as e:
            logger.warning(f"Unexpected error checking file existence: {e}")
            return False

    def delete_file(self, s3_uri: str) -> bool:
        """
        Delete a file from S3.

        Args:
            s3_uri: Full S3 URI (s3://bucket/key/path)

        Returns:
            True if deletion was successful, False otherwise

        Example:
            >>> storage = S3Storage()
            >>> success = storage.delete_file("s3://bucket/raw/youtube/videos/old_file.jsonl")
        """
        try:
            bucket, key = self._parse_s3_uri(s3_uri)

            logger.info(f"Deleting file: {s3_uri}")
            self.s3_client.delete_object(Bucket=bucket, Key=key)
            logger.info(f"Successfully deleted: {s3_uri}")
            return True

        except ClientError as e:
            logger.error(f"Failed to delete file: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting file: {e}")
            return False

    def get_file_metadata(self, s3_uri: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a file in S3.

        Args:
            s3_uri: Full S3 URI (s3://bucket/key/path)

        Returns:
            Dictionary of metadata or None if file doesn't exist

        Example:
            >>> storage = S3Storage()
            >>> metadata = storage.get_file_metadata("s3://bucket/raw/youtube/videos/file.jsonl")
            >>> print(metadata['item_count'])
            100
        """
        try:
            bucket, key = self._parse_s3_uri(s3_uri)

            response = self.s3_client.head_object(Bucket=bucket, Key=key)

            metadata = {
                'size_bytes': response.get('ContentLength', 0),
                'last_modified': response.get('LastModified'),
                'content_type': response.get('ContentType'),
                'custom_metadata': response.get('Metadata', {})
            }

            logger.debug(f"Retrieved metadata for {s3_uri}")
            return metadata

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                logger.debug(f"File not found: {s3_uri}")
                return None
            else:
                logger.error(f"Error retrieving metadata: {e}")
                return None
        except Exception as e:
            logger.error(f"Unexpected error retrieving metadata: {e}")
            return None


# Example usage and testing
if __name__ == "__main__":
    print("=" * 70)
    print("S3 STORAGE EXAMPLE USAGE")
    print("=" * 70)

    try:
        # Initialize storage
        print("\n1. Initializing S3 storage...")
        storage = S3Storage()
        print(f"✓ Connected to bucket: {storage.bucket_name}")

        # Prepare sample data
        print("\n2. Preparing sample data...")
        sample_videos = [
            {
                "source_id": "abc123",
                "title": "Best of Boracay 2024",
                "author": "TravelVlogger",
                "duration_seconds": 847,
                "fetched_at": datetime.now(timezone.utc).isoformat()
            },
            {
                "source_id": "xyz789",
                "title": "Palawan Travel Guide",
                "author": "AdventureSeeker",
                "duration_seconds": 623,
                "fetched_at": datetime.now(timezone.utc).isoformat()
            }
        ]
        print(f"✓ Prepared {len(sample_videos)} sample videos")

        # Upload to S3
        print("\n3. Uploading to S3...")
        s3_uri = storage.upload_jsonl(
            data=sample_videos,
            source="youtube",
            data_type="videos"
        )
        print(f"✓ Uploaded to: {s3_uri}")

        # Check if file exists
        print("\n4. Checking if file exists...")
        exists = storage.file_exists(s3_uri)
        print(f"✓ File exists: {exists}")

        # Get file metadata
        print("\n5. Getting file metadata...")
        metadata = storage.get_file_metadata(s3_uri)
        if metadata:
            print(f"✓ File size: {metadata['size_bytes']} bytes")
            print(f"✓ Content type: {metadata['content_type']}")
            print(f"✓ Custom metadata: {metadata['custom_metadata']}")

        # Download from S3
        print("\n6. Downloading from S3...")
        downloaded_data = storage.download_jsonl(s3_uri)
        print(f"✓ Downloaded {len(downloaded_data)} items")

        # List files
        print("\n7. Listing files...")
        files = storage.list_files("raw/youtube/videos/")
        print(f"✓ Found {len(files)} files")
        for file in files[:3]:  # Show first 3
            print(f"  - {file}")

        print("\n" + "=" * 70)
        print("All S3 operations completed successfully!")
        print("=" * 70)

    except S3CredentialsError as e:
        print(f"\n✗ Credentials Error: {e}")
        print("\nPlease ensure your .env file has valid AWS credentials:")
        print("  AWS_ACCESS_KEY_ID=your_key")
        print("  AWS_SECRET_ACCESS_KEY=your_secret")
        print("  AWS_REGION=us-east-1")
        print("  S3_BUCKET_NAME=your-bucket")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
