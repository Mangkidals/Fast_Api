"""
WebSocket routes for live audio streaming and real-time transcript processing
Menerima audio stream dari frontend, kirim hasil transkripsi realtime
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from typing import Dict, List, Any
import json
import asyncio
import logging
from datetime import datetime

from models.session import SessionStatus, TranscriptStatus
from services.live_session import live_session_service
from services.alignment import alignment_service
from services.supabase import supabase_service
from utils.logging import transcript_logger
from sockets.helpers_ws import ConnectionManager, AudioProcessor

logger = logging.getLogger(__name__)
router = APIRouter()

# Connection manager untuk handle multiple WebSocket connections
connection_manager = ConnectionManager()
audio_processor = AudioProcessor()

@router.websocket("/ws/live/{session_id}")
async def websocket_live_transcript(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint untuk menerima audio stream dari Flutter
    dan mengirim hasil transkripsi realtime
    """
    await connection_manager.connect(websocket, session_id)
    
    try:
        # Verify session exists and is active
        session_status = await live_session_service.get_session_status(session_id)
        if not session_status:
            await websocket.send_json({
                "type": "error",
                "message": "Session not found or inactive",
                "sessionId": session_id
            })
            return
        
        # Send initial session status
        await websocket.send_json({
            "type": "session_status",
            "data": session_status,
            "message": "WebSocket connected successfully"
        })
        
        # Log WebSocket connection
        await transcript_logger.log_session_event(
            session_id, "websocket_connected", 
            "WebSocket connection established"
        )
        
        # Main message handling loop
        while True:
            try:
                # Receive message from client
                message = await websocket.receive()
                
                if message["type"] == "websocket.receive":
                    if "bytes" in message:
                        # Handle binary audio data
                        await handle_audio_data(websocket, session_id, message["bytes"])
                    elif "text" in message:
                        # Handle JSON messages
                        await handle_text_message(websocket, session_id, message["text"])
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error in WebSocket {session_id}: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": f"Processing error: {str(e)}",
                    "sessionId": session_id
                })
                
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
        await transcript_logger.log_error(
            session_id, "websocket_error", str(e)
        )
    finally:
        # Cleanup connection
        connection_manager.disconnect(session_id)
        await transcript_logger.log_session_event(
            session_id, "websocket_disconnected", 
            "WebSocket connection closed"
        )

