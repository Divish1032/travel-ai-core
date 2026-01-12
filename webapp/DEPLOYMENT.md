# TravelAI Production Deployment Guide

## 🌐 Server Information

- **Public IP**: `68.233.112.202`
- **Platform**: Oracle Cloud Ubuntu
- **Docker**: v29.1.3
- **Docker Compose**: v5.0.0

## 📍 Access URLs

| Service | URL | Purpose |
|---------|-----|---------|
| **Frontend (React)** | http://68.233.112.202/travelai/ | User interface |
| **Backend API** | http://68.233.112.202/travelai/api | REST API endpoint |
| **Health Check** | http://68.233.112.202/travelai/health | Service health status |
| **API Documentation** | http://68.233.112.202/travelai/docs | Interactive Swagger UI |
| **ReDoc** | http://68.233.112.202/travelai/redoc | Alternative API docs |
| **OpenAPI JSON** | http://68.233.112.202/travelai/openapi.json | OpenAPI schema |

---

## 🏗️ Architecture

### Services Stack

```
Internet (Port 80)
    ↓
Nginx Reverse Proxy (travelai-nginx)
    ├─→ Backend API (travelai-backend:8000)
    │   └─→ FastAPI + RAG Pipeline
    │       ├─→ ChromaDB Cloud (2,254 entities)
    │       ├─→ Gemini API (primary LLM)
    │       ├─→ DeepSeek API (fallback LLM)
    │       └─→ gte-large-en-v1.5 (embeddings)
    └─→ Frontend (travelai-frontend:80)
        └─→ React + Vite (static files)
```

### Docker Containers

| Container | Image | Port | Status | Health Check |
|-----------|-------|------|--------|--------------|
| `travelai-nginx` | nginx:alpine | 80 | Running | wget /health |
| `travelai-backend` | webapp-backend | 8000 | Healthy | curl /health |
| `travelai-frontend` | webapp-frontend | 80 | Running | wget / |

---

## 🚀 Deployment Steps

### 1. Prerequisites

Ensure you have access to the server:

```bash
ssh ubuntu@68.233.112.202
```

### 2. Navigate to Project

```bash
cd /home/ubuntu/work/travel-ai-core/webapp
```

### 3. Configure Environment Variables

Verify `.env` file exists with all required credentials:

```bash
cat .env
```

**Required variables:**

```bash
# AWS Configuration (required by config.py, not used for webapp)
AWS_ACCESS_KEY_ID=dummy_key
AWS_SECRET_ACCESS_KEY=dummy_secret
AWS_REGION=us-east-1
S3_BUCKET_NAME=travel-ai-data

# ChromaDB Cloud Configuration
CHROMADB_TENANT=7d36fa79-75b1-4fd6-af47-953dd1b5d16f
CHROMADB_DATABASE=travel-ai-dev
CHROMADB_API_KEY=ck-3EGr9csTHwFvaFrYbBz3ChpANQCTYJwbtufmKYyka8He

# LLM Provider Configuration
LLM_PROVIDER=gemini
GEMINI_API_KEY=AIzaSyBsapvn8ryIofJyIZE5CBjxVAk9P7adWoM
DEEPSEEK_API_KEY=sk-378173b30c554d7a89ebc78023c7b1ed

# Logging
LOG_LEVEL=INFO
```

### 4. Build and Deploy

**Full deployment (all services):**

```bash
docker compose -f docker-compose-nginx.yml up -d --build
```

**Rebuild specific service:**

```bash
# Backend only
docker compose -f docker-compose-nginx.yml build backend
docker compose -f docker-compose-nginx.yml up -d backend

# Frontend only
docker compose -f docker-compose-nginx.yml build frontend
docker compose -f docker-compose-nginx.yml up -d frontend

# Nginx only (for config changes)
docker compose -f docker-compose-nginx.yml restart nginx
```

### 5. Monitor Deployment

```bash
# Check container status
docker compose -f docker-compose-nginx.yml ps

# View logs (all services)
docker compose -f docker-compose-nginx.yml logs -f

# View specific service logs
docker compose -f docker-compose-nginx.yml logs -f backend
docker compose -f docker-compose-nginx.yml logs -f frontend
docker compose -f docker-compose-nginx.yml logs -f nginx

# Check last 100 lines
docker compose -f docker-compose-nginx.yml logs --tail=100
```

### 6. Verify Deployment

