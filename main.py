"""
FastAPI Quran Transcript Application - Updated
Main entry point dengan WebSocket support dan monitoring
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import os
from dotenv import load_dotenv

# ✅ Load environment variables first
load_dotenv()

# ✅ Import routes setelah env tersedia
from routes.quran import router as quran_router
from routes.transcript import router as transcript_router
from routes.live_ws import router as websocket_router
from utils.monitoring import performance_monitor

# Create FastAPI app
app = FastAPI(
    title="Quran Transcript API",
    description="API for Quran reading transcript comparison with live session support and WebSocket streaming",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware - Updated untuk WebSocket support
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
app.include_router(websocket_router, prefix="", tags=["WebSocket"])  # ✅ Tambah WebSocket routes

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Quran Transcript API with Live WebSocket Support",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "active",
        "features": [
            "REST API for Quran data",
            "Live transcript sessions",
            "WebSocket streaming",
            "Real-time audio processing",
            "Performance monitoring"
        ]
    }

# Health check - Enhanced
@app.get("/health")
async def health_check():
    health_status = performance_monitor.get_health_status()
    
    return {
        "status": "healthy",
        "service": "quran-transcript-api",
        "version": "1.0.0",
        "health": health_status,
        "uptime": performance_monitor.get_system_stats()["uptime_formatted"]
    }

# ✅ Monitoring endpoints
@app.get("/monitoring/stats")
async def get_monitoring_stats():
    """Get comprehensive monitoring statistics"""
    return {
        "success": True,
        "data": performance_monitor.get_comprehensive_stats(),
        "message": "Monitoring statistics retrieved successfully"
    }

@app.get("/monitoring/health")
async def get_health_status():
    """Get detailed health status"""
    return {
        "success": True,
        "data": performance_monitor.get_health_status(),
        "message": "Health status retrieved successfully"
    }

@app.get("/monitoring/websocket")
async def get_websocket_stats():
    """Get WebSocket statistics"""
    return {
        "success": True,
        "data": performance_monitor.get_websocket_stats(),
        "message": "WebSocket statistics retrieved successfully"
    }

@app.post("/monitoring/reset")
async def reset_monitoring():
    """Reset all monitoring metrics (development only)"""
    performance_monitor.reset_metrics()
    return {
        "success": True,
        "message": "Monitoring metrics reset successfully"
    }

# ✅ Development info endpoint
@app.get("/dev/info")
async def get_dev_info():
    """Get development server information"""
    return {
        "environment": os.getenv("DEBUG", "False"),
        "port": int(os.getenv("PORT", 8000)),
        "supabase_configured": bool(os.getenv("SUPABASE_URL")),
        "endpoints": {
            "docs": "/docs",
            "health": "/health",
            "monitoring": "/monitoring/stats",
            "websocket_live": "/ws/live/{session_id}",
            "websocket_monitor": "/ws/monitor"
        },
        "websocket_info": {
            "protocol": "WebSocket",
            "message_types": [
                "transcript", "move_ayah", "ping", "session_info"
            ],
            "response_types": [
                "transcript_result", "ayah_moved", "pong", "session_info", "error"
            ]
        }
    }

# ✅ Startup dan shutdown events
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    # Log startup
    print("🚀 Quran Transcript API starting up...")
    print(f"📊 Monitoring enabled")
    print(f"🔌 WebSocket endpoints ready")
    print(f"📡 Supabase configured: {bool(os.getenv('SUPABASE_URL'))}")
    
    # Initialize monitoring
    performance_monitor.reset_metrics()

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    print("👋 Quran Transcript API shutting down...")
    
    # Could add cleanup tasks here
    # e.g., close database connections, cleanup temp files

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=bool(os.getenv("DEBUG", True)),
        log_level="info"
    )