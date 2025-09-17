"""
FastAPI Quran Transcript Application - Memory-Based Version
Main entry point with in-memory session management and WebSocket support
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import os
from dotenv import load_dotenv
import logging

# Load environment variables first
load_dotenv()

# Import routes - make sure to import the memory-based versions
from routes.quran import router as quran_router
from routes.memory_transcript import router as transcript_router  # Updated import
from routes.memory_websocket import router as websocket_router    # Updated import
from utils.monitoring import performance_monitor
from services.memory_sessions import memory_live_session_service

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Quran Transcript API (Memory-Based)",
    description="""
    API for Quran reading transcript comparison with memory-based live sessions.
    
    Features:
    - In-memory session storage for low latency
    - WebSocket real-time communication  
    - Database persistence only on session end
    - Live ayah movement and transcript comparison
    """,
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Enhanced CORS middleware for WebSocket support
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Global exception handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "message": exc.detail,
            "status_code": exc.status_code,
            "timestamp": datetime.utcnow().isoformat()
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "message": "Internal server error",
            "status_code": 500
        }
    )

# Include routers with proper prefixes
app.include_router(quran_router, prefix="/quran", tags=["Quran Data"])
app.include_router(transcript_router, prefix="", tags=["Memory Sessions"])
app.include_router(websocket_router, prefix="", tags=["WebSocket Live"])

# Root endpoint with API info
@app.get("/")
async def root():
    from services.memory_sessions import memory_live_session_service
    memory_stats = memory_live_session_service.get_memory_stats()
    
    return {
        "service": "Quran Transcript API",
        "version": "2.0.0",
        "architecture": "Memory-Based Sessions",
        "status": "active",
        "memory_stats": memory_stats,
        "features": [
            "✅ In-memory session storage",
            "✅ WebSocket real-time communication",
            "✅ Database persistence on session end",
            "✅ Live ayah movement",
            "✅ Transcript comparison",
            "✅ Performance monitoring"
        ],
        "endpoints": {
            "docs": "/docs",
            "health": "/health",
            "start_session": "/live/start/{surah_id}/{ayah}",
            "move_ayah": "/live/move/{session_id}",
            "end_session": "/live/end/{session_id}",
            "websocket_live": "/ws/live/{session_id}",
            "websocket_monitor": "/ws/monitor"
        }
    }

# Enhanced health check
@app.get("/health")
async def health_check():
    try:
        # Check memory system health
        memory_stats = memory_live_session_service.get_memory_stats()
        performance_health = performance_monitor.get_health_status()
        
        # Test database connectivity
        db_healthy = True
        try:
            from services.supabase import supabase_service
            test_surat = await supabase_service.get_surat_info(1)
            db_healthy = test_surat is not None
        except Exception as e:
            logger.warning(f"Database health check failed: {e}")
            db_healthy = False
        
        health_status = "healthy"
        issues = []
        
        if not db_healthy:
            health_status = "degraded"
            issues.append("Database connectivity issues")
        
        if performance_health["status"] != "healthy":
            health_status = performance_health["status"]
            issues.extend(performance_health.get("issues", []))
        
        return {
            "status": health_status,
            "service": "quran-transcript-api",
            "version": "2.0.0",
            "architecture": "memory-based",
            "timestamp": datetime.utcnow().isoformat(),
            "health_details": {
                "memory_system": "healthy",
                "database": "healthy" if db_healthy else "degraded",
                "performance": performance_health["status"]
            },
            "memory_stats": memory_stats,
            "uptime": performance_monitor.get_system_stats()["uptime_formatted"],
            "issues": issues
        }
        
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )

# ===== MONITORING ENDPOINTS =====

@app.get("/monitoring/stats")
async def get_comprehensive_monitoring():
    """Get all monitoring statistics including memory usage"""
    try:
        performance_stats = performance_monitor.get_comprehensive_stats()
        memory_stats = memory_live_session_service.get_memory_stats()
        
        return {
            "success": True,
            "data": {
                **performance_stats,
                "memory_system": {
                    "stats": memory_stats,
                    "active_sessions": memory_live_session_service.get_all_active_sessions()
                }
            },
            "message": "Comprehensive monitoring data retrieved"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving monitoring data: {str(e)}")

@app.get("/monitoring/memory")
async def get_memory_monitoring():
    """Get detailed memory system monitoring"""
    try:
        stats = memory_live_session_service.get_memory_stats()
        all_sessions = memory_live_session_service.get_all_active_sessions()
        
        # Format sessions for response
        formatted_sessions = {}
        for session_id, session in all_sessions.items():
            formatted_sessions[session_id] = {
                "user_id": session["user_id"],
                "surah_id": session["surah_id"],
                "ayah": session["ayah"],
                "position": session["position"],
                "mode": session["mode"],
                "status": session["status"],
                "is_persisted": session["is_persisted"],
                "created_at": session["created_at"].isoformat(),
                "updated_at": session["updated_at"].isoformat()
            }
        
        return {
            "success": True,
            "data": {
                "statistics": stats,
                "sessions": formatted_sessions,
                "session_count": len(formatted_sessions)
            },
            "message": "Memory system monitoring data retrieved"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving memory data: {str(e)}")

@app.get("/monitoring/websocket")
async def get_websocket_monitoring():
    """Get WebSocket connection statistics"""
    try:
        ws_stats = performance_monitor.get_websocket_stats()
        
        return {
            "success": True,
            "data": ws_stats,
            "message": "WebSocket monitoring data retrieved"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving WebSocket data: {str(e)}")

# ===== DEVELOPMENT & ADMIN ENDPOINTS =====

@app.get("/dev/info")
async def get_development_info():
    """Development server information and configuration"""
    return {
        "environment": {
            "debug": bool(os.getenv("DEBUG", True)),
            "port": int(os.getenv("PORT", 8000)),
            "supabase_configured": bool(os.getenv("SUPABASE_URL"))
        },
        "architecture": {
            "type": "memory-based",
            "description": "Sessions stored in memory, persisted on end",
            "benefits": ["Low latency", "Real-time updates", "Efficient WebSocket communication"]
        },
        "api_endpoints": {
            "session_management": {
                "start": "POST /live/start/{surah_id}/{ayah}",
                "move": "PATCH /live/move/{session_id}",
                "end": "POST /live/end/{session_id}",
                "status": "GET /live/status/{session_id}"
            },
            "websocket": {
                "live_session": "WS /ws/live/{session_id}",
                "monitor": "WS /ws/monitor"
            },
            "monitoring": {
                "stats": "GET /monitoring/stats",
                "memory": "GET /monitoring/memory",
                "websocket": "GET /monitoring/websocket"
            }
        },
        "websocket_protocol": {
            "client_messages": [
                {"type": "move_ayah", "ayah": "int", "position": "int"},
                {"type": "transcript", "text": "string", "is_final": "boolean"},
                {"type": "get_session_status"},
                {"type": "ping"}
            ],
            "server_messages": [
                {"type": "session_connected", "data": "object"},
                {"type": "ayah_moved", "...": "ayah_data"},
                {"type": "transcript_result", "results": "array"},
                {"type": "session_ended", "final_data": "object"},
                {"type": "error", "message": "string"}
            ]
        },
        "example_usage": {
            "javascript": "const ws = new WebSocket('ws://localhost:8000/ws/live/{session_id}')",
            "flutter": "WebSocketChannel.connect(Uri.parse('ws://localhost:8000/ws/live/{session_id}'))"
        }
    }

@app.post("/dev/reset")
async def reset_monitoring_data():
    """Reset monitoring metrics (development only)"""
    try:
        performance_monitor.reset_metrics()
        
        return {
            "success": True,
            "message": "Monitoring metrics reset successfully",
            "warning": "Development endpoint - use with caution"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error resetting metrics: {str(e)}")

# ===== STARTUP & SHUTDOWN EVENTS =====

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    try:
        print("🚀 Quran Transcript API (Memory-Based) Starting...")
        print("="*60)
        
        # Test database connection
        try:
            from services.supabase import supabase_service
            test_surat = await supabase_service.get_surat_info(1)
            if test_surat:
                print("✅ Database connection: OK")
            else:
                print("⚠️  Database connection: Limited")
        except Exception as e:
            print(f"⚠️ Database connection: ERROR - {e}")
        
        # Initialize memory system
        print("🧠 Memory session system: Ready")
        print(f"📊 Performance monitoring: Enabled")
        print(f"🔌 WebSocket endpoints: Ready")
        
        # Log system configuration
        memory_stats = memory_live_session_service.get_memory_stats()
        print(f"💾 Memory store initialized: {memory_stats}")
        
        # Initialize monitoring
        performance_monitor.reset_metrics()
        print("📈 Monitoring metrics: Reset")
        
        print("="*60)
        print("🎉 Server ready for connections!")
        print(f"📡 Local: http://localhost:{os.getenv('PORT', 8000)}")
        print(f"📖 Docs: http://localhost:{os.getenv('PORT', 8000)}/docs")
        print(f"🔌 WebSocket: ws://localhost:{os.getenv('PORT', 8000)}/ws/live/{{session_id}}")
        
    except Exception as e:
        logger.error(f"Startup error: {e}")
        print(f"❌ Startup failed: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    try:
        print("\n👋 Shutting down Quran Transcript API...")
        
        # Get final stats
        memory_stats = memory_live_session_service.get_memory_stats()
        print(f"📊 Final memory stats: {memory_stats}")
        
        # If there are active sessions, warn about data loss
        if memory_stats.get("active_sessions", 0) > 0:
            print("⚠️  WARNING: Active sessions will lose unsaved data!")
            print("💡 Consider ending sessions properly in production")
        
        # Log shutdown
        logger.info("Server shutdown completed")
        print("✅ Shutdown completed")
        
    except Exception as e:
        logger.error(f"Shutdown error: {e}")
        print(f"❌ Shutdown error: {e}")

# ===== ERROR HANDLING MIDDLEWARE =====

@app.middleware("http")
async def error_handling_middleware(request, call_next):
    """Global error handling and request logging"""
    try:
        # Track request
        performance_monitor.track_websocket_message("http_request", "request_received")
        
        response = await call_next(request)
        
        # Track response
        if response.status_code >= 400:
            performance_monitor.track_websocket_error("http_request", f"status_{response.status_code}")
        
        return response
        
    except Exception as e:
        logger.error(f"Request processing error: {e}")
        performance_monitor.track_websocket_error("http_request", "processing_error")
        
        return JSONResponse(
            status_code=500,
            content={
                "error": True,
                "message": "Internal server error",
                "request_id": id(request)
            }
        )

# ===== CUSTOM ROUTES FOR MEMORY SYSTEM =====

@app.get("/system/status")
async def get_system_status():
    """Get overall system status including memory and performance"""
    try:
        memory_stats = memory_live_session_service.get_memory_stats()
        performance_stats = performance_monitor.get_comprehensive_stats()
        
        # Calculate system health
        total_sessions = memory_stats.get("total_sessions", 0)
        active_sessions = memory_stats.get("active_sessions", 0)
        memory_usage = "normal"
        
        if total_sessions > 100:
            memory_usage = "high"
        elif total_sessions > 50:
            memory_usage = "medium"
        
        # Performance health
        perf_health = performance_monitor.get_health_status()
        
        return {
            "system": {
                "status": "operational",
                "version": "2.0.0",
                "architecture": "memory-based",
                "uptime": performance_stats["system"]["uptime_formatted"]
            },
            "memory": {
                "usage": memory_usage,
                "stats": memory_stats,
                "active_sessions": active_sessions,
                "total_sessions": total_sessions
            },
            "performance": {
                "health": perf_health["status"],
                "issues": perf_health.get("issues", []),
                "warnings": perf_health.get("warnings", [])
            },
            "database": {
                "status": "connected",  # Could add actual health check
                "operations": performance_stats.get("database", {})
            }
        }
        
    except Exception as e:
        logger.error(f"System status error: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "system": {"status": "error"},
                "error": str(e)
            }
        )

@app.get("/sessions/summary")
async def get_sessions_summary():
    """Get summary of all sessions in memory"""
    try:
        all_sessions = memory_live_session_service.get_all_active_sessions()
        memory_stats = memory_live_session_service.get_memory_stats()
        
        # Group sessions by status
        by_status = {}
        by_surah = {}
        by_user = {}
        
        for session_id, session in all_sessions.items():
            status = session["status"]
            surah_id = session["surah_id"]
            user_id = session["user_id"]
            
            by_status[status] = by_status.get(status, 0) + 1
            by_surah[surah_id] = by_surah.get(surah_id, 0) + 1
            by_user[user_id] = by_user.get(user_id, 0) + 1
        
        return {
            "success": True,
            "data": {
                "total_sessions": len(all_sessions),
                "memory_stats": memory_stats,
                "distribution": {
                    "by_status": by_status,
                    "by_surah": by_surah,
                    "by_user": by_user
                },
                "most_active_surah": max(by_surah.items(), key=lambda x: x[1]) if by_surah else None,
                "most_active_user": max(by_user.items(), key=lambda x: x[1]) if by_user else None
            },
            "message": "Sessions summary retrieved successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting sessions summary: {str(e)}")

# Import datetime for timestamps
from datetime import datetime

# ===== WEBSOCKET HEALTH CHECK =====

@app.get("/ws/health")
async def websocket_health():
    """Check WebSocket subsystem health"""
    try:
        ws_stats = performance_monitor.get_websocket_stats()
        
        # Import the WebSocket manager from the routes
        try:
            from routes.memory_websocket import websocket_manager
            manager_stats = websocket_manager.get_stats()
        except ImportError:
            manager_stats = {"error": "WebSocket manager not available"}
        
        return {
            "websocket_system": {
                "status": "healthy",
                "performance_stats": ws_stats,
                "manager_stats": manager_stats
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "websocket_system": {"status": "error"},
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )

if __name__ == "__main__":
    # Configuration
    host = "0.0.0.0"
    port = int(os.getenv("PORT", 8000))
    debug = bool(os.getenv("DEBUG", True))
    
    # Enhanced uvicorn configuration
    uvicorn_config = {
        "app": "main:app",
        "host": host,
        "port": port,
        "reload": debug,
        "log_level": "info",
        "access_log": True,
        "server_header": False,
        "date_header": False
    }
    
    # Add WebSocket support configuration
    if not debug:
        uvicorn_config.update({
            "loop": "uvloop",  # Better performance for production
            "http": "httptools"
        })
    
    print(f"Starting Quran Transcript API on {host}:{port}")
    print(f"Debug mode: {debug}")
    print(f"WebSocket support: Enabled")
    print(f"Memory-based sessions: Enabled")
    
    uvicorn.run(**uvicorn_config)