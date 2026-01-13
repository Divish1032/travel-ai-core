#!/bin/bash

################################################################################
# TravelAI Deployment Script
# Simple script to deploy locally or to cloud
################################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

show_help() {
    cat << EOF

${GREEN}TravelAI Deployment${NC}

${YELLOW}Local Development:${NC}
  ./deploy.sh --local --frontend     Start frontend dev server (port 5173)
  ./deploy.sh --local --backend      Start backend dev server (port 8000)
  ./deploy.sh --stop --local         Stop all local servers

${YELLOW}Cloud Production:${NC}
  ./deploy.sh --cloud                Start Docker containers
  ./deploy.sh --stop --cloud         Stop Docker containers
  ./deploy.sh --cloud --build        Rebuild and start Docker containers

${YELLOW}Examples:${NC}
  # Start local frontend
  ./deploy.sh --local --frontend

  # Start local backend
  ./deploy.sh --local --backend

  # Deploy to cloud
  ./deploy.sh --cloud

  # Stop local servers
  ./deploy.sh --stop --local

EOF
}

################################################################################
# Local Frontend
################################################################################

start_local_frontend() {
    log_info "Starting frontend dev server..."

    cd "$SCRIPT_DIR/frontend-react"

    # Install dependencies if needed
    if [ ! -d "node_modules" ]; then
        log_info "Installing dependencies..."
        npm install
    fi

    # Create .env.local if needed
    if [ ! -f ".env.local" ]; then
        cat > .env.local <<EOF
VITE_API_URL=http://localhost:8001
EOF
        log_info "Created .env.local"
    fi

    log_success "Frontend starting on http://localhost:5173"
    npm run dev
}

################################################################################
# Local Backend
################################################################################

start_local_backend() {
    log_info "Starting backend dev server..."

    # cd "$SCRIPT_DIR/backend"

    # # Create venv if needed
    # if [ ! -d ".venv" ]; then
    #     log_info "Creating Python virtual environment..."
    #     python3 -m venv .venv
    # fi

    # # Activate venv and install dependencies
    # source .venv/bin/activate
    # pip install -q --upgrade pip
    # pip install -q -r requirements.txt

    # # Install project dependencies
    # cd "$PROJECT_ROOT"
    # pip install -q -r requirements.txt

    cd "$SCRIPT_DIR/backend"

    # Load environment
    if [ -f "$SCRIPT_DIR/.env" ]; then
        set -a
        source "$SCRIPT_DIR/.env"
        set +a
    fi

    # Set PYTHONPATH
    export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

    log_success "Backend starting on http://localhost:8001"
    uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
}

################################################################################
# Stop Local
################################################################################

stop_local() {
    log_info "Stopping local servers..."

    # Stop backend
    if pgrep -f "uvicorn.*app.main:app" > /dev/null; then
        pkill -f "uvicorn.*app.main:app"
        log_info "Backend stopped"
    fi

    # Stop frontend
    if pgrep -f "vite" > /dev/null; then
        pkill -f "vite"
        log_info "Frontend stopped"
    fi

    log_success "All local servers stopped"
}

################################################################################
# Cloud Deploy
################################################################################

start_cloud() {
    local build_flag="$1"

    log_info "Starting cloud deployment..."

    cd "$SCRIPT_DIR"

    # Check if .env exists
    if [ ! -f ".env" ]; then
        log_error ".env file not found. Copy from .env.example and configure."
        exit 1
    fi

    # Start with or without build
    if [ "$build_flag" = "--build" ]; then
        log_info "Building and starting containers..."
        docker compose -f docker-compose-nginx.yml up -d --build
    else
        log_info "Starting containers..."
        docker compose -f docker-compose-nginx.yml up -d
    fi

    log_success "Cloud deployment started"
    log_info "Frontend: http://68.233.112.202/travelai/"
    log_info "Backend:  http://68.233.112.202/travelai/api"
    log_info "Health:   http://68.233.112.202/travelai/health"

    echo ""
    log_info "Container status:"
    docker compose -f docker-compose-nginx.yml ps
}

################################################################################
# Stop Cloud
################################################################################

stop_cloud() {
    log_info "Stopping cloud deployment..."

    cd "$SCRIPT_DIR"
    docker compose -f docker-compose-nginx.yml down

    log_success "Cloud deployment stopped"
}

################################################################################
# Main
################################################################################

main() {
    local mode=""
    local target=""
    local build_flag=""

    # Parse arguments
    for arg in "$@"; do
        case $arg in
            --local)
                mode="local"
                ;;
            --cloud)
                mode="cloud"
                ;;
            --stop)
                target="stop"
                ;;
            --frontend)
                target="frontend"
                ;;
            --backend)
                target="backend"
                ;;
            --build)
                build_flag="--build"
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown argument: $arg"
                show_help
                exit 1
                ;;
        esac
    done

    # Execute based on mode and target
    if [ "$mode" = "local" ]; then
        if [ "$target" = "frontend" ]; then
            start_local_frontend
        elif [ "$target" = "backend" ]; then
            start_local_backend
        elif [ "$target" = "stop" ]; then
            stop_local
        else
            log_error "Please specify --frontend or --backend"
            show_help
            exit 1
        fi
    elif [ "$mode" = "cloud" ]; then
        if [ "$target" = "stop" ]; then
            stop_cloud
        else
            start_cloud "$build_flag"
        fi
    elif [ "$target" = "stop" ] && [ "$mode" = "" ]; then
        log_error "Please specify --local or --cloud with --stop"
        show_help
        exit 1
    else
        show_help
        exit 1
    fi
}

main "$@"