```bash
# Local verification
curl http://localhost/travelai/health

# Expected response:
# {"status":"healthy","pipeline_ready":true,"service":"travelai-backend"}

# Test API generation
curl -X POST http://localhost/travelai/api/generate \
  -H "Content-Type: application/json" \
  -d '{"query": "2 days Bangkok budget", "skip_narrative": true}'
```

**External verification (from your local machine):**

```bash
# Health check
curl http://68.233.112.202/travelai/health

# Frontend
curl -I http://68.233.112.202/travelai/

# API docs
curl -I http://68.233.112.202/travelai/docs
```

---

## ⚙️ Configuration Details

### Nginx Reverse Proxy

**File**: `webapp/nginx-proxy/nginx.conf`

**Key configurations:**

1. **API Timeout** - Supports 10-minute API responses:
   ```nginx
   proxy_connect_timeout 600s;
   proxy_send_timeout 600s;
   proxy_read_timeout 600s;
   ```

2. **CORS Headers** - Allow cross-origin requests:
   ```nginx
   add_header Access-Control-Allow-Origin "*" always;
   add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS" always;
   add_header Access-Control-Allow-Headers "Content-Type, Authorization, X-Requested-With" always;
   ```

3. **Security Headers**:
   ```nginx
   add_header X-Frame-Options "SAMEORIGIN" always;
   add_header X-Content-Type-Options "nosniff" always;
   add_header X-XSS-Protection "1; mode=block" always;
   ```

### Frontend Configuration

**File**: `webapp/frontend-react/vite.config.js`

**Base path configuration:**
```javascript
base: '/travelai/',  // Ensures correct asset paths
```

**File**: `webapp/frontend-react/nginx.conf`

- Serves React app at `/travelai/` path
- Caches static assets for 1 year
- Falls back to `index.html` for SPA routing

### Backend Configuration

**File**: `webapp/backend/app/main.py`

**Root path configuration:**
```python
app = FastAPI(
    title="TravelAI Itinerary Generator API",
    description="Generate personalized travel itineraries using RAG pipeline",
    version="1.0.0",
    root_path="/travelai"  # Tells FastAPI about the path prefix
)
```

**Key features:**
- ChromaDB Cloud integration (2,254 entities, 145 profile consensus, 646 experiences)
- Gemini API (primary) + DeepSeek (fallback) for LLM operations
- Free local embedding model (gte-large-en-v1.5)
- Pipeline caching enabled
- Cost tracking per request (~$0.0006 per itinerary)
- Generation time: 45-60 seconds (without narrative), 8-10 minutes (with narrative)

---

## 🔥 Firewall Configuration

### Oracle Cloud Security List

**Required ingress rules:**

| Protocol | Port | Source CIDR | Description |
|----------|------|-------------|-------------|
| TCP | 80 | 0.0.0.0/0 | HTTP - TravelAI webapp |
| TCP | 443 | 0.0.0.0/0 | HTTPS (optional, for future SSL) |
| TCP | 22 | 0.0.0.0/0 | SSH (restrict to your IP) |

**How to configure:**

1. Login to Oracle Cloud Console: https://cloud.oracle.com
2. Navigate: **Compute** → **Instances** → Click your instance
3. Click on **Subnet** link under "Primary VNIC Information"
4. Click **Security Lists** → **Default Security List**
5. Click **Add Ingress Rules**
6. Add rule for port 80:
   - Source Type: CIDR
   - Source CIDR: `0.0.0.0/0`
   - IP Protocol: TCP
   - Destination Port Range: `80`
   - Description: `HTTP - TravelAI Webapp`

### Local iptables (Already Configured)

Current rules:
```bash
sudo iptables -L INPUT -n --line-numbers

# Port 80 and 443 rules are placed BEFORE the REJECT rule
# Rules are saved permanently via netfilter-persistent
```

**To verify:**
```bash
sudo iptables -L INPUT -n -v --line-numbers | grep "dpt:80"
```

**Rules are persisted** and will survive reboots.

---

## 🔄 Common Operations

### Restart Services

```bash
# Restart all services
docker compose -f docker-compose-nginx.yml restart

# Restart specific service
docker compose -f docker-compose-nginx.yml restart backend
docker compose -f docker-compose-nginx.yml restart frontend
docker compose -f docker-compose-nginx.yml restart nginx
```

### Stop Services

