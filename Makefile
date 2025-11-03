.PHONY: help setup test clean

help:
	@echo "Available commands:"
	@echo "  make setup    - Run automated setup script"
	@echo "  make test     - Run pytest test suite"
	@echo "  make clean    - Remove cache files and logs"
	@echo ""
	@echo "For crawling, use: ./crawl.sh youtube --input urls.txt"
	@echo "For tracking, use: ./crawl.sh status"

setup:
	@./setup.sh

test:
	@echo "Running tests..."
	@python -m pytest tests/ -v

clean:
	@echo "Cleaning cache and logs..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@rm -rf .pytest_cache
	@rm -rf logs/*.log
	@echo "Clean complete!"
