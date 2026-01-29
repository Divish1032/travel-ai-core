# Deployment Guide

Guide to deploying TravelAI in production environments.

---

## Deployment Options

1. **Local Development** - Single machine setup
2. **Docker** - Containerized deployment
3. **Cloud VM** - AWS EC2, Google Compute, etc.
4. **Kubernetes** - Scalable orchestration (future)

---

## Local Development Deployment

### Setup

```bash
# Clone repository
git clone https://github.com/your-repo/TravelAI.git
cd TravelAI

# Run automated setup
./setup.sh

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Activate environment
source venv/bin/activate

# Verify installation
./crawl.sh status
```

**Use Cases:**
- Development and testing
- Small-scale processing (<100 videos)
- Learning the system

---

## Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download Whisper model
RUN python -c "import whisper; whisper.load_model('small')"

# Copy application code
COPY . .

# Set Python path
ENV PYTHONPATH=/app

# Default command
CMD ["bash"]
```

### Docker Compose

```yaml
version: '3.8'

services:
  travelai:
    build: .
    container_name: travelai
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./stage4-vectors:/app/stage4-vectors
    env_file:
      - .env
    environment:
      - PYTHONPATH=/app
    command: tail -f /dev/null  # Keep container running

  dashboard:
    build: ./dashboard
    container_name: travelai-dashboard
    ports:
      - "8501:8501"
    volumes:
      - ./data:/app/data
    env_file:
      - .env
    depends_on:
      - travelai
```

### Build and Run

```bash
# Build image
docker-compose build

# Start services
docker-compose up -d

# Run pipeline commands
docker-compose exec travelai ./crawl.sh status
docker-compose exec travelai ./crawl.sh youtube --input urls.txt

# View logs
docker-compose logs -f travelai

# Access dashboard
open http://localhost:8501

# Stop services
docker-compose down
```

---

## Cloud VM Deployment

### AWS EC2 Setup

**Instance Requirements:**
- **Type:** t3.medium (2 vCPU, 4GB RAM minimum)
- **Storage:** 50GB SSD
- **OS:** Ubuntu 22.04 LTS
- **Network:** Public IP with SSH access

**Setup Script:**

```bash
#!/bin/bash
# setup-production.sh

# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Python 3.11
sudo apt-get install -y python3.11 python3.11-venv python3-pip

# Install ffmpeg
sudo apt-get install -y ffmpeg

# Install AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Clone repository
git clone https://github.com/your-repo/TravelAI.git
cd TravelAI

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Download Whisper model
python -c "import whisper; whisper.load_model('small')"

# Setup environment
cp .env.example .env
echo "Edit .env with your credentials"
```

### Running as Service

```bash
# Create systemd service
sudo nano /etc/systemd/system/travelai.service
```

**Service file:**
```ini
[Unit]
Description=TravelAI Pipeline
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/TravelAI
Environment="PATH=/home/ubuntu/TravelAI/venv/bin"
Environment="PYTHONPATH=/home/ubuntu/TravelAI"
ExecStart=/home/ubuntu/TravelAI/venv/bin/python -m src.scheduler
Restart=always

[Install]
WantedBy=multi-user.target
```

**Enable service:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable travelai
sudo systemctl start travelai
sudo systemctl status travelai
```

---

## Production Configuration

### Environment Variables for Production

```bash
# Production .env
AWS_REGION=us-east-1
S3_BUCKET_NAME=travelai-production-data

# Use Gemini for cost efficiency
LLM_PROVIDER=gemini

# Enable cloud ChromaDB
CHROMADB_MODE=cloud
CHROMA_API_KEY=your_production_key

# Logging
LOG_LEVEL=INFO
LOG_FILE=/var/log/travelai/pipeline.log

# Cost limits
RAG_BUDGET_LIMIT=0.50  # Higher for production
```

### Nginx Reverse Proxy (Dashboard)

```nginx
# /etc/nginx/sites-available/travelai
server {
    listen 80;
    server_name dashboard.yourdomain.com;

    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

**Enable site:**
```bash
sudo ln -s /etc/nginx/sites-available/travelai /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## Monitoring

### Log Rotation

```bash
# /etc/logrotate.d/travelai
/var/log/travelai/*.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    create 0640 ubuntu ubuntu
    sharedscripts
    postrotate
        systemctl reload travelai
    endscript
}
```

### Health Checks

```bash
# healthcheck.sh
#!/bin/bash

# Check service status
systemctl is-active --quiet travelai || exit 1

# Check S3 connectivity
aws s3 ls s3://your-bucket/ > /dev/null || exit 1

# Check ChromaDB connectivity
python -c "from src.vectordb import ChromaDBClient; ChromaDBClient.initialize_from_env()" || exit 1

echo "Health check passed"
```

---

## Scaling Considerations

### Horizontal Scaling

**Stage 1 (Crawling):**
- Parallelize across multiple instances
- Divide URL list by instance
- Share S3 bucket

**Stage 2-3 (Processing):**
- Process different entity types in parallel
- Use task queue (Celery/RQ) for distribution

**Stage 4 (Vectorization):**
- Single instance sufficient (fast, local embeddings)

**Stage 5 (RAG):**
- Stateless - can scale horizontally
- Load balance with nginx

### Vertical Scaling

| Component | CPU | RAM | Storage | Notes |
|-----------|-----|-----|---------|-------|
| Stage 1 | 2+ cores | 8GB | 50GB | Whisper benefits from CPU |
| Stage 2-3 | 2+ cores | 4GB | 20GB | LLM API-bound |
| Stage 4 | 4+ cores | 8GB | 50GB | Embedding generation |
| Stage 5 | 2+ cores | 4GB | 20GB | LLM API-bound |

---

## Security

### API Key Security

```bash
# Use AWS Secrets Manager
aws secretsmanager create-secret \
    --name travelai/youtube-api-key \
    --secret-string "your_key_here"

# Retrieve in application
aws secretsmanager get-secret-value \
    --secret-id travelai/youtube-api-key \
    --query SecretString \
    --output text
```

### S3 Bucket Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::ACCOUNT:user/travelai-service"
      },
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::your-bucket",
        "arn:aws:s3:::your-bucket/*"
      ]
    }
  ]
}
```

---

## Cost Optimization

### Production Cost Estimates

**Monthly Costs (1,000 videos/month):**
- S3 Storage: $0.05
- ChromaDB: $0.01
- LLM API (Gemini): $3.00
- YouTube API: FREE
- EC2 t3.medium: $30/month
- **Total:** ~$33/month

### Cost Reduction Tips

1. **Use Gemini** (cheapest LLM)
2. **Batch processing** (off-peak hours)
3. **Cache results** (avoid re-processing)
4. **S3 lifecycle policies** (archive old data)

---

## Backup Strategy

**See:** [backup-recovery.md](../06-operations/backup-recovery.md)

```bash
# Daily backups
0 2 * * * /home/ubuntu/TravelAI/backup.sh

# Weekly full backup
0 3 * * 0 aws s3 sync s3://production-bucket s3://backup-bucket
```

---

## References

- **Monitoring:** [monitoring.md](monitoring.md)
- **Backup:** [backup-recovery.md](../06-operations/backup-recovery.md)
- **Troubleshooting:** [troubleshooting.md](../06-operations/troubleshooting.md)