```bash
# Stop all services (containers remain)
docker compose -f docker-compose-nginx.yml stop

# Stop and remove containers
docker compose -f docker-compose-nginx.yml down

# Stop and remove everything (including volumes)
docker compose -f docker-compose-nginx.yml down -v
```

### Update Application

```bash
# 1. Pull latest code (if using git)
cd /home/ubuntu/work/travel-ai-core
git pull

# 2. Rebuild and restart
cd webapp
docker compose -f docker-compose-nginx.yml up -d --build

# 3. Verify
docker compose -f docker-compose-nginx.yml ps
curl http://localhost/travelai/health
```

### View Container Details

```bash
# Container status
docker compose -f docker-compose-nginx.yml ps

# Resource usage
docker stats

# Inspect specific container
docker inspect travelai-backend

# Execute command in container
docker exec -it travelai-backend bash

# Check environment variables
docker exec travelai-backend env | grep GEMINI
```

---

## 🐛 Troubleshooting

### Issue: API Timeout After 60 Seconds

**Symptom**: API requests fail with timeout error after ~60 seconds

**Solution**: Already fixed. Nginx proxy timeout set to 600 seconds (10 minutes)

**Verify:**
```bash
docker exec travelai-nginx grep "proxy_.*_timeout" /etc/nginx/nginx.conf
```

### Issue: Frontend Shows White Page / 404 for Assets

**Symptom**:
```
GET http://68.233.112.202/assets/index-BTSUOMv3.js net::ERR_ABORTED 404
```

**Solution**: Already fixed. Vite `base` path set to `/travelai/`

**Verify:**
```bash
curl -I http://localhost/travelai/assets/index-BTSUOMv3.js
# Should return: HTTP/1.1 200 OK
```

### Issue: Backend Not Healthy

**Check logs:**
```bash
docker compose -f docker-compose-nginx.yml logs backend --tail=100
```

**Common causes:**
1. Missing environment variables (check `.env` file)
2. ChromaDB connection failure (verify API key)
3. LLM API key invalid (check Gemini/DeepSeek keys)
4. Port 8000 already in use

**Fix:**
```bash
# Restart backend
docker compose -f docker-compose-nginx.yml restart backend

# Rebuild if code changed
docker compose -f docker-compose-nginx.yml build backend
docker compose -f docker-compose-nginx.yml up -d backend
```

### Issue: Cannot Access from Internet

**Check Oracle Cloud Security List:**
```bash
# Test from server (should work)
curl http://localhost/travelai/health

# Test from internet
curl http://68.233.112.202/travelai/health
```

If local works but external doesn't:
1. Check Oracle Cloud Security List (see Firewall Configuration section)
2. Verify port 80 is open in iptables
3. Check nginx is listening on 0.0.0.0:80

```bash
ss -tlnp | grep :80
# Should show: 0.0.0.0:80 (not 127.0.0.1:80)
```

### Issue: API Documentation Shows "Failed to load API definition"

**Solution**: Already fixed. FastAPI `root_path` set to `/travelai`

**Verify:**
```bash
curl http://localhost/travelai/openapi.json | jq '.servers'
# Should show: [{"url": "/travelai"}]
```

### Issue: CORS Errors in Browser Console

**Check CORS headers:**
```bash
curl -I -X OPTIONS http://localhost/travelai/api/generate \
  -H "Origin: http://68.233.112.202" \
  -H "Access-Control-Request-Method: POST"
```

Should return:
```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
```

**If missing:** Restart nginx to apply CORS configuration

### Issue: Nginx Container Unhealthy

**Check nginx configuration:**
```bash
# Test config syntax
docker exec travelai-nginx nginx -t

# View error logs
docker logs travelai-nginx --tail=50
```

**Common causes:**
1. Syntax error in nginx.conf
2. Backend/frontend containers not reachable
3. Port conflicts

**Fix:**
```bash
# Restart nginx
docker compose -f docker-compose-nginx.yml restart nginx

# If config changed, rebuild
docker compose -f docker-compose-nginx.yml build nginx
docker compose -f docker-compose-nginx.yml up -d nginx
```

---

## 📊 Performance & Monitoring

### Performance Metrics

| Metric | Value | Notes |
|--------|-------|-------|
| **API Response Time** | 45-60 seconds | Without narrative |
| **API Response Time** | 8-10 minutes | With narrative |
| **Cost per Itinerary** | ~$0.0006 | Using Gemini Flash |
| **ChromaDB Entities** | 2,254 | Bangkok travel data |
| **Memory Usage** | ~2GB | Backend container |
| **CPU Usage** | Low | Mostly I/O bound (API calls) |

