# TravelAI Web Interface

Web interface for TravelAI itinerary generator with local and cloud deployment options.

---

## Quick Start

### Local Development

```bash
cd webapp

# Terminal 1: Start backend
./deploy.sh --local --backend

# Terminal 2: Start frontend
./deploy.sh --local --frontend
```

Access:
- Frontend: http://localhost:5173
- Backend: http://localhost:8001
- API Docs: http://localhost:8001/docs

### Cloud Production

```bash
cd webapp

# Deploy to cloud
./deploy.sh --cloud

# Or rebuild and deploy
./deploy.sh --cloud --build
```

Access at: http://your-server-ip/travelai/

---

## Configuration

### Environment Setup

1. Copy example env file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your credentials:
   ```bash
   # ChromaDB
   CHROMADB_TENANT=your-tenant-id
   CHROMADB_DATABASE=your-database
   CHROMADB_API_KEY=your-api-key

   # LLM API Keys
   GEMINI_API_KEY=your-key
   DEEPSEEK_API_KEY=your-key
   ```

---

## Commands

### Local Mode

```bash
# Start frontend dev server
./deploy.sh --local --frontend

# Start backend dev server
./deploy.sh --local --backend

# Stop all local servers
./deploy.sh --stop --local
```

### Cloud Mode

```bash
# Start Docker containers
./deploy.sh --cloud

# Start with rebuild
./deploy.sh --cloud --build

# Stop Docker containers
./deploy.sh --stop --cloud

# View logs
docker compose -f docker-compose-nginx.yml logs -f

# Check status
docker compose -f docker-compose-nginx.yml ps
```

---

## Troubleshooting

### Local: Backend won't start

```bash
# Kill existing process
pkill -f "uvicorn.*app.main:app"

# Try again
./deploy.sh --local --backend
```

### Local: Frontend won't start

```bash
# Kill existing process
pkill -f "vite"

# Reinstall dependencies
cd frontend-react
rm -rf node_modules
npm install

# Try again
cd ..
./deploy.sh --local --frontend
```

### Cloud: Check container logs

```bash
docker logs travelai-backend --tail 100
docker logs travelai-frontend --tail 100
docker logs travelai-nginx --tail 100
```

### Cloud: Restart containers

```bash
docker compose -f docker-compose-nginx.yml restart backend
docker compose -f docker-compose-nginx.yml restart frontend
```

---

## API Endpoints

### Generate Itinerary

```bash
POST /travelai/api/generate
Content-Type: application/json

{
  "query": "5 days Bangkok solo budget party",
  "skip_narrative": false
}
```

### Health Check

```bash
GET /travelai/health
```

---

## Cloud Server (Oracle)

**Server IP:** 68.233.112.202

**Deployment:**
```bash
ssh ubuntu@68.233.112.202
cd /home/ubuntu/work/travel-ai-core/webapp
./deploy.sh --cloud --build
```

**Access:**
- Frontend: http://68.233.112.202/travelai/
- Backend: http://68.233.112.202/travelai/api
- Health: http://68.233.112.202/travelai/health
- Docs: http://68.233.112.202/travelai/docs

---

## Help

```bash
./deploy.sh --help
```