async def handle_audio_data(websocket: WebSocket, session_id: str, audio_bytes: bytes):
    """
    Handle incoming audio data from frontend
    Frontend sudah melakukan speech-to-text dengan Vosk,
    jadi ini hanya untuk fallback atau audio monitoring
    """
    try:
        # Audio preprocessing if needed
        processed_audio = await audio_processor.preprocess_audio(audio_bytes)
        
        # Send acknowledgment
        await websocket.send_json({
            "type": "audio_received",
            "sessionId": session_id,
            "size": len(audio_bytes),
            "processed_size": len(processed_audio) if processed_audio else 0,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Log audio data received
        await transcript_logger.log_session_event(
            session_id, "audio_received",
            f"Received {len(audio_bytes)} bytes of audio data"
        )
        
    except Exception as e:
        logger.error(f"Error handling audio data for {session_id}: {e}")
        await websocket.send_json({
            "type": "error",
            "message": f"Audio processing error: {str(e)}",
            "sessionId": session_id
        })

async def handle_text_message(websocket: WebSocket, session_id: str, text_data: str):
    """
    Handle JSON text messages from frontend
    Ini yang utama - frontend kirim hasil Vosk sebagai text
    """
    try:
        data = json.loads(text_data)
        message_type = data.get("type")
        
        if message_type == "transcript":
            await handle_transcript_message(websocket, session_id, data)
        elif message_type == "move_ayah":
            await handle_move_ayah_message(websocket, session_id, data)
        elif message_type == "ping":
            await handle_ping_message(websocket, session_id)
        elif message_type == "session_info":
            await handle_session_info_request(websocket, session_id)
        else:
            await websocket.send_json({
                "type": "error",
                "message": f"Unknown message type: {message_type}",
                "sessionId": session_id
            })
            
    except json.JSONDecodeError:
        await websocket.send_json({
            "type": "error",
            "message": "Invalid JSON format",
            "sessionId": session_id
        })
    except Exception as e:
        logger.error(f"Error handling text message for {session_id}: {e}")
        await websocket.send_json({
            "type": "error",
            "message": f"Message processing error: {str(e)}",
            "sessionId": session_id
        })

async def handle_transcript_message(websocket: WebSocket, session_id: str, data: Dict[str, Any]):
    """
    Handle transcript from frontend Vosk
    Format: {"type": "transcript", "text": "...", "is_final": true/false}
    """
    try:
        transcript = data.get("text", "")
        is_final = data.get("is_final", False)
        
        if not transcript:
            return
        
        # Get current session status
        session_status = await live_session_service.get_session_status(session_id)
        if not session_status:
            await websocket.send_json({
                "type": "error",
                "message": "Session not found or inactive",
                "sessionId": session_id
            })
            return
        
        # Get current ayah data
        current_ayah = session_status["current_ayah"]
        current_position = session_status["position"]
        total_words = session_status["total_words"]
        words_array = current_ayah["words_array"]
        
        # Compare transcript with expected words
        expected_words = words_array[current_position:current_position + 10]  # Next 10 words
        results, summary = alignment_service.compare_transcript(
            expected_words=expected_words,
            spoken_transcript=transcript,
            is_final=is_final
        )
        
        # Adjust position indices
        for result in results:
            result.position = current_position + result.position
        
        # Create response
        response = {
            "type": "transcript_result",
            "sessionId": session_id,
            "status": "final" if is_final else "provisional",
            "transcript": transcript,
            "results": [
                {
                    "position": r.position,
                    "expected": r.expected,
                    "spoken": r.spoken,
                    "status": r.status.value,
                    "similarity_score": r.similarity_score,
                    "index": alignment_service.generate_position_index(
                        session_status["surah_id"], 
                        session_status["ayah"], 
                        r.position
                    )
                }
                for r in results
            ],
            "summary": summary if is_final else None,
            "current_position": current_position,
            "total_words": total_words,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Send response to frontend
        await websocket.send_json(response)
        
        if is_final and results:
            # Update session position based on matched words
            matched_words = sum(1 for r in results if r.status.value in ["matched"])
            new_position = current_position + matched_words
            
            # Save to database and update session
            from models.session import UpdateSessionRequest
            update_request = UpdateSessionRequest(transcript=transcript, is_final=True)
            await live_session_service.update_session(session_id, update_request)
            
            # Check if ayah is complete
            if new_position >= total_words:
                await websocket.send_json({
                    "type": "ayah_complete",
                    "sessionId": session_id,
                    "surah_id": session_status["surah_id"],
                    "ayah": session_status["ayah"],
                    "message": "Ayah completed successfully"
                })
                
                # Auto-advance might happen in live_session_service
        
        # Broadcast to other connections if needed
        await connection_manager.broadcast_to_session(session_id, response)
        
    except Exception as e:
        logger.error(f"Error processing transcript for {session_id}: {e}")
        await websocket.send_json({
            "type": "error",
            "message": f"Transcript processing error: {str(e)}",
            "sessionId": session_id
        })

async def handle_move_ayah_message(websocket: WebSocket, session_id: str, data: Dict[str, Any]):
    """
    Handle move to different ayah
    Format: {"type": "move_ayah", "ayah": 5, "position": 0}
    """
    try:
        new_ayah = data.get("ayah")
        new_position = data.get("position", 0)
        
        if new_ayah is None:
            await websocket.send_json({
                "type": "error",
                "message": "Ayah number is required",
                "sessionId": session_id
            })
            return
        
        # Update session via live_session_service
        await supabase_service.update_live_session(session_id, {
            "ayah": new_ayah,
            "position": new_position
        })
        
        # Get updated session status
        updated_status = await live_session_service.get_session_status(session_id)
        
        # Send response
        await websocket.send_json({
            "type": "ayah_moved",
            "sessionId": session_id,
            "surah_id": updated_status["surah_id"],
            "ayah": new_ayah,
            "position": new_position,
            "current_ayah": updated_status["current_ayah"],
            "message": f"Moved to ayah {new_ayah}"
        })
        
        # Log the move
        await transcript_logger.log_session_event(
            session_id, "ayah_moved",
            f"Moved to ayah {new_ayah}, position {new_position}"
        )
        
    except Exception as e:
        logger.error(f"Error moving ayah for {session_id}: {e}")
        await websocket.send_json({
            "type": "error",
            "message": f"Move ayah error: {str(e)}",
            "sessionId": session_id
        })

async def handle_ping_message(websocket: WebSocket, session_id: str):
    """Handle ping/keepalive messages"""
    await websocket.send_json({
        "type": "pong",
        "sessionId": session_id,
        "timestamp": datetime.utcnow().isoformat()
    })

async def handle_session_info_request(websocket: WebSocket, session_id: str):
    """Handle request for current session information"""
    try:
        session_status = await live_session_service.get_session_status(session_id)
        if session_status:
            await websocket.send_json({
                "type": "session_info",
                "data": session_status
            })
        else:
            await websocket.send_json({
                "type": "error",
                "message": "Session not found",
                "sessionId": session_id
            })
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "message": f"Error getting session info: {str(e)}",
            "sessionId": session_id
        })

@router.websocket("/ws/monitor")
async def websocket_monitor():
    """
    WebSocket endpoint untuk monitoring semua active sessions
    Berguna untuk admin dashboard
    """
    websocket = None
    try:
        websocket = WebSocket
        await websocket.accept()
        
        while True:
            # Get active sessions
            active_sessions = list(connection_manager.active_connections.keys())
            
            # Send status update
            await websocket.send_json({
                "type": "monitor_update",
                "active_sessions": active_sessions,
                "total_connections": len(active_sessions),
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Wait 5 seconds before next update
            await asyncio.sleep(5)
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Monitor WebSocket error: {e}")
        if websocket:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })