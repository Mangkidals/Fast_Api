"""
FastAPI Quran Transcript Application
Main entry point for the API server
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import os
from dotenv import load_dotenv

# ✅ Load environment variables first
load_dotenv()

# ✅ Baru import routes setelah env tersedia
from routes.quran import router as quran_router
from routes.transcript import router as transcript_router

# Create FastAPI app
app = FastAPI(
    title="Quran Transcript API",
    description="API for Quran reading transcript comparison with live session support",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ⚠️ ganti whitelist domain di production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "message": exc.detail,
            "status_code": exc.status_code
        }
    )

# Include routers
app.include_router(quran_router, prefix="/quran", tags=["Quran"])
app.include_router(transcript_router, prefix="", tags=["Transcript"])

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Quran Transcript API",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "active"
    }

# Health check
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "quran-transcript-api"
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True
    )
