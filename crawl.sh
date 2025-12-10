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
    echo "  ./crawl.sh process-stage3 [OPTIONS]              Deduplicate, canonicalize & consensus (Stage 3)"
    echo "  ./crawl.sh validate-stage3 [OPTIONS]             Validate Stage 3 quality (QA)"
    echo "  ./crawl.sh stage3-stats                          Show Stage 3 statistics"
    echo "  ./crawl.sh show-entity ENTITY_ID                 Display entity details with provenance"
    echo "  ./crawl.sh search-entities --query QUERY         Search entities by name"
    echo "  ./crawl.sh reset-stage3 [OPTIONS]                Reset Stage 3 data and metadata"
    echo "  ./crawl.sh status                                 Check pipeline status"
    echo "  ./crawl.sh stage STAGE_NAME                       View stage details"
    echo "  ./crawl.sh failed                                 List failed items"
    echo "  ./crawl.sh languages                              Show language distribution"
    echo "  ./crawl.sh view-stage2 VIDEO_ID [OPTIONS]        View extracted entities for a video"
    echo "  ./crawl.sh list-stage2 [OPTIONS]                 List all Stage 2 processed videos"
    echo "  ./crawl.sh audit --stage STAGE_NAME [OPTIONS]    Audit S3 bucket vs metadata"
    echo "  ./crawl.sh reset --stage STAGE_NAME [OPTIONS]    Reset stage status for videos"
    echo "  ./crawl.sh sync --stage STAGE_NAME               Sync metadata with S3 reality"
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
    echo "Stage 3 Processing Options:"
    echo "  --limit N                Limit to first N videos (for testing)"
    echo "  --entity-types TYPES     Comma-separated entity types (e.g., attraction,destination)"
    echo "  --no-save                Don't save to S3 (for testing)"
    echo "  --log-level LEVEL        Set logging level (DEBUG, INFO, WARNING, ERROR)"
    echo ""
    echo "Stage 3 Validation Options:"
    echo "  --sample N               Number of entities to sample for review (default: 20)"
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
    echo "  # Stage 3: Deduplicate, canonicalize & consensus"
    echo "  ./crawl.sh process-stage3 --limit 10                 # Test with 10 videos"
    echo "  ./crawl.sh process-stage3 --entity-types attraction  # Process only attractions"
    echo "  ./crawl.sh process-stage3                            # Process all videos, all types"
    echo ""
    echo "  # Stage 3 Validation: Quality assurance"
    echo "  ./crawl.sh validate-stage3                           # Validate with default settings"
    echo "  ./crawl.sh validate-stage3 --sample 50               # Validate with larger sample"
    echo ""
    echo "  # Stage 3 Tools: Statistics and search"
    echo "  ./crawl.sh stage3-stats                              # Show entity statistics"
    echo "  ./crawl.sh show-entity ATT_001                       # Show entity details"
    echo "  ./crawl.sh search-entities --query \"Khao San\"        # Search entities"
    echo "  ./crawl.sh search-entities --query \"temple\" --city Bangkok  # Filter by city"
    echo ""
    echo "  # Stage 3 Reset: Reprocess with updated config"
    echo "  ./crawl.sh reset-stage3 --dry-run --all              # Preview what will be reset"
    echo "  ./crawl.sh reset-stage3 --all                        # Reset all Stage 3 data"
    echo "  ./crawl.sh reset-stage3 --video-ids abc123,xyz789    # Reset specific videos"
    echo ""
    echo "  # Monitoring"
    echo "  ./crawl.sh status                                     # Overall pipeline status"
    echo "  ./crawl.sh stage stage_2_extract                      # Stage 2 details"
    echo "  ./crawl.sh list-stage2 --limit 20                     # List top 20 videos by entities"
    echo "  ./crawl.sh view-stage2 youtube_abc123                 # View all entities for video"
    echo "  ./crawl.sh view-stage2 youtube_abc123 -t restaurant   # View only restaurants"
    echo ""
    echo "  # S3 Audit & Reset"
    echo "  ./crawl.sh audit --stage stage_2_extract              # Compare S3 vs metadata"
    echo "  ./crawl.sh audit --stage stage_2_extract --show-missing  # Show missing videos"
    echo "  ./crawl.sh reset --stage stage_2_extract --all --dry-run # Preview reset"
    echo "  ./crawl.sh reset --stage stage_2_extract --video-id youtube_abc123  # Reset specific video"
    echo "  ./crawl.sh sync --stage stage_2_extract               # Sync metadata with S3"
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
    status|stage|failed|info|retry|export|languages|view-stage2|list-stage2)
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
    process-stage3)
        # Stage 3 processing command
        shift  # Remove 'process-stage3' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/process_stage3.py" "$@"
        ;;
    validate-stage3)
        # Stage 3 validation command
        shift  # Remove 'validate-stage3' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/validate_stage3.py" "$@"
        ;;
    stage3-stats)
        # Stage 3 statistics command
        shift  # Remove 'stage3-stats' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/stage3_stats.py" "$@"
        ;;
    show-entity)
        # Show entity command
        shift  # Remove 'show-entity' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/show_entity.py" "$@"
        ;;
    search-entities)
        # Search entities command
        shift  # Remove 'search-entities' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/search_entities.py" "$@"
        ;;
    reset-stage3)
        # Reset Stage 3 command
        shift  # Remove 'reset-stage3' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/reset_stage3.py" "$@"
        ;;
    audit|reset|sync)
        # S3 audit and reset commands
        $PYTHON_CMD "$SCRIPT_DIR/cli/audit_s3.py" "$@"
        ;;
    *)
        echo -e "${RED}Error: Unknown command '$1'${NC}"
        echo "Run './crawl.sh help' for usage information"
        exit 1
        ;;
esac
