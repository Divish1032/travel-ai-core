.PHONY: help setup test clean

VENV = venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip

help:
	@echo "Available commands:"
	@echo "  make setup    - Create virtual environment and install dependencies"
	@echo "  make test     - Run pytest test suite"
	@echo "  make clean    - Remove cache files and logs"
	@echo ""
	@echo "For crawling, use: ./crawl.sh youtube --input urls.txt"
	@echo "For tracking, use: ./crawl.sh status"

setup:
	@echo "Creating virtual environment..."
	python3 -m venv $(VENV)
	@echo "Installing dependencies..."
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo "Creating log directory..."
	mkdir -p logs
	@echo ""
	@echo "Setup complete!"
	@echo "Next steps:"
	@echo "  1. Activate environment: source $(VENV)/bin/activate"
	@echo "  2. Configure AWS: cp .env.example .env && edit .env"
	@echo "  3. Test crawl: ./crawl.sh youtube --input test_urls.txt --limit 3"

test:
	@echo "Running tests..."
	$(PYTHON) -m pytest tests/ -v

clean:
	@echo "Cleaning cache and logs..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf logs/*.log
	@echo "Clean complete!"
