# Testing Guide

Comprehensive guide to testing TravelAI.

---

## Test Structure

```
tests/
├── unit/                    # Unit tests for individual functions
│   ├── test_stage1.py
│   ├── test_stage2.py
│   ├── test_stage3.py
│   ├── test_stage4.py
│   └── test_rag.py
├── integration/             # Integration tests for pipelines
│   ├── test_pipeline.py
│   ├── test_s3_storage.py
│   └── test_chromadb.py
└── fixtures/                # Test data
    ├── sample_transcripts/
    ├── sample_entities/
    └── sample_canonical/
```

---

## Running Tests

### All Tests

```bash
# Run all tests
pytest

# With verbose output
pytest -v

# With coverage report
pytest --cov=src --cov-report=html

# View coverage
open htmlcov/index.html
```

### Specific Tests

```bash
# Run specific file
pytest tests/unit/test_stage2.py

# Run specific test
pytest tests/unit/test_stage2.py::test_semantic_chunking

# Run by pattern
pytest -k "test_stage2"
```

---

## Unit Tests

### Stage 1: Crawling

**Test file:** `tests/unit/test_stage1.py`

```python
import pytest
from src.crawlers.youtube import extract_video_id, transcribe_audio

def test_extract_video_id():
    """Test video ID extraction from various URL formats."""
    urls = [
        ("https://youtube.com/watch?v=abc123", "abc123"),
        ("https://youtu.be/abc123", "abc123"),
        ("https://m.youtube.com/watch?v=abc123", "abc123"),
    ]

    for url, expected in urls:
        assert extract_video_id(url) == expected

def test_extract_video_id_invalid():
    """Test invalid URL handling."""
    with pytest.raises(ValueError):
        extract_video_id("https://invalid-url.com")
```

### Stage 2: Entity Extraction

**Test file:** `tests/unit/test_stage2.py`

```python
from src.processors.stage2_extractor import (
    split_transcript_semantically,
    merge_duplicate_entities,
    are_entities_similar
)

def test_semantic_chunking():
    """Test semantic chunking splits on topic shifts."""
    transcript = [
        {"text": "Today we're in Bangkok", "start": 0.0, "duration": 5.0},
        {"text": "It's amazing here", "start": 5.0, "duration": 3.0},
        {"text": "Day 2, we went to Phuket", "start": 300.0, "duration": 5.0}
    ]

    chunks = split_transcript_semantically(transcript)

    assert len(chunks) == 2  # Split at "Day 2" marker
    assert len(chunks[0]) == 2  # First chunk has 2 segments
    assert len(chunks[1]) == 1  # Second chunk has 1 segment

def test_fuzzy_deduplication():
    """Test fuzzy matching merges similar entities."""
    from src.utils.schemas import EntityExperience

    entities = [
        EntityExperience(
            entity_name="Grand Palace",
            entity_type="attraction",
            sentiment="positive"
        ),
        EntityExperience(
            entity_name="The Grand Palace",
            entity_type="attraction",
            sentiment="positive"
        )
    ]

    merged = merge_duplicate_entities(entities, use_fuzzy=True)

    assert len(merged) == 1  # Should merge into one
    assert merged[0].entity_name in ["Grand Palace", "The Grand Palace"]
```

### Stage 3: Canonicalization

**Test file:** `tests/unit/test_stage3.py`

```python
from src.processors.deduplication import exact_match, fuzzy_match

def test_exact_match():
    """Test exact matching logic."""
    entity1 = {
        'normalized_name': 'wat pho',
        'normalized_location': 'bangkok',
        'entity': {'entity_type': 'attraction'}
    }
    entity2 = {
        'normalized_name': 'wat pho',
        'normalized_location': 'bangkok',
        'entity': {'entity_type': 'attraction'}
    }

    assert exact_match(entity1, entity2) == True

def test_fuzzy_match_similar():
    """Test fuzzy matching for similar entities."""
    entity1 = {
        'normalized_name': 'grand palace',
        'normalized_location': 'bangkok',
        'entity': {'entity_type': 'attraction'}
    }
    entity2 = {
        'normalized_name': 'the grand palace',
        'normalized_location': 'bangkok',
        'entity': {'entity_type': 'attraction'}
    }

    similarity = fuzzy_match(entity1, entity2)

    assert similarity >= 0.90  # Should be high similarity
```

---

## Integration Tests

### Full Pipeline Test

**Test file:** `tests/integration/test_pipeline.py`

```python
import pytest
from src.crawlers.youtube import YouTubeCrawler
from src.processors.stage2_extractor import extract_entities_from_video
from src.storage.s3 import S3Storage

@pytest.mark.integration
def test_stage1_to_stage2_pipeline():
    """Test data flows correctly from Stage 1 to Stage 2."""
    storage = S3Storage()

    # Stage 1: Crawl video (use test video)
    crawler = YouTubeCrawler(storage)
    result = crawler.crawl("https://youtube.com/watch?v=test123")

    assert result is not None
    assert len(result.transcript) > 0

    # Stage 2: Extract entities
    stage2_result = extract_entities_from_video(
        video_id=result.video_id,
        storage=storage
    )

    assert len(stage2_result.entities) > 0
    assert stage2_result.traveler_profile is not None
```

