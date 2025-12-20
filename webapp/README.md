# TravelAI Web Interface

Simple web interface for testing the RAG itinerary generator.

## Prerequisites

- Docker & Docker Compose installed
- EC2 instance with ports 80 and 8080 open in security group
- ChromaDB credentials
- LLM API keys (Gemini/DeepSeek/OpenAI)

## Setup

1. **Copy environment file:**
   ```bash
   cd webapp
   cp .env.example .env
   ```

2. **Edit `.env` with your credentials:**
   - Add ChromaDB tenant, database, and API key
   - Add LLM API keys (at least one provider)
   - Set LLM_PROVIDER to your preferred provider (gemini/deepseek/openai)

3. **Build and start services:**
   ```bash
   docker-compose up -d --build
   ```

4. **Check health:**
   ```bash
   curl http://localhost/health
   ```

   Expected response:
   ```json
   {"status":"healthy","pipeline_ready":true}
   ```

5. **Access the application:**
   - **Frontend**: http://your-ec2-public-ip/
   - **Backend API**: http://your-ec2-public-ip/api/
   - **Health Check**: http://your-ec2-public-ip/health
   - **Traefik Dashboard**: http://your-ec2-public-ip:8080/

## Usage

1. Open the web interface in your browser
2. Enter a travel query in natural language
   - Example: "5 days Bangkok solo budget party"
   - Example: "romantic weekend in Phuket for couple"
   - Example: "3 days Chiang Mai family mid-range"
3. Optionally check "Skip narrative" for faster generation
4. Click "Generate Itinerary"
5. Wait 30-60 seconds for generation
6. View the formatted itinerary with metadata (cost, time, validation score)

## API Endpoints

### Generate Itinerary
```http
POST /api/generate
Content-Type: application/json

{
  "query": "5 days Bangkok solo budget party",
  "skip_narrative": false
}
```

**Response:**
```json
{
  "success": true,
  "html_output": "<h1>...</h1>",
  "metadata": {
    "cost": "$0.1234",
    "time": "45.2s",
    "validation_score": "0.95",
    "entities_used": 15
  }
}
```

### Health Check
```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "pipeline_ready": true
}
```

## Architecture

The application consists of three Docker services:

1. **Traefik** (Reverse Proxy)
   - Routes `/api` requests to backend
   - Routes `/` requests to frontend
   - Provides dashboard on port 8080

2. **Backend** (FastAPI)
   - Wraps RAGPipeline for itinerary generation
   - Handles API requests
   - Returns HTML-formatted itineraries

3. **Frontend** (Nginx)
   - Serves static HTML/CSS/JS
   - Simple form-based interface
   - Real-time loading feedback

## Stopping Services

```bash
docker-compose down
```

To also remove volumes:
```bash
docker-compose down -v
```

## Viewing Logs

```bash
# All services
docker-compose logs -f

# Backend only
docker-compose logs -f backend

# Frontend only
docker-compose logs -f frontend

# Traefik only
docker-compose logs -f traefik
```

## Troubleshooting

### Backend not starting

**Symptoms**: Backend container keeps restarting or exits immediately

**Solutions**:
- Check `.env` file has all required variables
- Verify ChromaDB credentials are correct
- Check logs: `docker-compose logs backend`
- Ensure ChromaDB is accessible from EC2 instance

### Generation failing

**Symptoms**: API returns 500 error or generation times out

**Solutions**:
- Verify ChromaDB connection: `curl http://localhost/health`
- Check API keys are valid and have quota remaining
- Review backend logs for specific errors
- Try with `skip_narrative: true` for faster generation
- Check if entity data exists in ChromaDB

### Frontend not accessible

**Symptoms**: Cannot reach web interface on port 80

**Solutions**:
- Check EC2 security group has port 80 open
- Verify Traefik is running: `docker-compose ps`
- Check Traefik dashboard at port 8080
- Review Traefik logs: `docker-compose logs traefik`

### CORS errors in browser

**Symptoms**: Browser console shows CORS policy errors

**Solutions**:
- Verify backend CORS middleware is enabled (already configured)
- Clear browser cache
- Try accessing from same domain/IP

### Slow generation times

**Symptoms**: Itinerary generation takes > 60 seconds

**Solutions**:
- Enable "Skip narrative" option (reduces time by 30-50%)
- Check network latency to ChromaDB
- Verify LLM API response times
- Consider upgrading EC2 instance type for more memory/CPU

### Out of memory errors

**Symptoms**: Backend crashes with OOM errors

**Solutions**:
- Ensure EC2 instance has at least 8GB RAM
- Reduce concurrent requests
- Monitor memory: `docker stats`

## Performance Notes

- **First request**: Takes longer due to pipeline initialization (~10-15s extra)
- **Typical generation**: 30-60 seconds depending on query complexity
- **With skip_narrative**: 15-30 seconds
- **Caching**: Enabled by default for faster repeated queries
- **Memory usage**: Embedding model uses ~4GB RAM

## Security Considerations

- Keep `.env` file secure and never commit to git
- Use HTTPS in production (configure Traefik with Let's Encrypt)
- Restrict API access with authentication if needed
- Keep API keys rotated regularly
- Monitor usage and costs

## Deployment to EC2

1. **SSH into EC2 instance:**
   ```bash
   ssh -i your-key.pem ubuntu@your-ec2-ip
   ```

2. **Install Docker and Docker Compose:**
   ```bash
   sudo apt update
   sudo apt install -y docker.io docker-compose
   sudo systemctl enable docker
   sudo usermod -aG docker ubuntu
   ```

3. **Clone repository:**
   ```bash
   git clone https://github.com/your-repo/TravelAI.git
   cd TravelAI/webapp
   ```

4. **Configure environment:**
   ```bash
   cp .env.example .env
   nano .env  # Edit with your credentials
   ```

5. **Start services:**
   ```bash
   docker-compose up -d --build
   ```

6. **Verify deployment:**
   ```bash
   curl http://localhost/health
   ```

7. **Access from browser:**
   - Open http://your-ec2-public-ip/

## Support

For issues or questions:
- Check logs first: `docker-compose logs`
- Review this README's troubleshooting section
- Check ChromaDB and LLM API status
- Verify all environment variables are set correctly
