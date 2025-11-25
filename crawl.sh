#!/bin/bash
#
# Travel AI YouTube Crawler - Helper Script
#
# Simplifies running the crawler by automatically setting PYTHONPATH
# and providing convenient shortcuts for common commands.
#
# Usage:
#   ./crawl.sh youtube --input urls.txt              # Crawl videos (skips duplicates)
#   ./crawl.sh youtube --input urls.txt --force      # Force re-processing
#   ./crawl.sh youtube --input urls.txt --limit 5    # Test with 5 videos
#   ./crawl.sh status                                # Check pipeline status
#   ./crawl.sh help                                  # Show help
#

# Get script directory (project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Set PYTHONPATH to project root
export PYTHONPATH="$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if virtual environment exists
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo -e "${YELLOW}Warning: Virtual environment not found at $SCRIPT_DIR/venv${NC}"
    echo -e "${YELLOW}Consider creating one: python -m venv venv && source venv/bin/activate && pip install -r requirements.txt${NC}"
    echo ""
fi

# Check if .env file exists
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo -e "${RED}Error: .env file not found${NC}"
    echo -e "${YELLOW}Please create .env file with AWS credentials:${NC}"
    echo -e "  cp .env.example .env"
    echo -e "  # Then edit .env with your AWS credentials"
    exit 1
fi

# If no arguments or 'help', show usage
if [ $# -eq 0 ] || [ "$1" == "help" ] || [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
    echo -e "${BLUE}Travel AI YouTube Crawler - Helper Script${NC}"
    echo ""
    echo "Usage:"
    echo "  ./crawl.sh youtube --input urls.txt [OPTIONS]    Crawl YouTube videos (Stage 1)"
    echo "  ./crawl.sh process-stage2 [OPTIONS]              Extract entities with LLM (Stage 2)"
    echo "  ./crawl.sh status                                 Check pipeline status"
    echo "  ./crawl.sh stage STAGE_NAME                       View stage details"
    echo "  ./crawl.sh failed                                 List failed items"
    echo "  ./crawl.sh languages                              Show language distribution"
    echo "  ./crawl.sh help                                   Show this help"
    echo ""
    echo "YouTube Crawl Options (Stage 1):"
    echo "  --input, -i FILE         Path to URLs file (required)"
    echo "  --limit, -l N            Limit to first N videos"
    echo "  --force                  Force re-processing (skip deduplication check)"
    echo "  --dry-run                Show what would be crawled without crawling"
    echo ""
    echo "Stage 2 Processing Options:"
    echo "  --limit N                Limit to first N videos (for testing)"
    echo "  --force                  Reprocess videos that already have Stage 2 data"
    echo "  --log-level LEVEL        Set logging level (DEBUG, INFO, WARNING, ERROR)"
    echo ""
    echo "Examples:"
    echo "  # Stage 1: Crawl and transcribe videos"
    echo "  ./crawl.sh youtube --input urls.txt                  # Skips already processed videos"
    echo "  ./crawl.sh youtube --input urls.txt --force          # Re-process all videos"
    echo "  ./crawl.sh youtube --input urls.txt --limit 5        # Test with 5 videos"
    echo ""
    echo "  # Stage 2: Extract entities with LLM"
    echo "  ./crawl.sh process-stage2 --limit 5                  # Test with 5 videos"
    echo "  ./crawl.sh process-stage2                            # Process all pending videos"
    echo "  ./crawl.sh process-stage2 --force --limit 10         # Reprocess 10 videos"
    echo ""
    echo "  # Monitoring"
    echo "  ./crawl.sh status"
    echo "  ./crawl.sh stage stage_2_extract"
    echo ""
    exit 0
fi

# Detect Python command (prefer python3, fallback to python)
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo -e "${RED}Error: Python not found${NC}"
    echo -e "${YELLOW}Please install Python 3.8 or higher${NC}"
    exit 1
fi

# Handle special commands
case "$1" in
    status|stage|failed|info|retry|export|languages)
        # Tracking commands
        $PYTHON_CMD "$SCRIPT_DIR/cli/tracking.py" "$@"
        ;;
    youtube)
        # Crawler command
        $PYTHON_CMD "$SCRIPT_DIR/cli/crawl.py" "$@"
        ;;
    validate)
        # Validate command
        $PYTHON_CMD "$SCRIPT_DIR/cli/crawl.py" "$@"
        ;;
    process-stage2)
        # Stage 2 processing command
        shift  # Remove 'process-stage2' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/process_stage2.py" "$@"
        ;;
    *)
        echo -e "${RED}Error: Unknown command '$1'${NC}"
        echo "Run './crawl.sh help' for usage information"
        exit 1
        ;;
esac