### Cost Tracking

API costs per request phase:
- Intent parsing: ~$0.0001
- Re-ranking: ~$0.0015
- Generation: ~$0.0025
- Validation: ~$0.0008
- Narrative: ~$0.0035 (if enabled)

**Total:** $0.005-0.008 per itinerary

### Health Checks

```bash
# Backend health
curl http://localhost/travelai/health

# Frontend health
curl http://localhost/health  # Nginx health
docker exec travelai-frontend wget -q -O - http://localhost/health

# Check all containers
docker compose -f docker-compose-nginx.yml ps
```

### Log Monitoring

```bash
# Tail all logs
docker compose -f docker-compose-nginx.yml logs -f

# Filter for errors
docker compose -f docker-compose-nginx.yml logs | grep -i error

# Check specific timeframe
docker compose -f docker-compose-nginx.yml logs --since="2026-01-12T10:00:00"

# Export logs to file
docker compose -f docker-compose-nginx.yml logs > deployment-logs.txt
```

---

## 🔒 Security Hardening

### Current Security Measures

✅ **Implemented:**
- [x] Security headers (X-Frame-Options, X-Content-Type-Options, X-XSS-Protection)
- [x] CORS configuration
- [x] Environment variables for secrets (not hardcoded)
- [x] Health check endpoints (no sensitive info exposed)
- [x] Firewall rules (Oracle Cloud + iptables)
- [x] Docker container isolation
- [x] Non-root user in containers (where applicable)

### Recommended Production Enhancements

🔐 **High Priority:**

1. **Enable HTTPS with SSL/TLS:**
   ```bash
   # Install certbot
   sudo apt install certbot python3-certbot-nginx

   # Get certificate (requires domain name)
   sudo certbot --nginx -d yourdomain.com
   ```

2. **Restrict CORS origins:**
   - Update `webapp/nginx-proxy/nginx.conf`
   - Change `Access-Control-Allow-Origin: *` to your domain

3. **Add authentication for API:**
   - Implement API key authentication
   - Or use OAuth2/JWT tokens

4. **Environment variable security:**
   ```bash
   # Restrict .env permissions
   chmod 600 /home/ubuntu/work/travel-ai-core/webapp/.env

   # Never commit .env to git
   echo ".env" >> .gitignore
   ```

5. **Regular updates:**
   ```bash
   # Update Docker images
   docker compose -f docker-compose-nginx.yml pull
   docker compose -f docker-compose-nginx.yml up -d

   # Update system
   sudo apt update && sudo apt upgrade -y
   ```

⚠️ **Medium Priority:**

1. **Rate limiting** - Add nginx rate limiting for API endpoints
2. **Monitoring** - Set up monitoring (Prometheus, Grafana, or cloud service)
3. **Backup strategy** - Regular backups of configuration and data
4. **Log rotation** - Configure Docker log rotation
5. **SSH hardening** - Disable password auth, use key-only

📋 **Low Priority:**

1. **Container security scanning** - Use tools like Trivy or Clair
2. **Network segmentation** - Isolate containers in separate networks
3. **Secret management** - Use Docker Secrets or Vault
4. **Web Application Firewall (WAF)** - Add Cloudflare or AWS WAF

---

## 📝 Maintenance Schedule

### Daily
- Check container health: `docker compose -f docker-compose-nginx.yml ps`
- Monitor logs for errors: `docker compose -f docker-compose-nginx.yml logs --tail=100 | grep -i error`

### Weekly
- Review resource usage: `docker stats`
- Check disk space: `df -h`
- Review API usage and costs

### Monthly
- Update Docker images
- Review and rotate API keys if needed
- Check for security updates: `sudo apt update && apt list --upgradable`
- Backup configuration files

### Quarterly
- Full security audit
- Review and update dependencies
- Performance optimization review

---

## 🆘 Emergency Procedures

### Complete Service Failure

```bash
# 1. Stop everything
docker compose -f docker-compose-nginx.yml down

# 2. Check for conflicts
sudo lsof -i :80
docker ps -a

# 3. Clean up
docker system prune -a --volumes  # WARNING: Removes all unused Docker data

# 4. Rebuild from scratch
cd /home/ubuntu/work/travel-ai-core/webapp
docker compose -f docker-compose-nginx.yml up -d --build --force-recreate

# 5. Verify
docker compose -f docker-compose-nginx.yml ps
curl http://localhost/travelai/health
```

