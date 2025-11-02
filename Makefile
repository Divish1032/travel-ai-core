.PHONY: setup crawl-sample crawl-youtube test clean jupyter help

VENV = venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip

help:
	@echo "Available commands:"
	@echo "  make setup          - Create virtual environment and install dependencies"
	@echo "  make crawl-sample   - Crawl 5 sample YouTube videos"
	@echo "  make crawl-youtube  - Crawl YouTube videos from urls file"
	@echo "  make test           - Run pytest test suite"
	@echo "  make clean          - Remove cache files and logs"
	@echo "  make jupyter        - Start Jupyter Lab"

setup:
	@echo "Creating virtual environment..."
	python3 -m venv $(VENV)
	@echo "Installing dependencies..."
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo "Creating data directories..."
	mkdir -p data/raw data/processed data/cache logs
	@echo "Setup complete! Activate with: source $(VENV)/bin/activate"

crawl-sample:
	@echo "Crawling 5 sample videos..."
	$(PYTHON) cli/crawl.py --limit 5

crawl-youtube:
	@echo "Crawling YouTube videos from urls file..."
	$(PYTHON) cli/crawl.py --input data/youtube_urls.txt

test:
	@echo "Running tests..."
	$(PYTHON) -m pytest tests/ -v

clean:
	@echo "Cleaning cache and logs..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf logs/*.log
	rm -rf data/cache/*
	@echo "Clean complete!"

jupyter:
	@echo "Starting Jupyter Lab..."
	$(PYTHON) -m jupyter lab
