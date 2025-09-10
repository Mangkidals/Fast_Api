"""
FastAPI routes for transcript comparison and live sessions
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict, Any

from models.session import (
    StartSessionRequest, StartSessionResponse,
    UpdateSessionRequest, UpdateSessionResponse,
    MoveAyahRequest, MoveAyahResponse,
    EndSessionResponse, TranscriptComparisonRequest, 
    TranscriptComparisonResponse,
)
from services.live_session import live_session_service
from services.supabase import supabase_service
from services.alignment import alignment_service
from utils.logging import transcript_logger

router = APIRouter()

@router.post("/transcript/{surah_id}/{ayah}", response_model=TranscriptComparisonResponse)
async def compare_transcript(surah_id: int, ayah: int, request: TranscriptComparisonRequest):
    """Compare transcript with specific ayah (non-live mode)"""
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
        
        # Get expected words (prefer words_array, fallback to split arabic text)
        expected_words = ayat_data.words_array or ayat_data.arabic.split()
        
        # Compare transcript
        results, summary = alignment_service.compare_transcript(
            expected_words=expected_words,
            spoken_transcript=request.transcript,
            is_final=True
        )
        
        # Log the comparison
        session_id = f"single_compare_{surah_id}_{ayah}"
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

@router.post("/live/start/{surah_id}/{ayah}", response_model=StartSessionResponse)
async def start_live_session(surah_id: int, ayah: int, request: StartSessionRequest):
    """Start new live transcript session"""
    try:
        # Validate parameters
        if surah_id < 1 or surah_id > 114:
            raise HTTPException(status_code=400, detail="Surah ID must be between 1 and 114")
        
        if ayah < 1:
            raise HTTPException(status_code=400, detail="Ayat Dimulai Dari 1")
        
        # Override surah_id and ayah from URL parameters
        request.surah_id = surah_id
        request.ayah = ayah
        
        # Start session
        response = await live_session_service.start_session(request)
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    
@router.patch("/live/move/{session_id}", response_model=MoveAyahResponse)
async def move_to_ayah(session_id: str, request: MoveAyahRequest):
    """Move current session to a new ayah (without creating a new session)"""
    try:
        if not session_id:
            raise HTTPException(status_code=400, detail="Session ID is required")

        # Cek apakah session masih aktif
        session = await live_session_service.get_session_status(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found or inactive")

        # Update ayah & position
        await supabase_service.update_live_session(session_id, {
            "ayah": request.ayah,
            "position": request.position
        })

        return MoveAyahResponse(
            sessionId=session_id,
            surah_id=session["surah_id"],
            ayah=request.ayah,
            status="active",
            position=request.position,
            message=f"Moved to ayah {request.ayah}"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post("/live/update/{session_id}", response_model=UpdateSessionResponse)
async def update_live_session(session_id: str, request: UpdateSessionRequest):
    """Update live session with new transcript (streaming)"""
    try:
        if not session_id:
            raise HTTPException(status_code=400, detail="Session ID is required")
        
        # Update session
        response = await live_session_service.update_session(session_id, request)
        
        return response
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post("/live/end/{session_id}", response_model=EndSessionResponse)
async def end_live_session(session_id: str, background_tasks: BackgroundTasks):
    """End live transcript session"""
    try:
        if not session_id:
            raise HTTPException(status_code=400, detail="Session ID is required")
        
        # End session
        response = await live_session_service.end_session(session_id)
        
        # Add background task for cleanup if needed
        background_tasks.add_task(live_session_service.cleanup_inactive_sessions)
        
        return response
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/live/status/{session_id}")
async def get_live_session_status(session_id: str):
    """Get current status of live session"""
    try:
        if not session_id:
            raise HTTPException(status_code=400, detail="Session ID is required")
        
        status = await live_session_service.get_session_status(session_id)
        
        if not status:
            raise HTTPException(status_code=404, detail="Session not found or inactive")
        
        return {
            "success": True,
            "data": status,
            "message": "Session status retrieved successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/logs/{session_id}")
async def get_session_logs(session_id: str):
    """Get transcript logs for a specific session"""
    try:
        if not session_id:
            raise HTTPException(status_code=400, detail="Session ID is required")
        
        # Get logs from database
        logs = await supabase_service.get_transcript_logs(session_id)
        
        return {
            "success": True,
            "data": {
                "session_id": session_id,
                "logs": [
                    {
                        "id": log.id,
                        "transcript": log.transcript,
                        "is_final": log.is_final,
                        "created_at": log.created_at,
                        "updated_at": log.updated_at
                    }
                    for log in logs
                ],
                "total": len(logs)
            },
            "message": f"Retrieved {len(logs)} logs for session {session_id}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/logs/stats")
async def get_logging_stats(hours: int = 24):
    """Get logging statistics"""
    try:
        if hours < 1 or hours > 168:  # Max 1 week
            raise HTTPException(status_code=400, detail="Hours must be between 1 and 168")
        
        stats = transcript_logger.get_log_stats(hours)
        
        return {
            "success": True,
            "data": stats,
            "message": f"Logging statistics for last {hours} hours"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.delete("/live/{session_id}")
async def force_delete_session(session_id: str):
    """Force delete a session (admin endpoint)"""
    try:
        if not session_id:
            raise HTTPException(status_code=400, detail="Session ID is required")
        
        # End session if it exists
        try:
            await live_session_service.end_session(session_id)
        except:
            pass  # Session might not exist
        
        # Delete logs
        await supabase_service._make_request(
            "DELETE",
            f"transcript_logs?session_id=eq.{session_id}",
            use_service_role=True
        )
        
        # Delete session
        await supabase_service._make_request(
            "DELETE", 
            f"live_sessions?id=eq.{session_id}",
            use_service_role=True
        )
        
        return {
            "success": True,
            "message": f"Session {session_id} and related data deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/live/active")
async def get_active_sessions():
    """Get list of currently active sessions"""
    try:
        # Query active sessions from database
        params = {"status": "eq.active", "order": "created_at.desc"}
        result = await supabase_service._make_request(
            "GET", 
            "live_sessions", 
            params=params, 
            use_service_role=True
        )
        
        return {
            "success": True,
            "data": {
                "active_sessions": result or [],
                "total": len(result) if result else 0
            },
            "message": "Active sessions retrieved successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# Cleanup endpoint (should be called by background task/cron)
@router.post("/maintenance/cleanup")
async def cleanup_old_sessions(hours: int = 24):
    """Cleanup old inactive sessions (maintenance endpoint)"""
    try:
        if hours < 1 or hours > 168:
            raise HTTPException(status_code=400, detail="Hours must be between 1 and 168")
        
        await live_session_service.cleanup_inactive_sessions(hours)
        
        return {
            "success": True,
            "message": f"Cleanup completed for sessions older than {hours} hours"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")