### S3 Storage Test

**Test file:** `tests/integration/test_s3_storage.py`

```python
import pytest
from src.storage.s3 import S3Storage

@pytest.mark.integration
def test_s3_upload_download():
    """Test S3 upload and download cycle."""
    storage = S3Storage()

    test_data = {"test": "data", "number": 123}
    s3_key = "test/test_file.json"

    # Upload
    storage.upload_json(test_data, s3_key)

    # Download
    downloaded = storage.download_json(s3_key)

    assert downloaded == test_data

    # Cleanup
    storage.delete_file(s3_key)
```

---

## Mock Tests

### Mocking LLM Calls

```python
from unittest.mock import Mock, patch
from src.llm.factory import LLMFactory

def test_entity_extraction_with_mock_llm():
    """Test entity extraction with mocked LLM."""
    mock_response = {
        "entities": [
            {
                "entity_name": "Grand Palace",
                "entity_type": "attraction",
                "sentiment": "positive"
            }
        ],
        "traveler_profile": {
            "touristiness": 7,
            "budget_level": 5
        }
    }

    with patch.object(LLMFactory, 'create') as mock_llm:
        mock_llm.return_value.generate.return_value.text = json.dumps(mock_response)

        result = extract_entities_from_video("test_video")

        assert len(result.entities) == 1
        assert result.entities[0].entity_name == "Grand Palace"
```

---

## Fixtures

### Sample Data Fixtures

**Test file:** `tests/fixtures/conftest.py`

```python
import pytest

@pytest.fixture
def sample_transcript():
    """Provide sample transcript for testing."""
    return [
        {
            "text": "Today we're exploring Bangkok",
            "start": 0.0,
            "duration": 5.0
        },
        {
            "text": "The Grand Palace is amazing",
            "start": 5.0,
            "duration": 4.0
        }
    ]

@pytest.fixture
def sample_entities():
    """Provide sample entities for testing."""
    from src.utils.schemas import EntityExperience

    return [
        EntityExperience(
            entity_name="Grand Palace",
            entity_type="attraction",
            sentiment="positive",
            context="Amazing temple with intricate details"
        ),
        EntityExperience(
            entity_name="Chatuchak Market",
            entity_type="place",
            sentiment="positive",
            context="Huge market with endless stalls"
        )
    ]
```

---

## Test Coverage Goals

### Current Coverage

**Overall:** ~60%

### Target Coverage

| Module | Current | Target |
|--------|---------|--------|
| Stage 1 (Crawlers) | 70% | 85% |
| Stage 2 (Extractors) | 55% | 80% |
| Stage 3 (Canonicalization) | 60% | 80% |
| Stage 4 (Vectorization) | 50% | 75% |
| Stage 5 (RAG) | 40% | 70% |
| Storage | 65% | 85% |
| Utils | 75% | 90% |

---

## Performance Tests

### Benchmark Tests

```python
import pytest
import time

def test_semantic_chunking_performance():
    """Test semantic chunking performance."""
    # Large transcript (1000 segments)
    transcript = [
        {"text": f"Segment {i}", "start": float(i), "duration": 1.0}
        for i in range(1000)
    ]

    start = time.time()
    chunks = split_transcript_semantically(transcript)
    duration = time.time() - start

    assert duration < 1.0  # Should complete in < 1 second
    assert len(chunks) > 0
```

---

## Continuous Integration

### GitHub Actions

**File:** `.github/workflows/tests.yml`

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v2

    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install -r requirements-dev.txt

    - name: Run tests
      run: |
        pytest --cov=src --cov-report=xml

    - name: Upload coverage
      uses: codecov/codecov-action@v2
```

---

## Testing Best Practices

### 1. Test Naming

```python
# Good: Descriptive test name
def test_semantic_chunking_splits_on_day_markers():
    pass

# Bad: Vague test name
def test_chunking():
    pass
```

### 2. One Assertion Per Test

```python
# Good: Single clear assertion
def test_entity_name_normalization():
    assert normalize_name("Grand Palace") == "grand palace"

# Acceptable: Multiple related assertions
def test_entity_structure():
    entity = create_entity("Test")
    assert entity.name == "Test"
    assert entity.type == "unknown"
```

### 3. Use Fixtures

```python
# Good: Reusable fixture
@pytest.fixture
def sample_entity():
    return EntityExperience(name="Test", type="attraction")

def test_entity_validation(sample_entity):
    assert validate_entity(sample_entity) == True

# Bad: Duplicate setup in each test
def test_entity_validation():
    entity = EntityExperience(name="Test", type="attraction")
    assert validate_entity(entity) == True
```

---

## References

- **Contributing:** [contributing.md](contributing.md)
- **Project Structure:** [project-structure.md](../01-getting-started/project-structure.md)
- **Pytest Documentation:** https://docs.pytest.org/
