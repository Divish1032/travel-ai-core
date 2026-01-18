# TravelAI Dashboard Dockerfile
# Streamlit dashboard for monitoring video processing pipeline

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY dashboard/requirements.txt /app/dashboard/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r dashboard/requirements.txt

# Copy necessary source code
COPY src/ /app/src/
COPY dashboard/ /app/dashboard/

# Use production config for Docker deployment
RUN cp /app/dashboard/.streamlit/config.production.toml /app/dashboard/.streamlit/config.toml

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Expose Streamlit port
EXPOSE 8501

# Set working directory to dashboard
WORKDIR /app/dashboard

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Run Streamlit
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
