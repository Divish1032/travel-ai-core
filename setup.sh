#!/bin/bash

################################################################################
# Travel AI - Stage 1 Setup Script for Mac
#
# This script automates the setup process for the Travel AI project.
# It checks prerequisites, sets up the environment, and prepares the project
# for first use.
#
# Usage: ./setup.sh
################################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Extract version number
get_python_version() {
    python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))'
}

# Compare version numbers
version_ge() {
    printf '%s\n%s\n' "$2" "$1" | sort -V -C
}

################################################################################
# STEP 1: Check Prerequisites
################################################################################

print_header "STEP 1: Checking Prerequisites"

# Check Python 3.11+
print_info "Checking Python version..."
if ! command_exists python3; then
    print_error "Python 3 is not installed"
    echo "Please install Python 3.11+ from https://www.python.org/downloads/"
    exit 1
fi

PYTHON_VERSION=$(get_python_version)
REQUIRED_VERSION="3.11"

if version_ge "$PYTHON_VERSION" "$REQUIRED_VERSION"; then
    print_success "Python $PYTHON_VERSION is installed (>= $REQUIRED_VERSION required)"
else
    print_error "Python $PYTHON_VERSION is too old (>= $REQUIRED_VERSION required)"
    echo "Please upgrade Python: https://www.python.org/downloads/"
    exit 1
fi

# Check pip
print_info "Checking pip..."
if ! command_exists pip3; then
    print_error "pip is not installed"
    echo "Please install pip: python3 -m ensurepip"
    exit 1
fi
print_success "pip is installed"

# Check git (optional)
print_info "Checking git..."
if command_exists git; then
    print_success "git is installed"
else
    print_warning "git is not installed (optional but recommended)"
fi

################################################################################
# STEP 2: Create Virtual Environment
################################################################################

print_header "STEP 2: Creating Virtual Environment"

if [ -d "venv" ]; then
    print_warning "Virtual environment already exists"
    read -p "Do you want to recreate it? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Removing existing virtual environment..."
        rm -rf venv
        print_success "Removed existing venv"
    else
        print_info "Keeping existing virtual environment"
    fi
fi

if [ ! -d "venv" ]; then
    print_info "Creating virtual environment..."
    python3 -m venv venv
    print_success "Virtual environment created"
fi

print_info "To activate the virtual environment, run:"
echo -e "${GREEN}  source venv/bin/activate${NC}"

# Activate virtual environment for this script
source venv/bin/activate

################################################################################
# STEP 3: Upgrade pip
################################################################################

print_header "STEP 3: Upgrading pip"

print_info "Upgrading pip to latest version..."
pip install --upgrade pip --quiet
print_success "pip upgraded successfully"

################################################################################
# STEP 4: Install Dependencies
################################################################################

print_header "STEP 4: Installing Dependencies"

if [ ! -f "requirements.txt" ]; then
    print_error "requirements.txt not found"
    exit 1
fi

print_info "Installing Python packages (this may take a few minutes)..."
pip install -r requirements.txt --quiet
print_success "All dependencies installed successfully"

################################################################################
# STEP 5: Create Directories
################################################################################

print_header "STEP 5: Creating Project Directories"

print_info "Creating data directories..."
mkdir -p data/raw data/processed data/cache
print_success "Data directories created"

print_info "Creating logs directory..."
mkdir -p logs
print_success "Logs directory created"

################################################################################
# STEP 6: Setup Environment Variables
################################################################################

print_header "STEP 6: Setting Up Environment Variables"

if [ -f ".env" ]; then
    print_success ".env file already exists"
else
    if [ -f ".env.example" ]; then
        print_info "Creating .env from .env.example..."
        cp .env.example .env
        print_success ".env file created"
        print_warning "Please edit .env and add your AWS credentials:"
        echo -e "${YELLOW}  - AWS_ACCESS_KEY_ID${NC}"
        echo -e "${YELLOW}  - AWS_SECRET_ACCESS_KEY${NC}"
        echo -e "${YELLOW}  - S3_BUCKET_NAME${NC}"
        echo ""
        read -p "Press Enter to continue after you've updated .env (or skip for now)..."
    else
        print_error ".env.example not found"
        exit 1
    fi
fi

################################################################################
# STEP 7: Verify AWS Credentials (Optional)
################################################################################

print_header "STEP 7: Verifying AWS Credentials"

print_info "Checking AWS credentials..."

# Try to verify AWS credentials with Python
python3 << 'EOF'
import sys
try:
    from src.utils.config import config
    from src.storage.s3 import S3Storage

    if config is None:
        print("⚠ Config not loaded - please set up .env file")
        sys.exit(0)

    # Try to initialize S3 storage
    storage = S3Storage()
    print("✓ AWS credentials are valid")
    print(f"✓ Connected to S3 bucket: {storage.bucket_name}")
    sys.exit(0)

