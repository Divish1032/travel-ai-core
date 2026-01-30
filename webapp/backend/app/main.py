#!/usr/bin/env python3
"""
TravelAI Web Backend - FastAPI Application

Provides REST API for the RAG itinerary generation pipeline with
Firebase authentication and user management.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from contextlib import asynccontextmanager
import sys
import os
import logging

# Add parent directory to path to import from TravelAI root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from src.rag.pipeline import RAGPipeline, InsufficientDataError, ValidationError

# Import app modules
from app.config import settings
from app.utils.firebase import firebase_admin_instance
from app.routers import auth, users, itineraries, favorites, collections, places, search

# Configure logging
logging.basicConfig(
    level=logging.INFO if settings.DEBUG else logging.WARNING,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

# Global pipeline instance
pipeline = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Lifespan event handler for startup and shutdown"""
    global pipeline

    # Startup
    logger.info("Initializing TravelAI Backend...")

    # Initialize Firebase Admin SDK (non-fatal if credentials missing)
    logger.info("Initializing Firebase Admin SDK...")
    firebase_admin_instance.initialize()
    if firebase_admin_instance._initialized:
        logger.info("✅ Firebase Admin SDK initialized")
    else:
        logger.warning("⚠️  Firebase Admin SDK not initialized - auth endpoints disabled")

    # Initialize RAG Pipeline (non-fatal if ChromaDB not available)
    try:
        logger.info("Initializing RAG Pipeline...")
        pipeline = RAGPipeline(enable_cache=True)
        logger.info("✅ RAG Pipeline initialized")
    except Exception as e:
        logger.warning(f"⚠️  RAG Pipeline initialization failed: {e}")
        logger.warning("⚠️  Itinerary generation endpoint will not work")
        logger.warning("⚠️  Set ChromaDB credentials in .env to enable RAG features")
        pipeline = None

    logger.info("✅ TravelAI Backend startup complete")

    yield

    # Shutdown (cleanup if needed)
    logger.info("Shutting down TravelAI Backend...")


# Initialize FastAPI app with lifespan
app = FastAPI(
    title="TravelAI Backend API",
    description="Travel planning platform with AI-powered itinerary generation and personalized recommendations",
    version="2.0.0",
    root_path="/travelai",
    lifespan=lifespan
)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(itineraries.router, prefix="/api")
app.include_router(favorites.router, prefix="/api")
app.include_router(collections.router, prefix="/api")
app.include_router(places.router, prefix="/api")
app.include_router(search.router, prefix="/api")


class GenerateRequest(BaseModel):
    """Request model for itinerary generation"""
    query: str
    skip_narrative: bool = False


class GenerateResponse(BaseModel):
    """Response model for itinerary generation"""
    success: bool
    html_output: str
    metadata: dict


@app.post("/api/generate", response_model=GenerateResponse)
async def generate_itinerary(request: GenerateRequest):
    """
    Generate travel itinerary from natural language query

    Args:
        request: GenerateRequest with query and options

    Returns:
        GenerateResponse with HTML output and metadata

    Raises:
        HTTPException: If generation fails
    """
    # Check if pipeline is initialized
    if pipeline is None:
        raise HTTPException(
            status_code=503,
            detail="RAG Pipeline not initialized. ChromaDB credentials may be missing. Check server logs."
        )

    logger.info(f"Received generation request: {request.query}")

    try:
        # Generate itinerary using RAG pipeline
        result = pipeline.generate(
            query=request.query,
            output_format='html',
            skip_narrative=request.skip_narrative,
            max_retries=2
        )

        logger.info(f"✅ Generation successful (cost: ${result['metadata']['total_cost']:.4f}, time: {result['metadata']['processing_time']:.1f}s)")

        return GenerateResponse(
            success=True,
            html_output=result['formatted_output'],
            metadata={
                "cost": f"${result['metadata']['total_cost']:.4f}",
                "time": f"{result['metadata']['processing_time']:.1f}s",
                "validation_score": f"{result['metadata']['validation_score']:.2f}",
                "entities_used": result['metadata']['entities_used'],
                "validation_passed": result['metadata']['validation_passed']
            }
        )

    except InsufficientDataError as e:
        logger.warning(f"Insufficient data for query: {request.query}")
        raise HTTPException(
            status_code=404,
            detail=f"Insufficient data: {str(e)}"
        )

    except ValidationError as e:
        logger.warning(f"Validation failed for query: {request.query}")
        raise HTTPException(
            status_code=400,
            detail=f"Validation failed: {str(e)}"
        )

    except Exception as e:
        logger.error(f"Generation error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Generation failed. Please try again or contact support."
        )


@app.get("/health")
async def health_check():
    """
    Health check endpoint

    Returns:
        Health status and pipeline readiness
    """
    return {
        "status": "healthy",
        "pipeline_ready": pipeline is not None,
        "service": "travelai-backend"
    }


@app.get("/")
async def root():
    """Root endpoint - redirect to docs"""
    return {
        "message": "TravelAI Itinerary Generator API",
        "docs": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
