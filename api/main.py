"""
Minimal FastAPI application for Travel AI.
This is a placeholder for future API development.
"""
from fastapi import FastAPI

app = FastAPI(
    title="Travel AI API",
    description="API for Travel AI - YouTube vlog processing and travel planning",
    version="0.1.0"
)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"message": "Stage 1: API not yet implemented"}


@app.get("/health")
async def health_check():
    """Detailed health check endpoint."""
    return {
        "status": "healthy",
        "stage": "Stage 1 - Infrastructure Setup",
        "features": {
            "crawling": "in_development",
            "processing": "not_implemented",
            "llm_integration": "not_implemented",
            "travel_planning": "not_implemented"
        }
    }
