# TravelAI EC2 Deployment Guide

## Server Information

- **EC2 IP**: 34.234.128.198
- **Existing Service**: FastAPI on port 3000 at root (/)
- **TravelAI Configuration**: Port 8001, route prefix `/travelai`

## Ports and Routes

### TravelAI Services

| Service | Port | Route | URL |
|---------|------|-------|-----|
| Frontend | 8001 | `/travelai` | http://34.234.128.198:8001/travelai |
| Backend API | 8001 | `/travelai/api` | http://34.234.128.198:8001/travelai/api |
| Health Check | 8001 | `/travelai/health` | http://34.234.128.198:8001/travelai/health |
| API Docs | 8001 | `/travelai/docs` | http://34.234.128.198:8001/travelai/docs |
| Traefik Dashboard | 8081 | `/` | http://34.234.128.198:8081 |

### Existing Services (Not Affected)

- Port 3000: Your existing FastAPI server

## EC2 Security Group Requirements

Ensure the following ports are open in your EC2 security group:

- **8001** - TravelAI HTTP traffic
- **8081** - Traefik dashboard
- **3000** - Your existing server (already open)

## Deployment Steps

### 1. Copy Project to EC2

```bash
# From your local machine
rsync -avz --exclude 'node_modules' --exclude '__pycache__' --exclude '.git' \
  /Users/itachi/Documents/Github/TravelAI/ \
  ubuntu@34.234.128.198:/home/ubuntu/TravelAI/
```

### 2. SSH to EC2

```bash
ssh ubuntu@34.234.128.198
```

### 3. Install Docker (if not already installed)

```bash
# Update system
sudo apt update

# Install Docker
sudo apt install -y docker.io docker-compose

# Enable Docker
sudo systemctl enable docker
sudo systemctl start docker

# Add user to docker group
sudo usermod -aG docker ubuntu

# Re-login for group changes to take effect
exit
# SSH back in
```

### 4. Navigate to Project

```bash
cd ~/TravelAI/webapp
```

### 5. Configure Environment

```bash
# Check if .env exists
ls -la .env

# If not, create from example
cp .env.example .env

# Edit with your credentials
nano .env
```

Required variables in `.env`:
```bash
# ChromaDB Configuration
CHROMADB_TENANT=your-tenant-id
CHROMADB_DATABASE=travel-ai-dev
CHROMADB_API_KEY=your-chroma-api-key

# LLM Provider
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-gemini-api-key
DEEPSEEK_API_KEY=your-deepseek-api-key

# Logging
LOG_LEVEL=INFO
```

### 6. Build and Start Services

```bash
# Build and start all services
docker compose up -d --build

# This will:
# - Build the backend Docker image
# - Build the React frontend Docker image
# - Start Traefik reverse proxy
# - Configure routing with /travelai prefix
```

### 7. Monitor Deployment

```bash
# Check service status
docker compose ps

# View logs
docker compose logs -f

# View specific service logs
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f traefik
```

### 8. Verify Deployment

```bash
# Test backend health
curl http://localhost:8001/travelai/health

# Expected response:
# {"status":"healthy","pipeline_ready":true}
```

### 9. Access the Application

Open in your browser:
- **Frontend**: http://34.234.128.198:8001/travelai
- **API Docs**: http://34.234.128.198:8001/travelai/docs
- **Health Check**: http://34.234.128.198:8001/travelai/health
- **Traefik Dashboard**: http://34.234.128.198:8081

## Traefik Routing Configuration

Traefik handles all routing with the following rules:

### Backend Routes
- Matches: `/travelai/api`, `/travelai/health`, `/travelai/docs`, `/travelai/openapi.json`
- Strips `/travelai` prefix before forwarding to FastAPI
- Priority: Higher (checked first)

### Frontend Routes
- Matches: `/travelai` and all sub-paths
- Strips `/travelai` prefix before serving React app
- Priority: Lower (checked after backend)

## Updating the Application

### Update Code

```bash
# SSH to EC2
ssh ubuntu@34.234.128.198

# Navigate to project
cd ~/TravelAI/webapp

# Pull latest changes (if using git)
git pull

# Rebuild and restart
docker compose up -d --build
```

### Update Only Frontend

```bash
docker compose up -d --build frontend
```

### Update Only Backend

```bash
docker compose up -d --build backend
```

## Stopping Services

```bash
# Stop all services
docker compose down

# Stop and remove volumes
docker compose down -v
```

## Troubleshooting

### Port Conflicts

If port 8001 or 8081 is already in use:

1. Check what's using the port:
   ```bash
   sudo lsof -i :8001
   sudo lsof -i :8081
   ```

2. Stop the conflicting service or update `docker-compose.yml` ports:
   ```yaml
   ports:
     - "DIFFERENT_PORT:80"
   ```

### Backend Not Starting

```bash
# Check logs
docker compose logs backend

# Common issues:
# - Missing .env file
# - Invalid ChromaDB credentials
# - Missing src/ directory (must be in TravelAI root)
```

### Frontend Not Loading

```bash
# Check logs
docker compose logs frontend

# Common issues:
# - Build failed (check npm dependencies)
# - API URL misconfigured in .env
```

### Routes Not Working

```bash
# Check Traefik routing
docker compose logs traefik

# Verify Traefik dashboard
# Open http://34.234.128.198:8081
# Check HTTP Routers and Services sections
```

### CORS Issues

If you see CORS errors in browser console:
- CORS is already configured in backend for all origins
- Ensure you're accessing via the correct URL with port 8001
- Check browser network tab for actual request URLs

## Maintenance

### View Logs

```bash
# All services
docker compose logs -f

# Last 100 lines
docker compose logs --tail=100

# Specific timeframe
docker compose logs --since="2024-01-20T10:00:00"
```

### Restart Services

```bash
# Restart all
docker compose restart

# Restart specific service
docker compose restart backend
```

### Clean Up

```bash
# Remove stopped containers
docker compose down

# Remove all images and volumes
docker compose down -v --rmi all

# Rebuild from scratch
docker compose up -d --build --force-recreate
```

## Performance Tips

1. **Backend**: Already uses uvicorn with optimized settings
2. **Frontend**: Vite builds optimized production bundle
3. **Caching**: RAG pipeline has caching enabled by default
4. **Memory**: Ensure EC2 instance has at least 8GB RAM

## Security Recommendations

1. **Use HTTPS**: Configure Traefik with Let's Encrypt for production
2. **Restrict Traefik Dashboard**: Remove port 8081 or add authentication
3. **Environment Variables**: Keep .env secure, never commit to git
4. **API Keys**: Rotate regularly
5. **Update Dependencies**: Keep Docker images updated

## Support

For issues:
1. Check logs: `docker compose logs -f`
2. Verify .env configuration
3. Test backend health: `curl http://localhost:8001/travelai/health`
4. Check Traefik dashboard: http://34.234.128.198:8081
