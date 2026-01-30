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
    echo "  ./crawl.sh process-insights [OPTIONS]            Extract travel insights (Insights Pipeline)"
    echo "  ./crawl.sh canonicalize-insights [OPTIONS]       Deduplicate & canonicalize insights (Phase 2C)"
    echo "  ./crawl.sh insights-stats                        Show insights pipeline statistics"
    echo "  ./crawl.sh process-city-index [OPTIONS]          Build city-level index (Stage 4 Tier 1)"
    echo "  ./crawl.sh process-stage4 [OPTIONS]              Generate and index vector embeddings (Stage 4)"
    echo "  ./crawl.sh debug-extraction --url URL            Debug entity extraction pipeline (Stages 1-3)"
    echo "  ./crawl.sh dashboard                             Launch interactive data dashboard (Streamlit)"
    echo "  ./crawl.sh validate-stage3 [OPTIONS]             Validate Stage 3 quality (QA)"
    echo "  ./crawl.sh stage3-stats                          Show Stage 3 statistics"
    echo "  ./crawl.sh stage4-stats                          Show Stage 4 statistics and metrics"
    echo "  ./crawl.sh show-entity ENTITY_ID                 Display entity details with provenance"
    echo "  ./crawl.sh search-entities --query QUERY         Search entities by name"
    echo "  ./crawl.sh search --query QUERY [OPTIONS]        Semantic search interface"
    echo "  ./crawl.sh reset-stage2 [OPTIONS]                Reset Stage 2 data and metadata"
    echo "  ./crawl.sh reset-stage3 [OPTIONS]                Reset Stage 3 data and metadata"
    echo "  ./crawl.sh reset-insights [OPTIONS]              Reset insights pipeline data and metadata"
    echo "  ./crawl.sh reset-stage4 [OPTIONS]                Reset Stage 4 vector database"
    echo "  ./crawl.sh reset-all [OPTIONS]                   Reset ALL stages (1,2,3) with automatic backup"
    echo "  ./crawl.sh backup-vectors [OPTIONS]              Backup vector database to S3"
    echo "  ./crawl.sh sync-to-cloud [OPTIONS]               Sync local vectors to cloud ChromaDB"
    echo "  ./crawl.sh monitor-stage4                        Monitor Stage 4 health and performance"
    echo "  ./crawl.sh generate-itinerary -q QUERY [OPTIONS] Generate personalized travel itinerary (Stage 5 RAG)"
    echo "  ./crawl.sh parse-query QUERY                     Test intent parsing without generating"
    echo "  ./crawl.sh validate-itinerary FILE               Validate existing itinerary JSON file"
    echo "  ./crawl.sh itinerary-examples                    Show example itinerary queries"
    echo "  ./crawl.sh check-stage5                          Check Stage 5 readiness"
    echo "  ./crawl.sh test-stage5                           Run Stage 5 integration tests"
    echo "  ./crawl.sh quick-test                            Quick Stage 5 sanity check"
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
    echo "Insights Pipeline Processing Options:"
    echo "  --limit N                Limit to first N videos (for testing)"
    echo "  --pass {1,2,all}         Which pass: 1 (entities), 2 (transcripts), all (default: all)"
    echo "  --log-level LEVEL        Set logging level (DEBUG, INFO, WARNING, ERROR)"
    echo ""
    echo "City Index Building Options (Stage 4 Tier 1):"
    echo "  --min-entities N         Minimum entities required per city (default: 5)"
    echo "  --batch-size N           Batch size for embedding generation (default: 50)"
    echo "  --verify-only            Only verify existing index (skip building)"
    echo ""
    echo "Stage 4 Vector Indexing Options:"
    echo "  --embedding-types TYPES  Comma-separated types: entity,profile,experience or 'all'"
    echo "  --limit N                Limit to first N entities (for testing)"
    echo "  --batch-size N           Batch size for embedding generation (default: 100)"
    echo "  --log-level LEVEL        Set logging level (DEBUG, INFO, WARNING, ERROR)"
    echo ""
    echo "Debug Extraction Options:"
    echo "  --url URL                YouTube video URL (required)"
    echo "  --output-dir DIR         Output directory for reports (default: debug_reports/)"
    echo ""
    echo "Stage 5 Itinerary Generation Options:"
    echo "  -q, --query QUERY        Travel query (e.g., '5 days Bangkok solo budget')"
    echo "  -o, --output FORMAT      Output format: json, markdown, html, text (default: markdown)"
    echo "  -s, --save FILE          Save output to file"
    echo "  -i, --interactive        Interactive mode with follow-up questions"
    echo "  --validate-only          Only validate, don't generate narrative"
    echo "  --skip-narrative         Skip narrative generation (faster)"
    echo "  --debug                  Show detailed debug information"
    echo ""
    echo "Stage 3 Validation Options:"
    echo "  --sample N               Number of entities to sample for review (default: 20)"
    echo "  --log-level LEVEL        Set logging level (DEBUG, INFO, WARNING, ERROR)"
    echo ""
    echo "Stage 4 Reset Options:"
    echo "  --all                    Reset all collections and metadata"
    echo "  --collections NAMES      Reset specific collections (entities,profiles,experiences)"
    echo "  --metadata               Reset metadata files only"
    echo "  --dry-run                Show what would be reset without making changes"
    echo "  --force                  Skip confirmation prompt"
    echo ""
    echo "Reset All Stages Options (Stages 1,2,3):"
    echo "  --backup                 Create backup before reset (RECOMMENDED - safe)"
    echo "  --backup-only            Only backup, don't delete data"
    echo "  --force                  Reset WITHOUT backup (DANGEROUS - NO RECOVERY!)"
    echo "  --dry-run                Preview what will be backed up/reset"
    echo "  --yes                    Skip all confirmation prompts"
    echo "  --keep-metadata          Don't reset metadata tracker"
    echo ""
    echo "Semantic Search Options:"
    echo "  --query, -q TEXT         Search query (required)"
    echo "  --profile, -p PROFILE    Traveler profile (solo_budget_party, couple_luxury, etc.)"
    echo "  --city, -c CITY          Filter by city"
    echo "  --type, -t TYPE          Filter by entity type (attraction, restaurant, hotel)"
    echo "  --top-k, -k N            Number of results (default: 10)"
    echo "  --rerank STRATEGY        Reranking: balanced, quality, popular, distance"
    echo "  --explain                Show match explanations"
    echo "  --interactive, -i        Run in interactive mode"
    echo ""
    echo "Vector Backup Options:"
    echo "  --collections NAMES      Backup specific collections (default: all)"
    echo "  --compress               Compress backup files"
    echo "  --incremental            Only backup changes since last backup"
    echo ""
    echo "Cloud Sync Options:"
    echo "  --collections NAMES      Sync specific collections (default: all)"
    echo "  --dry-run                Show what would be synced"
    echo "  --force                  Force full resync"
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
    echo "  # Debug: Test extraction pipeline with single video"
    echo "  ./crawl.sh debug-extraction --url 'https://youtube.com/watch?v=abc123'"
    echo ""
    echo "  # Stage 3: Deduplicate, canonicalize & consensus"
    echo "  ./crawl.sh process-stage3 --limit 10                 # Test with 10 videos"
    echo "  ./crawl.sh process-stage3 --entity-types attraction  # Process only attractions"
    echo "  ./crawl.sh process-stage3                            # Process all videos, all types"
    echo ""
    echo "  # Insights Pipeline: Extract travel tips, services, logistics"
    echo "  ./crawl.sh process-insights --limit 10               # Test with 10 videos"
    echo "  ./crawl.sh process-insights --pass 1                 # Process only filtered entities"
    echo "  ./crawl.sh process-insights --pass 2                 # Process only info-only videos"
    echo "  ./crawl.sh process-insights                          # Process all pending videos"
    echo "  ./crawl.sh insights-stats                            # Show insights statistics"
    echo ""
    echo "  # Stage 4: Vector embeddings and indexing"
    echo "  ./crawl.sh process-city-index --min-entities 5       # Build city-level index (Tier 1)"
    echo "  ./crawl.sh process-city-index --verify-only          # Verify existing city index"
    echo "  ./crawl.sh process-stage4 --embedding-types all --limit 10  # Test with 10 entities"
    echo "  ./crawl.sh process-stage4 --embedding-types entity   # Index only entity-level embeddings"
    echo "  ./crawl.sh process-stage4 --embedding-types all      # Index all embedding types"
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
    echo "  # Stage 2 Reset: Reprocess entity extraction"
    echo "  ./crawl.sh reset-stage2 --dry-run --all              # Preview what will be reset"
    echo "  ./crawl.sh reset-stage2 --all                        # Reset all Stage 2 data"
    echo "  ./crawl.sh reset-stage2 --video-ids abc123,xyz789    # Reset specific videos"
    echo ""
    echo "  # Stage 3 Reset: Reprocess with updated config"
    echo "  ./crawl.sh reset-stage3 --dry-run --all              # Preview what will be reset"
    echo "  ./crawl.sh reset-stage3 --all                        # Reset all Stage 3 data"
    echo "  ./crawl.sh reset-stage3 --video-ids abc123,xyz789    # Reset specific videos"
    echo ""
    echo "  # Insights Pipeline Reset: Reprocess insights"
    echo "  ./crawl.sh reset-insights --dry-run --all            # Preview what will be reset"
    echo "  ./crawl.sh reset-insights --all                      # Reset all insights data"
    echo "  ./crawl.sh reset-insights --video-ids abc123,xyz789  # Reset specific videos"
    echo ""
    echo "  # Stage 4 Reset: Reset vector database"
    echo "  ./crawl.sh reset-stage4 --all --dry-run              # Preview reset (no changes)"
    echo "  ./crawl.sh reset-stage4 --all                        # Reset everything (requires confirmation)"
    echo "  ./crawl.sh reset-stage4 --collections entities       # Reset only entities collection"
    echo "  ./crawl.sh reset-stage4 --collections entities,profiles  # Reset multiple collections"
    echo "  ./crawl.sh reset-stage4 --metadata                   # Reset only metadata files"
    echo ""
    echo "  # Reset ALL Stages (1,2,3): Complete pipeline reset with backup"
    echo "  ./crawl.sh reset-all --backup --dry-run              # SAFE: Preview what will happen"
    echo "  ./crawl.sh reset-all --backup                        # SAFE: Backup then reset (RECOMMENDED)"
    echo "  ./crawl.sh reset-all --backup-only                   # Create backup only (no deletion)"
    echo "  ./crawl.sh reset-all --force --yes                   # DANGER: Reset without backup!"
    echo ""
    echo "  # Semantic Search: Query the vector database"
    echo "  ./crawl.sh search --query \"beach parties\"              # Basic search"
    echo "  ./crawl.sh search --query \"romantic dinner\" --city Bangkok  # Filtered search"
    echo "  ./crawl.sh search --query \"places to stay\" --profile solo_budget_party  # Personalized"
    echo "  ./crawl.sh search --query \"restaurants\" --rerank quality  # With reranking"
    echo "  ./crawl.sh search --interactive                      # Interactive mode"
    echo ""
    echo "  # Stage 4 Operations: Backup and monitoring"
    echo "  ./crawl.sh stage4-stats                              # Show vector database statistics"
    echo "  ./crawl.sh backup-vectors                            # Backup all collections to S3"
    echo "  ./crawl.sh backup-vectors --collections entities --compress  # Compressed backup"
    echo "  ./crawl.sh sync-to-cloud                             # Sync local to cloud ChromaDB"
    echo "  ./crawl.sh monitor-stage4                            # Health check and monitoring"
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
    debug-extraction)
        # Debug entity extraction pipeline
        shift  # Remove 'debug-extraction' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/scripts/debug_entity_extraction.py" "$@"
        ;;
    dashboard)
        # Launch Streamlit dashboard
        "$SCRIPT_DIR/dashboard/run_dashboard.sh"
        ;;
    process-stage3)
        # Stage 3 processing command
        shift  # Remove 'process-stage3' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/process_stage3.py" "$@"
        ;;
    process-insights)
        # Insights Pipeline processing command
        shift  # Remove 'process-insights' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/process_insights.py" "$@"
        ;;
    insights-stats)
        # Insights statistics command
        shift  # Remove 'insights-stats' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/insights_stats.py" "$@"
        ;;
    canonicalize-insights)
        # Insights canonicalization command
        shift  # Remove 'canonicalize-insights' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/canonicalize_insights.py" "$@"
        ;;
    reset-insights)
        # Reset Insights Pipeline command
        shift  # Remove 'reset-insights' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/reset_insights.py" "$@"
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
    reset-stage2)
        # Reset Stage 2 command
        shift  # Remove 'reset-stage2' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/reset_stage2.py" "$@"
        ;;
    reset-stage3)
        # Reset Stage 3 command
        shift  # Remove 'reset-stage3' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/reset_stage3.py" "$@"
        ;;
    reset-stage4)
        # Reset Stage 4 command
        shift  # Remove 'reset-stage4' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/reset_stage4.py" "$@"
        ;;
    reset-all)
        # Reset ALL stages (1,2,3) with automatic backup
        shift  # Remove 'reset-all' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/reset_all_stages.py" "$@"
        ;;
    process-city-index)
        # Build city-level index (Stage 4 Tier 1)
        shift  # Remove 'process-city-index' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/process_city_index.py" "$@"
        ;;
    process-stage4)
        # Stage 4 vector indexing command
        shift  # Remove 'process-stage4' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/process_stage4.py" "$@"
        ;;
    stage4-stats)
        # Stage 4 statistics command
        shift  # Remove 'stage4-stats' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/stage4_stats.py" "$@"
        ;;
    search)
        # Semantic search interface
        shift  # Remove 'search' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/search_test.py" "$@"
        ;;
    backup-vectors)
        # Backup vector database to S3
        shift  # Remove 'backup-vectors' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/backup_vectors.py" "$@"
        ;;
    sync-to-cloud)
        # Sync local vectors to cloud ChromaDB
        shift  # Remove 'sync-to-cloud' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/sync_to_cloud.py" "$@"
        ;;
    monitor-stage4)
        # Monitor Stage 4 health and performance
        shift  # Remove 'monitor-stage4' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/monitor_stage4.py" "$@"
        ;;
    generate-itinerary)
        # Generate personalized travel itinerary (Stage 5 RAG)
        shift  # Remove 'generate-itinerary' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/generate_itinerary.py" generate "$@"
        ;;
    parse-query)
        # Test intent parsing without generating itinerary
        shift  # Remove 'parse-query' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/generate_itinerary.py" parse "$@"
        ;;
    validate-itinerary)
        # Validate existing itinerary JSON file
        shift  # Remove 'validate-itinerary' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/generate_itinerary.py" validate_file "$@"
        ;;
    itinerary-examples)
        # Show example itinerary queries
        shift  # Remove 'itinerary-examples' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/generate_itinerary.py" examples "$@"
        ;;
    check-stage5)
        # Check Stage 5 readiness
        shift  # Remove 'check-stage5' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/check_stage5_ready.py" "$@"
        ;;
    test-stage5)
        # Run Stage 5 integration tests
        shift  # Remove 'test-stage5' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/tests/test_stage5_rag.py" "$@"
        ;;
    quick-test)
        # Quick Stage 5 sanity check
        shift  # Remove 'quick-test' from arguments
        $PYTHON_CMD "$SCRIPT_DIR/cli/quick_test.py" "$@"
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
