# Contributing to TravelAI

Thank you for your interest in contributing to TravelAI! This guide will help you get started.

---

## Getting Started

### 1. Fork and Clone

```bash
# Fork on GitHub, then clone your fork
git clone https://github.com/YOUR-USERNAME/TravelAI.git
cd TravelAI

# Add upstream remote
git remote add upstream https://github.com/original/TravelAI.git
```

### 2. Set Up Development Environment

```bash
# Run automated setup
./setup.sh

# Or manual setup
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Development dependencies
```

### 3. Create Feature Branch

```bash
git checkout -b feature/your-feature-name
```

---

## Development Workflow

### 1. Make Changes

- Follow code style guidelines (see below)
- Write/update tests for new features
- Update documentation

### 2. Test Changes

```bash
# Run tests
pytest tests/

# Run specific test
pytest tests/test_stage2.py

# Check code style
flake8 src/
black --check src/

# Format code
black src/
```

### 3. Commit Changes

```bash
# Stage changes
git add .

# Commit with descriptive message
git commit -m "Add semantic chunking to Stage 2 extraction

- Implement topic shift detection patterns
- Add min/max/target chunk duration parameters
- Update tests for new chunking strategy
"
```

### 4. Push and Create PR

```bash
# Push to your fork
git push origin feature/your-feature-name

# Create Pull Request on GitHub
```

---

## Code Style

### Python Style Guide

- **Follow PEP 8**
- **Use Black** for formatting (line length: 100)
- **Use type hints** for function signatures
- **Write docstrings** for all public functions

**Example:**
```python
def extract_entities(
    transcript: List[Dict[str, Any]],
    use_semantic_chunking: bool = True
) -> List[EntityExperience]:
    """
    Extract travel entities from transcript.

    Args:
        transcript: List of transcript segments from Stage 1
        use_semantic_chunking: Whether to use semantic chunking (default: True)

    Returns:
        List of extracted EntityExperience objects

    Example:
        >>> transcript = load_transcript("video_123")
        >>> entities = extract_entities(transcript)
        >>> print(f"Extracted {len(entities)} entities")
    """
    pass
```

### Code Organization

- **One class per file** (exceptions: small helper classes)
- **Group imports** (stdlib → third-party → local)
- **Use descriptive names** (avoid abbreviations)

---

## Testing Guidelines

### Writing Tests

```python
import pytest
from src.processors.stage2_extractor import extract_entities

def test_semantic_chunking():
    """Test semantic chunking splits on topic shifts."""
    transcript = [
        {"text": "Today we're in Bangkok", "start": 0.0, "duration": 5.0},
        {"text": "Day 2, we went to Phuket", "start": 300.0, "duration": 5.0}
    ]

    chunks = split_transcript_semantically(transcript)

    assert len(chunks) == 2  # Split at "Day 2" marker
    assert chunks[0][0]['text'] == "Today we're in Bangkok"
    assert chunks[1][0]['text'] == "Day 2, we went to Phuket"
```

### Test Structure

```
tests/
├── unit/                    # Unit tests
│   ├── test_stage1.py
│   ├── test_stage2.py
│   └── test_stage3.py
├── integration/             # Integration tests
│   ├── test_pipeline.py
│   └── test_s3_storage.py
└── fixtures/                # Test data
    ├── sample_transcripts/
    └── sample_entities/
```

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=src --cov-report=html

# Specific module
pytest tests/unit/test_stage2.py

# Specific test
pytest tests/unit/test_stage2.py::test_semantic_chunking

# Verbose output
pytest -v
```

---

## Documentation

### Updating Documentation

When adding new features:

1. **Update relevant stage docs** in `docs/03-pipeline-stages/`
2. **Update CLI reference** if adding new commands
3. **Add examples** to show usage
4. **Update configuration guide** if adding new .env variables

### Documentation Style

- **Use clear headings** for navigation
- **Provide code examples** for every feature
- **Include "Why" explanations**, not just "What"
- **Cross-reference** related documentation

---

## Pull Request Guidelines

### PR Title

Use conventional commit format:
```
feat: Add semantic chunking to Stage 2
fix: Correct geohash precision in Stage 4
docs: Update RAG pipeline documentation
refactor: Simplify fuzzy matching logic
test: Add tests for Stage 3 deduplication
```

### PR Description Template

```markdown
## Description
Brief description of what this PR does.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing completed

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] Tests pass locally
- [ ] No new warnings
```

---

## Areas for Contribution

### High Priority

1. **Add more LLM providers** (Anthropic Claude, Cohere)
2. **Improve Stage 2 entity extraction** (better prompts, edge cases)
3. **Add more embedding types** (location-focused, logistics-focused)
4. **Build REST API** (FastAPI endpoints)
5. **Add more test coverage** (currently ~60%, target 80%+)

### Medium Priority

6. **Improve documentation** (more examples, tutorials)
7. **Add CLI progress bars** (better UX)
8. **Optimize costs** (smarter LLM usage, caching)
9. **Add monitoring dashboard** (Grafana, Prometheus)
10. **Support more languages** (non-English videos)

### Good First Issues

- Add more topic shift patterns for semantic chunking
- Improve error messages in CLI
- Add more examples to documentation
- Fix typos and formatting issues
- Add unit tests for existing functions

---

## Code Review Process

### Reviewer Checklist

- [ ] Code follows style guidelines
- [ ] Tests are comprehensive
- [ ] Documentation is clear
- [ ] No breaking changes (or documented)
- [ ] Performance impact considered
- [ ] Security implications reviewed

### Review Response

- **Be respectful** and constructive
- **Explain your suggestions** with reasoning
- **Ask questions** if unclear
- **Approve when satisfied** or request changes

---

## Getting Help

### Questions

- **Documentation:** Check [docs/](../README.md) first
- **GitHub Issues:** Search existing issues
- **Discussions:** Use GitHub Discussions for questions

### Reporting Bugs

Include:
1. **Description** of the bug
2. **Steps to reproduce**
3. **Expected behavior**
4. **Actual behavior**
5. **Environment** (OS, Python version, etc.)
6. **Logs** (relevant error messages)

---

## License

By contributing to TravelAI, you agree that your contributions will be licensed under the MIT License.

---

## References

- **Testing:** [testing.md](testing.md)
- **Project Structure:** [project-structure.md](../01-getting-started/project-structure.md)
- **CLI Commands:** [cli-commands.md](../04-reference/cli-commands.md)
