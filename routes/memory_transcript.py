"""
Memory-based transcript routes
REST endpoints for session management with memory storage
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict, Any
import logging
from datetime import datetime

from models.session import (
    StartSessionRequest, StartSessionResponse,
    MoveAyahRequest, MoveAyahResponse,
    EndSessionResponse, TranscriptComparisonRequest, 
    TranscriptComparisonResponse,
)
from services.memory_sessions import memory_live_session_service
from services.supabase import supabase_service
from services.alignment import alignment_service
from utils.logging import transcript_logger

# Setup logger
logger = logging.getLogger(__name__)

router = APIRouter()

# ===== MEMORY-BASED SESSION ENDPOINTS =====

@router.post("/live/start/{surah_id}/{ayah}", response_model=StartSessionResponse)
async def start_memory_session(surah_id: int, ayah: int, request: StartSessionRequest):
    """
    Start new live session in memory (no immediate database write)
    Session will only be persisted when ended
    """
    try:
        # Validate parameters
        if surah_id < 1 or surah_id > 114:
            raise HTTPException(status_code=400, detail="Surah ID must be between 1 and 114")
        
        if ayah < 1:
            raise HTTPException(status_code=400, detail="Ayah must start from 1")
        
        # Override surah_id and ayah from URL parameters
        request.surah_id = surah_id
        request.ayah = ayah
        
        # Start session in memory
        response = await memory_live_session_service.start_session(request)
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.patch("/live/move/{session_id}", response_model=MoveAyahResponse)
async def move_ayah_memory(session_id: str, request: MoveAyahRequest):
    """
    Move session to new ayah in memory and broadcast to WebSocket clients
    No database write until session ends
    """
    try:
        if not session_id:
            raise HTTPException(status_code=400, detail="Session ID is required")

        # Move ayah in memory (automatically broadcasts to WebSocket clients)
        response = await memory_live_session_service.move_ayah(session_id, request)
        
        return response

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post("/live/end/{session_id}", response_model=EndSessionResponse)
async def end_memory_session(session_id: str, background_tasks: BackgroundTasks):
    """
    End live session and persist to database
    This is the ONLY point where session data is written to Supabase
    """
    try:
        if not session_id:
            raise HTTPException(status_code=400, detail="Session ID is required")
        
        # End session and persist to database
        response = await memory_live_session_service.end_session(session_id)
        
        # Add background cleanup task
        background_tasks.add_task(cleanup_old_memory_sessions)
        
        return response
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/live/status/{session_id}")
async def get_memory_session_status(session_id: str):
    """
    Get current status of memory session
    Returns live data from memory, not database
    """
    try:
        if not session_id:
            raise HTTPException(status_code=400, detail="Session ID is required")
        
        status = await memory_live_session_service.get_session_status(session_id)
        
        if not status:
            raise HTTPException(status_code=404, detail="Session not found in memory")
        
        return {
            "success": True,
            "data": status,
            "message": "Memory session status retrieved successfully",
            "source": "memory"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/live/active")
async def get_active_memory_sessions():
    """
    Get list of currently active sessions from memory
    Shows real-time session data
    """
    try:
        # Get all sessions from memory
        all_sessions = memory_live_session_service.get_all_active_sessions()
        memory_stats = memory_live_session_service.get_memory_stats()
        
        # Format for response
        formatted_sessions = []
        for session_id, session in all_sessions.items():
            formatted_sessions.append({
                "session_id": session_id,
                "user_id": session["user_id"],
                "surah_id": session["surah_id"],
                "ayah": session["ayah"],
                "position": session["position"],
                "mode": session["mode"],
                "status": session["status"],
                "is_persisted": session["is_persisted"],
                "created_at": session["created_at"].isoformat(),
                "updated_at": session["updated_at"].isoformat()
            })
        
        return {
            "success": True,
            "data": {
                "active_sessions": formatted_sessions,
                "memory_stats": memory_stats,
                "total": len(formatted_sessions)
            },
            "message": "Active memory sessions retrieved successfully",
            "source": "memory"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/memory/stats")
async def get_memory_statistics():
    """
    Get memory store statistics
    Shows current memory usage and session counts
    """
    try:
        stats = memory_live_session_service.get_memory_stats()
        
        return {
            "success": True,
            "data": stats,
            "message": "Memory statistics retrieved successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# ===== DIRECT TRANSCRIPT COMPARISON (NON-SESSION) =====

@router.post("/transcript/{surah_id}/{ayah}", response_model=TranscriptComparisonResponse)
async def compare_transcript_direct(surah_id: int, ayah: int, request: TranscriptComparisonRequest):
    """
    Direct transcript comparison without session
    For one-off comparisons
    """
    try:
        # Validate parameters
        if surah_id < 1 or surah_id > 114:
            raise HTTPException(status_code=400, detail="Surah ID must be between 1 and 114")
        
        if ayah < 1:
            raise HTTPException(status_code=400, detail="Ayah number must be greater than 0")
        
        # Get ayah data
        ayat_data = await supabase_service.get_ayat(surah_id, ayah)
        if not ayat_data:
            raise HTTPException(
                status_code=404, 
                detail=f"Ayah {surah_id}:{ayah} not found"
            )
        
        # Get expected words
        expected_words = ayat_data.words_array or ayat_data.arabic.split()
        
        # Compare transcript
        results, summary = alignment_service.compare_transcript(
            expected_words=expected_words,
            spoken_transcript=request.transcript,
            is_final=True
        )
        
        # Log the comparison
        session_id = f"direct_compare_{surah_id}_{ayah}"
        await transcript_logger.log_transcript(
            session_id, request.transcript, True, results, summary
        )
        
        return TranscriptComparisonResponse(
            success=True,
            results=results,
            summary=summary,
            message=f"Transcript compared with ayah {surah_id}:{ayah}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# ===== MAINTENANCE ENDPOINTS =====

@router.post("/maintenance/cleanup")
async def cleanup_memory_sessions():
    """
    Cleanup memory sessions (development/maintenance endpoint)
    Force clean sessions that should have been persisted
    """
    try:
        # Get all sessions
        all_sessions = memory_live_session_service.get_all_active_sessions()
        cleaned_count = 0
        
        # Clean sessions marked as persisted but still in memory
        for session_id, session in all_sessions.items():
            if session.get("is_persisted", False):
                memory_live_session_service.memory_store.delete_session(session_id)
                cleaned_count += 1
        
        return {
            "success": True,
            "message": f"Cleaned up {cleaned_count} persisted sessions from memory",
            "cleaned_sessions": cleaned_count
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.delete("/memory/session/{session_id}")
async def force_delete_memory_session(session_id: str):
    """
    Force delete a session from memory (admin/debug endpoint)
    Use with caution - this will lose unsaved session data
    """
    try:
        if not session_id:
            raise HTTPException(status_code=400, detail="Session ID is required")
        
        # Check if session exists
        session = memory_live_session_service.memory_store.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found in memory")
        
        # Delete from memory
        success = memory_live_session_service.memory_store.delete_session(session_id)
        
        if success:
            return {
                "success": True,
                "message": f"Session {session_id} deleted from memory",
                "warning": "Session data was not persisted to database"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to delete session from memory")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# ===== BACKGROUND TASKS =====

async def cleanup_old_memory_sessions():
    """
    Background task to cleanup old memory sessions
    Called after session end operations
    """
    try:
        all_sessions = memory_live_session_service.get_all_active_sessions()
        current_time = datetime.utcnow()
        
        # Clean sessions that have been persisted for more than 1 hour
        for session_id, session in all_sessions.items():
            if (session.get("is_persisted", False) and 
                session.get("updated_at") and
                (current_time - session["updated_at"]).total_seconds() > 3600):
                
                memory_live_session_service.memory_store.delete_session(session_id)
                logger.info(f"Background cleanup: removed persisted session {session_id}")
        
    except Exception as e:
        logger.error(f"Error in background cleanup: {e}")