### Rollback to Previous Version

```bash
# If using git
cd /home/ubuntu/work/travel-ai-core
git log --oneline -n 10  # Find previous commit
git checkout <commit-hash>

# Rebuild
cd webapp
docker compose -f docker-compose-nginx.yml up -d --build

# Test
curl http://localhost/travelai/health
```

### Data Corruption / ChromaDB Issues

```bash
# Backend will automatically reconnect to ChromaDB Cloud
# No local data to corrupt

# Check ChromaDB connection
docker compose -f docker-compose-nginx.yml logs backend | grep -i chromadb

# If needed, restart backend
docker compose -f docker-compose-nginx.yml restart backend
```

---

## 📚 Additional Resources

### Documentation
- **Main README**: `/home/ubuntu/work/travel-ai-core/README.md`
- **API Documentation**: http://68.233.112.202/travelai/docs
- **Types & Assumptions**: `/home/ubuntu/work/travel-ai-core/docs/TYPES_AND_ASSUMPTIONS.md`
- **Production Runbook**: `/home/ubuntu/work/travel-ai-core/docs/PRODUCTION_RUNBOOK.md`

### Configuration Files
- **Nginx Proxy**: `/home/ubuntu/work/travel-ai-core/webapp/nginx-proxy/nginx.conf`
- **Frontend Nginx**: `/home/ubuntu/work/travel-ai-core/webapp/frontend-react/nginx.conf`
- **Docker Compose**: `/home/ubuntu/work/travel-ai-core/webapp/docker-compose-nginx.yml`
- **Environment**: `/home/ubuntu/work/travel-ai-core/webapp/.env`
- **Backend App**: `/home/ubuntu/work/travel-ai-core/webapp/backend/app/main.py`

### Key Directories
```
/home/ubuntu/work/travel-ai-core/
├── docs/                           # Documentation
├── src/                            # Core TravelAI source code
├── webapp/                         # Web application
│   ├── backend/                    # FastAPI backend
│   │   ├── app/main.py            # Main API application
│   │   └── Dockerfile             # Backend container config
│   ├── frontend-react/            # React frontend
│   │   ├── src/                   # React components
│   │   ├── vite.config.js         # Vite configuration
│   │   ├── nginx.conf             # Frontend nginx config
│   │   └── Dockerfile             # Frontend container config
│   ├── nginx-proxy/               # Reverse proxy
│   │   └── nginx.conf             # Main nginx config
│   ├── docker-compose-nginx.yml   # Production compose file
│   └── .env                       # Environment variables (SECRET)
```

---

## ✅ Production Readiness Checklist

- [x] **Docker containers running** (backend, frontend, nginx)
- [x] **Environment variables configured** (.env file with API keys)
- [x] **Firewall configured** (Oracle Cloud Security List + iptables)
- [x] **API timeout increased** (600 seconds for long-running requests)
- [x] **Frontend assets loading** (correct base path `/travelai/`)
- [x] **Health checks working** (all services respond to health endpoints)
- [x] **CORS configured** (frontend can call backend API)
- [x] **API documentation accessible** (Swagger UI + ReDoc)
- [x] **Security headers enabled** (X-Frame-Options, XSS protection, etc.)
- [x] **External access verified** (accessible from internet)
- [x] **Logs accessible** (Docker logs viewable)
- [x] **Restart policy configured** (containers auto-restart on failure)
- [x] **ChromaDB connected** (2,254 entities indexed)
- [x] **LLM APIs working** (Gemini + DeepSeek)
- [ ] **HTTPS/SSL** (recommended for production, requires domain)
- [ ] **Monitoring** (recommended: Prometheus, Grafana, or cloud service)
- [ ] **Backups** (configuration files, environment variables)
- [ ] **Rate limiting** (recommended for public API)

---

## 📞 Support & Contact

For issues or questions:

1. **Check logs first:**
   ```bash
   docker compose -f docker-compose-nginx.yml logs -f
   ```

2. **Test health endpoints:**
   ```bash
   curl http://localhost/travelai/health
   ```

3. **Review this documentation** for common issues and solutions

4. **Container information:**
   ```bash
   docker compose -f docker-compose-nginx.yml ps
   docker stats
   ```

---

**Last Updated:** January 12, 2026
**Version:** 1.0.0 - Production
**Deployment Status:** ✅ LIVE & OPERATIONAL