except Exception as e:
    error_msg = str(e)
    if "credentials" in error_msg.lower() or "access" in error_msg.lower():
        print(f"⚠ AWS credentials not configured or invalid")
        print("  Please update your .env file with valid AWS credentials")
        print("")
        print("  To get AWS credentials:")
        print("  1. Go to AWS Console: https://console.aws.amazon.com/")
        print("  2. Navigate to IAM > Users > Your User > Security Credentials")
        print("  3. Create Access Key and copy to .env")
        print("")
        print("  You can continue without AWS for now (local storage only)")
    else:
        print(f"⚠ Could not verify AWS setup: {error_msg}")
    sys.exit(0)
EOF

################################################################################
# STEP 8: Create Sample URLs File
################################################################################

print_header "STEP 8: Creating Data"

SAMPLE_URLS_FILE="urls.txt"

if [ -f "$SAMPLE_URLS_FILE" ]; then
    print_success "URLs file already exists"
else
    print_info "Creating sample URLs file..."
    cat > "$SAMPLE_URLS_FILE" << 'EOF'
# Sample YouTube Travel Vlog URLs for Testing
# Replace these with actual travel vlog URLs you want to crawl

# Example URLs (these may not have transcripts - replace with real URLs)
https://youtube.com/watch?v=dQw4w9WgXcQ
https://youtube.com/watch?v=jNQXAC9IVRw

# Add your own travel vlog URLs below:
# https://youtube.com/watch?v=YOUR_VIDEO_ID_HERE
EOF
    print_success "Sample URLs file created at $SAMPLE_URLS_FILE"
    print_warning "Please add real travel vlog URLs to $SAMPLE_URLS_FILE before crawling"
fi

################################################################################
# STEP 9: Run Basic Tests
################################################################################

print_header "STEP 9: Running Basic Tests"

print_info "Testing imports..."
python3 << 'EOF'
try:
    from src.utils.config import config
    from src.utils.logging import setup_logging, get_logger
    from src.utils.schemas import YouTubeVideo
    from src.crawlers.youtube import crawl_video
    from src.storage.s3 import S3Storage
    print("✓ All imports successful")
except Exception as e:
    print(f"✗ Import error: {e}")
    import sys
    sys.exit(1)
EOF

print_success "Basic tests passed"

################################################################################
# SUCCESS SUMMARY
################################################################################

print_header "Setup Complete! 🎉"

echo -e "${GREEN}Travel AI project setup is complete!${NC}"
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo ""
echo -e "${YELLOW}1. Activate the virtual environment:${NC}"
echo -e "   ${GREEN}source venv/bin/activate${NC}"
echo ""
echo -e "${YELLOW}2. Configure your .env file (if not done yet):${NC}"
echo -e "   ${GREEN}nano .env${NC}"
echo -e "   Add your AWS credentials"
echo ""
echo -e "${YELLOW}3. Add real YouTube URLs to sample file:${NC}"
echo -e "   ${GREEN}nano urls.txt${NC}"
echo ""
echo -e "${YELLOW}4. Run a test crawl:${NC}"
echo -e "   ${GREEN}./crawl.sh youtube --input test_urls.txt --limit 3${NC}"
echo ""
echo -e "${YELLOW}5. Check pipeline status:${NC}"
echo -e "   ${GREEN}./crawl.sh status${NC}"
echo ""
echo -e "${YELLOW}6. Validate pipeline:${NC}"
echo -e "   ${GREEN}python validate_pipeline.py${NC}"
echo ""
echo -e "${YELLOW}7. View logs:${NC}"
echo -e "   ${GREEN}tail -f logs/app_*.log${NC}"
echo ""
echo -e "${BLUE}Useful Commands:${NC}"
echo -e "   ${GREEN}./crawl.sh help${NC}              - Show crawler commands"
echo -e "   ${GREEN}./crawl.sh youtube --input urls.txt${NC} - Crawl videos"
echo -e "   ${GREEN}./crawl.sh status${NC}            - Check pipeline status"
echo -e "   ${GREEN}make test${NC}                    - Run tests"
echo -e "   ${GREEN}make clean${NC}                   - Clean cache and logs"
echo ""
echo -e "${BLUE}Documentation:${NC}"
echo -e "   ${GREEN}README.md${NC}                    - Project overview"
echo -e "   ${GREEN}src/crawlers/youtube.py${NC}      - Crawler implementation"
echo -e "   ${GREEN}cli/crawl.py${NC}                 - CLI documentation"
echo ""
echo -e "${GREEN}Happy crawling! 🚀${NC}"
echo ""

# Deactivate virtual environment for clean exit
deactivate 2>/dev/null || true
