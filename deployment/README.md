# ChromaDB Cloud Deployment Guide

This guide explains how to deploy ChromaDB to a cloud server for production use with TravelAI.

## Table of Contents
- [Prerequisites](#prerequisites)
- [Local Development](#local-development)
- [Cloud Deployment](#cloud-deployment)
- [Security Considerations](#security-considerations)
- [Environment Configuration](#environment-configuration)
- [Testing Connection](#testing-connection)
- [Troubleshooting](#troubleshooting)

## Prerequisites

- Docker and Docker Compose installed on your server
- Access to a cloud server (AWS EC2, GCP Compute Engine, DigitalOcean, etc.)
- SSH access to your server
- Firewall configured to allow incoming traffic on port 8000 (or your chosen port)

## Local Development

For local development, TravelAI uses ChromaDB in persistent local mode:

```bash
# Set environment variables in .env
CHROMADB_MODE=local
CHROMADB_PERSIST_DIR=./chroma_data

# Use the client
from src.vectordb import ChromaDBClient

# Initialize from environment
client = ChromaDBClient.initialize_from_env()

# Or initialize explicitly
client = ChromaDBClient()
client.initialize_local(persist_directory='./chroma_data')
```

## Cloud Deployment

### Step 1: Server Setup

1. **SSH into your cloud server**:
   ```bash
   ssh user@your-server-ip
   ```

2. **Install Docker and Docker Compose** (if not already installed):
   ```bash
   # Install Docker
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh

   # Install Docker Compose
   sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
   sudo chmod +x /usr/local/bin/docker-compose
   ```

3. **Verify installation**:
   ```bash
   docker --version
   docker-compose --version
   ```

### Step 2: Deploy ChromaDB

1. **Copy deployment files to server**:
   ```bash
   # On your local machine
   scp deployment/docker-compose.yml user@your-server-ip:~/travelai-chromadb/
   ```

2. **On the server, start ChromaDB**:
   ```bash
   cd ~/travelai-chromadb
   docker-compose up -d
   ```

3. **Check container status**:
   ```bash
   docker-compose ps
   docker-compose logs -f chromadb
   ```

4. **Verify ChromaDB is running**:
   ```bash
   curl http://localhost:8000/api/v1/heartbeat
   ```

   Expected response:
   ```json
   {"nanosecond heartbeat": 1234567890}
   ```

### Step 3: Configure Firewall

Allow incoming traffic on port 8000:

**AWS EC2 Security Group**:
- Add inbound rule: Custom TCP, Port 8000, Source: Your IP or 0.0.0.0/0 (for public access)

**Ubuntu/Debian UFW**:
```bash
sudo ufw allow 8000/tcp
sudo ufw status
```

**CentOS/RHEL Firewalld**:
```bash
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

### Step 4: Test Remote Connection

From your local machine:

```bash
curl http://your-server-ip:8000/api/v1/heartbeat
```

## Security Considerations

### 1. Enable Authentication (Recommended for Production)

ChromaDB supports token-based authentication. To enable:

1. **Create a token**:
   ```bash
   # Generate a random token
   openssl rand -hex 32
   ```

2. **Update docker-compose.yml**:
   ```yaml
   environment:
     - CHROMA_SERVER_AUTH_PROVIDER=chromadb.auth.token.TokenAuthServerProvider
     - CHROMA_SERVER_AUTH_TOKEN_TRANSPORT_HEADER=X-Chroma-Token
     - CHROMA_SERVER_AUTH_CREDENTIALS=your_generated_token_here
   ```

3. **Restart ChromaDB**:
   ```bash
   docker-compose down
   docker-compose up -d
   ```

4. **Update client code to use token**:
   ```python
   client = ChromaDBClient()
   client.initialize_cloud(
       host='your-server-ip',
       port=8000,
       api_key='your_generated_token_here'
   )
   ```

### 2. Use HTTPS/TLS

For production, use a reverse proxy (nginx/Caddy) with SSL:

```nginx
# nginx configuration example
server {
    listen 443 ssl;
    server_name chromadb.yourdomain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 3. Restrict Network Access

- Use VPC/private networking when possible
- Whitelist only trusted IP addresses
- Use SSH tunneling for development access

### 4. Regular Backups

Backup the ChromaDB data volume regularly:

```bash
# Create backup
docker-compose down
tar -czf chromadb-backup-$(date +%Y%m%d).tar.gz chromadb_data/
docker-compose up -d

# Or use Docker volume backup
docker run --rm -v travelai_chromadb_data:/data -v $(pwd):/backup ubuntu tar czf /backup/chromadb-backup.tar.gz /data
```

## Environment Configuration

### Local Mode (.env)
```bash
CHROMADB_MODE=local
CHROMADB_PERSIST_DIR=./chroma_data
```

### Cloud Mode (.env)
```bash
CHROMADB_MODE=cloud
CHROMADB_HOST=your-server-ip
CHROMADB_PORT=8000
CHROMADB_API_KEY=your_token_here  # Optional, but recommended
```

### Automatic Initialization

The ChromaDBClient automatically reads from environment variables:

```python
from src.vectordb import ChromaDBClient

# Reads CHROMADB_MODE and initializes accordingly
client = ChromaDBClient.initialize_from_env()

# Create collections
client.create_collections()

# Use the client
stats = client.get_stats()
client.print_stats()
```

## Testing Connection

### Test Local Mode

```python
from src.vectordb import ChromaDBClient

# Initialize local client
client = ChromaDBClient()
client.initialize_local('./chroma_data')

# Create test collection
collection = client.get_or_create_collection('test_collection')

# Add test data
collection.add(
    ids=['test1'],
    documents=['This is a test document'],
    metadatas=[{'type': 'test'}]
)

# Query
results = collection.query(query_texts=['test'], n_results=1)
print(f"Query results: {results}")

# Cleanup
client.delete_collection('test_collection')
```

### Test Cloud Mode

```python
from src.vectordb import ChromaDBClient
import os

# Set cloud environment variables
os.environ['CHROMADB_MODE'] = 'cloud'
os.environ['CHROMADB_HOST'] = 'your-server-ip'
os.environ['CHROMADB_PORT'] = '8000'
# os.environ['CHROMADB_API_KEY'] = 'your_token_here'  # If using auth

# Initialize from environment
client = ChromaDBClient.initialize_from_env()

# Create collections
client.create_collections()

# Check stats
client.print_stats()
```

## Troubleshooting

### Connection Refused

**Problem**: `ConnectionRefusedError` when connecting to cloud ChromaDB

**Solutions**:
1. Check if ChromaDB container is running: `docker-compose ps`
2. Check container logs: `docker-compose logs chromadb`
3. Verify firewall allows port 8000
4. Test from server: `curl http://localhost:8000/api/v1/heartbeat`
5. Test from local: `curl http://your-server-ip:8000/api/v1/heartbeat`

### Authentication Errors

**Problem**: 401 Unauthorized or authentication failures

**Solutions**:
1. Verify API key is correct in both docker-compose.yml and client code
2. Check environment variables are loaded: `echo $CHROMADB_API_KEY`
3. Restart ChromaDB after configuration changes: `docker-compose restart`

### Data Persistence Issues

**Problem**: Data lost after container restart

**Solutions**:
1. Verify volume is mounted: `docker inspect travelai-chromadb`
2. Check `IS_PERSISTENT=TRUE` in docker-compose.yml
3. Ensure `PERSIST_DIRECTORY=/chroma/chroma` matches volume mount
4. Check volume exists: `docker volume ls`

### High Memory Usage

**Problem**: ChromaDB consuming too much memory

**Solutions**:
1. Adjust resource limits in docker-compose.yml
2. Monitor with: `docker stats travelai-chromadb`
3. Consider using smaller embedding models
4. Implement batch processing for large inserts

### Port Already in Use

**Problem**: Port 8000 already occupied

**Solutions**:
1. Find process using port: `lsof -i :8000` or `netstat -tlnp | grep 8000`
2. Change port in docker-compose.yml: `"8001:8000"`
3. Update CHROMADB_PORT in .env accordingly

## Monitoring and Maintenance

### Check ChromaDB Health

```bash
# Container status
docker-compose ps

# Logs
docker-compose logs -f chromadb

# Resource usage
docker stats travelai-chromadb

# API health
curl http://your-server-ip:8000/api/v1/heartbeat
```

### Restart ChromaDB

```bash
# Restart gracefully
docker-compose restart chromadb

# Stop and start
docker-compose down
docker-compose up -d

# View startup logs
docker-compose logs -f chromadb
```

### Update ChromaDB

```bash
# Pull latest image
docker-compose pull chromadb

# Restart with new image
docker-compose down
docker-compose up -d

# Verify version
docker-compose exec chromadb chroma version
```

## Production Best Practices

1. **Use HTTPS**: Always use SSL/TLS in production
2. **Enable Authentication**: Use token-based auth
3. **Restrict Access**: Whitelist trusted IPs only
4. **Regular Backups**: Automate daily backups
5. **Monitor Resources**: Set up alerts for CPU/memory usage
6. **Version Control**: Pin ChromaDB image version in production
7. **High Availability**: Consider running multiple replicas
8. **Logging**: Centralize logs with ELK/CloudWatch
9. **Health Checks**: Monitor heartbeat endpoint
10. **Disaster Recovery**: Test backup restoration regularly

## Support

For issues with ChromaDB deployment:
- ChromaDB Documentation: https://docs.trychroma.com/
- TravelAI Issues: https://github.com/yourusername/TravelAI/issues
- ChromaDB GitHub: https://github.com/chroma-core/chroma
