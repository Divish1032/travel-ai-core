FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy backend requirements
COPY webapp/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy TravelAI source code (needed for pipeline imports)
COPY src /travelai/src
COPY cli /travelai/cli
COPY requirements.txt /travelai/requirements.txt

# Install TravelAI dependencies
RUN pip install --no-cache-dir -r /travelai/requirements.txt

# Copy backend app
COPY webapp/backend/app /app/app

# Copy .env file for config
COPY webapp/.env /travelai/.env

# Set Python path to include TravelAI root
ENV PYTHONPATH=/travelai:$PYTHONPATH

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
