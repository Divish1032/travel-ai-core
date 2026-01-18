# TravelAI Dashboard - Oracle Cloud Deployment Guide

Deploy the TravelAI Streamlit dashboard on Oracle Cloud Ubuntu instance using the existing webapp infrastructure.

## Overview

The dashboard integrates with your existing webapp deployment:
- Uses the same `travelai-network` Docker network
- Routes through the existing Nginx reverse proxy
- Accessible at `http://<PUBLIC_IP>/dashboard`
- No additional port exposure needed

## Prerequisites

- Oracle Cloud Ubuntu instance with Docker and Docker Compose installed
- Existing webapp services running (backend, frontend, nginx)
- `.env` file with AWS credentials for S3 access
- Git repository cloned on server

## Quick Deployment

```bash
# From your Oracle Cloud server
cd ~/TravelAI/dashboard
./deploy/deploy.sh
```

That's it! The script will handle everything automatically.

## Manual Deployment Steps

If you prefer manual deployment or need to troubleshoot:

### Step 1: Update Nginx Configuration

Copy the updated nginx.conf that includes dashboard routes:

```bash
cd ~/TravelAI
cp dashboard/deploy/nginx.conf webapp/nginx-proxy/nginx.conf
```

### Step 2: Build Dashboard Image

```bash
cd ~/TravelAI
docker build -f dashboard/Dockerfile -t travelai-dashboard:latest .
```

### Step 3: Start Dashboard Container

```bash
cd ~/TravelAI/dashboard
docker-compose up -d
```

### Step 4: Restart Nginx

```bash
cd ~/TravelAI/webapp
docker-compose -f docker-compose-nginx.yml restart nginx
```

### Step 5: Verify Deployment

```bash
# Check all containers are running
docker ps

# You should see:
# - travelai-nginx (port 80)
# - travelai-backend
# - travelai-frontend
# - travelai-dashboard (new!)

# Check dashboard logs
docker logs travelai-dashboard

# Test dashboard health
curl http://localhost:8501/_stcore/health
```

## Access the Dashboard

Open your browser to:
```
http://<YOUR_PUBLIC_IP>/dashboard
```

Example: `http://68.233.112.202/dashboard`

## What's Deployed

### Docker Services

**Dashboard Container:**
- Name: `travelai-dashboard`
- Internal Port: 8501
- Network: `travelai-network`
- Auto-restart: Yes
- Health check: Every 30s

**Network Topology:**
```
Internet (Port 80)
    ↓
travelai-nginx (Reverse Proxy)
    ├─→ /travelai/api     → backend:8000
    ├─→ /travelai/        → frontend:80
    └─→ /dashboard        → dashboard:8501 (NEW!)
```

### Files Created

```
dashboard/
├── Dockerfile                    # Dashboard container definition
├── docker-compose.yml            # Dashboard service config
├── .dockerignore                 # Build exclusions
├── .streamlit/
│   └── config.toml              # Streamlit server config
└── deploy/
    ├── deploy.sh                # Automated deployment script
    ├── nginx.conf               # Updated nginx config with dashboard routes
    └── DEPLOYMENT.md            # This file
```

## Configuration

### Environment Variables

Dashboard requires these AWS credentials in `.env`:

```bash
# Required for dashboard
AWS_ACCESS_KEY_ID=<your_key>
AWS_SECRET_ACCESS_KEY=<your_secret>
AWS_REGION=us-east-1
S3_BUCKET_NAME=travel-ai-data-divyansh-2025

# Optional - not needed for dashboard
YOUTUBE_API_KEY=placeholder
GEMINI_API_KEY=placeholder
```

### Nginx Routing

The updated nginx.conf adds these routes:

```nginx
# Dashboard upstream
upstream dashboard {
    server dashboard:8501;
}

# Dashboard routes
location /dashboard {
    proxy_pass http://dashboard:8501/dashboard;
    # WebSocket support
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}

location /dashboard/_stcore {
    proxy_pass http://dashboard:8501/dashboard/_stcore;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

## Container Management

### Useful Commands

```bash
# View all containers
docker ps -a

# View dashboard logs
docker logs -f travelai-dashboard

# Restart dashboard only
docker-compose -f ~/TravelAI/dashboard/docker-compose.yml restart

# Stop dashboard
docker-compose -f ~/TravelAI/dashboard/docker-compose.yml down

# Rebuild after code changes
cd ~/TravelAI/dashboard
./deploy/deploy.sh

# Check dashboard health
docker inspect travelai-dashboard --format='{{.State.Health.Status}}'

# Access dashboard container shell
docker exec -it travelai-dashboard /bin/bash
```

### Restart Everything

```bash
# Restart all services (nginx, backend, frontend, dashboard)
cd ~/TravelAI/webapp
docker-compose -f docker-compose-nginx.yml restart

