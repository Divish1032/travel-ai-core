#!/bin/bash
#
# TravelAI Dashboard Launcher
#
# Launches the Streamlit dashboard for visualizing pipeline data
#

# Get project root (parent of dashboard folder)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  TravelAI Dashboard${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if virtual environment exists
if [ ! -d "$PROJECT_ROOT/venv" ]; then
    echo -e "${GREEN}Virtual environment not found. Creating one...${NC}"
    cd "$PROJECT_ROOT"
    python3 -m venv venv
    source venv/bin/activate
    pip install -q -r dashboard/requirements.txt
else
    source "$PROJECT_ROOT/venv/bin/activate"
fi

# Check if dependencies are installed
if ! python -c "import streamlit" 2>/dev/null; then
    echo -e "${GREEN}Installing dashboard dependencies...${NC}"
    pip install -q -r "$PROJECT_ROOT/dashboard/requirements.txt"
fi

# Launch dashboard
echo -e "${GREEN}Launching dashboard...${NC}"
echo ""
echo -e "${BLUE}Dashboard will open at: http://localhost:8501${NC}"
echo ""
echo -e "Press Ctrl+C to stop the dashboard"
echo ""

cd "$PROJECT_ROOT/dashboard"
streamlit run 🏠_Home.py
