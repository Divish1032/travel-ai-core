#!/bin/bash
#
# TravelAI Dashboard Deployment Script
# Deploys dashboard to existing webapp infrastructure
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  TravelAI Dashboard Deployment${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Get project root (2 levels up from deploy/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WEBAPP_DIR="$PROJECT_ROOT/webapp"
DASHBOARD_DIR="$PROJECT_ROOT/dashboard"

# Check if webapp exists
if [ ! -d "$WEBAPP_DIR" ]; then
    echo -e "${RED}Error: webapp directory not found at $WEBAPP_DIR${NC}"
    exit 1
fi

# Check if docker-compose-nginx.yml exists
if [ ! -f "$WEBAPP_DIR/docker-compose-nginx.yml" ]; then
    echo -e "${RED}Error: docker-compose-nginx.yml not found in $WEBAPP_DIR${NC}"
    exit 1
fi

# Check if .env exists
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo -e "${YELLOW}Warning: .env file not found at $PROJECT_ROOT/.env${NC}"
    echo -e "${YELLOW}Dashboard requires AWS credentials in .env file${NC}"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo -e "${GREEN}Step 1: Building dashboard Docker image...${NC}"
cd "$PROJECT_ROOT"
docker build -f dashboard/Dockerfile -t travelai-dashboard:latest .

echo ""
echo -e "${GREEN}Step 2: Stopping existing dashboard container (if running)...${NC}"
docker stop travelai-dashboard 2>/dev/null || echo "No existing dashboard container found"
docker rm travelai-dashboard 2>/dev/null || true

echo ""
echo -e "${GREEN}Step 3: Starting dashboard container...${NC}"
cd "$DASHBOARD_DIR"
docker-compose up -d

echo ""
echo -e "${GREEN}Step 4: Waiting for dashboard to be healthy...${NC}"
sleep 5

# Wait for health check (max 60 seconds)
TIMEOUT=60
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    if docker inspect travelai-dashboard --format='{{.State.Health.Status}}' 2>/dev/null | grep -q "healthy"; then
        echo -e "${GREEN}✓ Dashboard is healthy!${NC}"
        break
    fi
    echo -n "."
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done

if [ $ELAPSED -ge $TIMEOUT ]; then
    echo ""
    echo -e "${YELLOW}Warning: Dashboard health check timeout${NC}"
    echo -e "${YELLOW}Check logs with: docker logs travelai-dashboard${NC}"
fi

echo ""
echo -e "${GREEN}Step 5: Checking nginx configuration...${NC}"

# Check if nginx.conf has dashboard routes
if ! docker exec travelai-nginx cat /etc/nginx/nginx.conf | grep -q "upstream dashboard"; then
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}  NGINX CONFIGURATION REQUIRED${NC}"
    echo -e "${RED}========================================${NC}"
    echo ""
    echo -e "${YELLOW}The nginx.conf file needs to be updated to route /dashboard requests.${NC}"
    echo ""
    echo -e "Follow these steps:"
    echo -e "  1. Copy the updated nginx.conf:"
    echo -e "     ${BLUE}cp $DASHBOARD_DIR/deploy/nginx.conf $WEBAPP_DIR/nginx-proxy/nginx.conf${NC}"
    echo ""
    echo -e "  2. Restart nginx:"
    echo -e "     ${BLUE}cd $WEBAPP_DIR && docker-compose -f docker-compose-nginx.yml restart nginx${NC}"
    echo ""
    echo -e "  3. Verify nginx is running:"
    echo -e "     ${BLUE}docker logs travelai-nginx${NC}"
    echo ""
    echo -e "${YELLOW}Or update manually - see: $DASHBOARD_DIR/deploy/nginx.conf${NC}"
    echo ""
else
    echo -e "${GREEN}✓ Nginx configuration already has dashboard routes${NC}"

    # Restart nginx to pick up new upstream
    echo ""
    echo -e "${GREEN}Step 6: Restarting nginx...${NC}"
    cd "$WEBAPP_DIR"
    docker-compose -f docker-compose-nginx.yml restart nginx

    sleep 3

    if docker ps | grep -q travelai-nginx; then
        echo -e "${GREEN}✓ Nginx restarted successfully${NC}"
    else
        echo -e "${RED}Error: Nginx failed to restart${NC}"
        echo -e "Check logs: ${BLUE}docker logs travelai-nginx${NC}"
        exit 1
    fi
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Deployment Summary${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Dashboard Status:"
docker ps --filter name=travelai-dashboard --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""

# Get public IP
PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || echo "<YOUR_IP>")

echo -e "${GREEN}✓ Dashboard deployed successfully!${NC}"
echo ""
echo -e "Access URLs:"
echo -e "  • Dashboard: ${BLUE}http://$PUBLIC_IP/dashboard${NC}"
echo -e "  • WebApp:    ${BLUE}http://$PUBLIC_IP/travelai/${NC}"
echo ""
echo -e "Useful commands:"
echo -e "  • View logs:    ${BLUE}docker logs -f travelai-dashboard${NC}"
echo -e "  • Restart:      ${BLUE}docker-compose -f $DASHBOARD_DIR/docker-compose.yml restart${NC}"
echo -e "  • Stop:         ${BLUE}docker-compose -f $DASHBOARD_DIR/docker-compose.yml down${NC}"
echo -e "  • Rebuild:      ${BLUE}$DASHBOARD_DIR/deploy/deploy.sh${NC}"
echo ""