cd ~/TravelAI/dashboard
docker-compose restart
```

## Updating the Dashboard

When you push code changes:

```bash
# On the server
cd ~/TravelAI
git pull origin main
./dashboard/deploy/deploy.sh
```

The deploy script will:
1. Rebuild the dashboard image
2. Stop the old container
3. Start a new container
4. Restart nginx
5. Verify health

## Troubleshooting

### Dashboard won't start

```bash
# Check logs for errors
docker logs travelai-dashboard

# Common issues:
# 1. Missing .env file
# 2. Invalid AWS credentials
# 3. Port 8501 already in use
```

### Can't access /dashboard

```bash
# 1. Check nginx is running
docker ps | grep nginx

# 2. Check nginx logs
docker logs travelai-nginx

# 3. Verify nginx.conf has dashboard routes
docker exec travelai-nginx cat /etc/nginx/nginx.conf | grep dashboard

# 4. Test locally first
curl http://localhost/dashboard
```

### Dashboard shows errors

```bash
# 1. Verify S3 credentials
docker exec travelai-dashboard env | grep AWS

# 2. Check S3 bucket exists and is accessible
docker exec travelai-dashboard python -c "from src.storage.s3 import S3Storage; s = S3Storage(); print(s.bucket_name)"

# 3. Check network connectivity
docker exec travelai-dashboard ping -c 3 s3.amazonaws.com
```

### Nginx won't restart

```bash
# Test nginx configuration
docker exec travelai-nginx nginx -t

# If config is invalid, check syntax
cat ~/TravelAI/webapp/nginx-proxy/nginx.conf

# Restore original if needed
cd ~/TravelAI/webapp
docker-compose -f docker-compose-nginx.yml down
docker-compose -f docker-compose-nginx.yml up -d
```

### Network issues

```bash
# Check network exists
docker network ls | grep travelai-network

# If missing, recreate from webapp
cd ~/TravelAI/webapp
docker-compose -f docker-compose-nginx.yml down
docker-compose -f docker-compose-nginx.yml up -d

# Then restart dashboard
cd ~/TravelAI/dashboard
docker-compose down
docker-compose up -d
```

## Performance Optimization

### Oracle Cloud Free Tier

Dashboard resource usage:
- Memory: ~300-500MB
- CPU: Low (spikes during S3 fetches)
- Network: S3 API calls

If running on Oracle Cloud free tier (1GB RAM):
- Monitor with `docker stats`
- Consider upgrading instance if memory issues occur
- Dashboard uses parallel fetching (20 workers) - very efficient

### Caching

Dashboard uses aggressive caching:
- Metadata: 10 min TTL
- Entities: 20 min TTL
- Subsequent page loads are <1 second

To clear cache, restart container:
```bash
docker-compose -f ~/TravelAI/dashboard/docker-compose.yml restart
```

## Security

### Current Setup

- Dashboard runs in isolated Docker network
- Only Nginx (port 80) is publicly exposed
- Dashboard not directly accessible from internet
- S3 credentials stored in .env (mode 600)

### Recommendations

1. **Restrict Dashboard Access** (optional):
   ```nginx
   # Add to nginx.conf dashboard location
   allow 1.2.3.4;  # Your IP
   deny all;
   ```

2. **Use HTTPS** (future enhancement):
   - Get domain name
   - Use Let's Encrypt SSL certificate
   - Update nginx to listen on 443

3. **Firewall**:
   ```bash
   # Only port 80 and 22 should be open
   sudo ufw status
   ```

## Monitoring

### Health Checks

Dashboard includes automatic health checks:
- Interval: Every 30 seconds
- Timeout: 10 seconds
- Retries: 3 before marking unhealthy

```bash
# Check health status
docker inspect travelai-dashboard --format='{{.State.Health.Status}}'

# View health check logs
docker inspect travelai-dashboard --format='{{json .State.Health}}'
```

### Logs

```bash
# View recent logs
docker logs --tail=100 travelai-dashboard

# Follow logs in real-time
docker logs -f travelai-dashboard

# View only errors
docker logs travelai-dashboard 2>&1 | grep -i error
```

## Cost Considerations

- **Oracle Cloud**: Free tier covers this deployment
- **Docker**: No additional cost
- **Network**: Free 10TB outbound/month
- **S3 Access**: AWS charges apply for cross-region data transfer

## Additional Resources

- Streamlit docs: https://docs.streamlit.io
- Docker compose docs: https://docs.docker.com/compose/
- Nginx proxy docs: https://nginx.org/en/docs/http/ngx_http_proxy_module.html

## Support

For issues:
1. Check logs first
2. Review troubleshooting section
3. Verify all containers are running
4. Test each component separately
