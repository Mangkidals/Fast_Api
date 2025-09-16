"""
WebSocket routes for memory-based live sessions
Real-time communication with in-memory session management
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from typing import Dict, List, Any
import json
import asyncio
import logging
from datetime import datetime

from models.session import SessionStatus, MoveAyahRequest
from services.memory_sessions import memory_live_session_service
from services.alignment import alignment_service
from utils.logging import transcript_logger

logger = logging.getLogger(__name__)
router = APIRouter()

class WebSocketManager:
    """
    Enhanced WebSocket connection manager for memory-based sessions
    """
    def __init__(self):
        # Active WebSocket connections: websocket_id -> {"websocket": ws, "session_id": str}
        self.active_connections: Dict[str, Dict[str, Any]] = {}
        # Connection counter for unique IDs
        self.connection_counter = 0
    
    def generate_connection_id(self) -> str:
        """Generate unique connection ID"""
        self.connection_counter += 1
        return f"ws_{self.connection_counter}_{int(datetime.utcnow().timestamp())}"
    
    async def connect(self, websocket: WebSocket, session_id: str) -> str:
        """Connect WebSocket to session"""
        await websocket.accept()
        
        # Generate unique connection ID
        connection_id = self.generate_connection_id()
        
        # Store connection
        self.active_connections[connection_id] = {
            "websocket": websocket,
            "session_id": session_id,
            "connected_at": datetime.utcnow()
        }
        
        # Add to memory session service
        await memory_live_session_service.add_websocket_connection(session_id, websocket)
        
        logger.info(f"WebSocket {connection_id} connected to session {session_id}")
        return connection_id
    
    def disconnect(self, connection_id: str):
        """Disconnect WebSocket"""
        if connection_id in self.active_connections:
            connection_info = self.active_connections[connection_id]
            session_id = connection_info["session_id"]
            websocket = connection_info["websocket"]
            
            # Remove from memory session service
            asyncio.create_task(
                memory_live_session_service.remove_websocket_connection(session_id, websocket)
            )
            
            # Remove from active connections
            del self.active_connections[connection_id]
            
            logger.info(f"WebSocket {connection_id} disconnected from session {session_id}")
    
    def get_session_connections(self, session_id: str) -> List[WebSocket]:
        """Get all WebSocket connections for a session"""
        connections = []
        for conn_info in self.active_connections.values():
            if conn_info["session_id"] == session_id:
                connections.append(conn_info["websocket"])
        return connections
    
    def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics"""
        session_counts = {}
        for conn_info in self.active_connections.values():
            session_id = conn_info["session_id"]
            session_counts[session_id] = session_counts.get(session_id, 0) + 1
        
        return {
            "total_connections": len(self.active_connections),
            "unique_sessions": len(session_counts),
            "session_connection_counts": session_counts
        }

# Global WebSocket manager
websocket_manager = WebSocketManager()

@router.websocket("/ws/live/{session_id}")
async def websocket_live_session(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for live session communication
    Handles real-time ayah moves, transcripts, and session updates
    """
    connection_id = None
    
    try:
        # Connect WebSocket to session
        connection_id = await websocket_manager.connect(websocket, session_id)
        
        # Verify session exists in memory
        session_status = await memory_live_session_service.get_session_status(session_id)
        if not session_status:
            await websocket.send_json({
                "type": "error",
                "message": "Session not found in memory",
                "sessionId": session_id,
                "error_code": "SESSION_NOT_FOUND"
            })
            return
        
        # Send initial session status
        await websocket.send_json({
            "type": "session_connected",
            "data": session_status,
            "message": "Connected to live session",
            "connection_id": connection_id,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Log WebSocket connection
        await transcript_logger.log_session_event(
            session_id, "websocket_connected", 
            f"WebSocket {connection_id} connected to session"
        )
        
        # Main message handling loop
        while True:
            try:
                # Receive message from client
                message = await websocket.receive()
                
                if message["type"] == "websocket.receive":
                    if "bytes" in message:
                        # Handle binary audio data (for future audio processing)
                        await handle_audio_data(websocket, session_id, connection_id, message["bytes"])
                    elif "text" in message:
                        # Handle JSON text messages
                        await handle_text_message(websocket, session_id, connection_id, message["text"])
                
            except WebSocketDisconnect:
                logger.info(f"WebSocket {connection_id} disconnected normally")
                break
            except Exception as e:
                logger.error(f"Error in WebSocket {connection_id}: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": f"Processing error: {str(e)}",
                    "sessionId": session_id,
                    "connection_id": connection_id,
                    "error_code": "PROCESSING_ERROR"
                })
                
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
        await transcript_logger.log_error(
            session_id, "websocket_error", str(e)
        )
    finally:
        # Cleanup connection
        if connection_id:
            websocket_manager.disconnect(connection_id)
        
        await transcript_logger.log_session_event(
            session_id, "websocket_disconnected", 
            f"WebSocket connection closed"
        )

async def handle_audio_data(websocket: WebSocket, session_id: str, connection_id: str, audio_bytes: bytes):
    """
    Handle incoming audio data from frontend
    For future audio processing features
    """
    try:
        # Basic audio data acknowledgment
        await websocket.send_json({
            "type": "audio_received",
            "sessionId": session_id,
            "connection_id": connection_id,
            "size": len(audio_bytes),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Log audio data received
        await transcript_logger.log_session_event(
            session_id, "audio_received",
            f"Received {len(audio_bytes)} bytes of audio data from {connection_id}"
        )
        
    except Exception as e:
        logger.error(f"Error handling audio data: {e}")
        await websocket.send_json({
            "type": "error",
            "message": f"Audio processing error: {str(e)}",
            "sessionId": session_id,
            "error_code": "AUDIO_ERROR"
        })

async def handle_text_message(websocket: WebSocket, session_id: str, connection_id: str, text_data: str):
    """
    Handle JSON text messages from frontend
    Main message handler for session commands
    """
    try:
        data = json.loads(text_data)
        message_type = data.get("type")
        
        if message_type == "move_ayah":
            await handle_move_ayah_message(websocket, session_id, connection_id, data)
        elif message_type == "transcript":
            await handle_transcript_message(websocket, session_id, connection_id, data)
        elif message_type == "get_session_status":
            await handle_session_status_request(websocket, session_id, connection_id)
        elif message_type == "ping":
            await handle_ping_message(websocket, session_id, connection_id)
        else:
            await websocket.send_json({
                "type": "error",
                "message": f"Unknown message type: {message_type}",
                "sessionId": session_id,
                "connection_id": connection_id,
                "error_code": "UNKNOWN_MESSAGE_TYPE"
            })
            
    except json.JSONDecodeError:
        await websocket.send_json({
            "type": "error",
            "message": "Invalid JSON format",
            "sessionId": session_id,
            "connection_id": connection_id,
            "error_code": "INVALID_JSON"
        })
    except Exception as e:
        logger.error(f"Error handling text message: {e}")
        await websocket.send_json({
            "type": "error",
            "message": f"Message processing error: {str(e)}",
            "sessionId": session_id,
            "connection_id": connection_id,
            "error_code": "MESSAGE_PROCESSING_ERROR"
        })

async def handle_move_ayah_message(websocket: WebSocket, session_id: str, connection_id: str, data: Dict[str, Any]):
    """
    Handle move ayah request through WebSocket
    Updates memory session and broadcasts to all clients
    """
    try:
        new_ayah = data.get("ayah")
        new_position = data.get("position", 0)
        
        if new_ayah is None:
            await websocket.send_json({
                "type": "error",
                "message": "Ayah number is required",
                "sessionId": session_id,
                "connection_id": connection_id,
                "error_code": "MISSING_AYAH"
            })
            return
        
        # Validate ayah number
        if not isinstance(new_ayah, int) or new_ayah < 1:
            await websocket.send_json({
                "type": "error",
                "message": "Invalid ayah number",
                "sessionId": session_id,
                "connection_id": connection_id,
                "error_code": "INVALID_AYAH"
            })
            return
        
        # Create move request
        move_request = MoveAyahRequest(ayah=new_ayah, position=new_position)
        
        # Move ayah in memory (this will automatically broadcast to all WebSocket clients)
        move_result = await memory_live_session_service.move_ayah(session_id, move_request)
        
        # Send confirmation to the requesting client
        await websocket.send_json({
            "type": "move_ayah_confirmed",
            "sessionId": session_id,
            "connection_id": connection_id,
            "new_ayah": move_result.ayah,
            "new_position": move_result.position,
            "message": move_result.message,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        logger.info(f"Ayah moved to {new_ayah} via WebSocket {connection_id}")
        
    except ValueError as e:
        await websocket.send_json({
            "type": "error",
            "message": str(e),
            "sessionId": session_id,
            "connection_id": connection_id,
            "error_code": "VALIDATION_ERROR"
        })
    except Exception as e:
        logger.error(f"Error moving ayah via WebSocket: {e}")
        await websocket.send_json({
            "type": "error",
            "message": f"Failed to move ayah: {str(e)}",
            "sessionId": session_id,
            "connection_id": connection_id,
            "error_code": "MOVE_AYAH_ERROR"
        })

async def handle_transcript_message(websocket: WebSocket, session_id: str, connection_id: str, data: Dict[str, Any]):
    """
    Handle transcript comparison message
    Process speech-to-text results from frontend
    """
    try:
        transcript = data.get("text", "")
        is_final = data.get("is_final", False)
        
        if not transcript:
            return
        
        # Get current session from memory
        session_status = await memory_live_session_service.get_session_status(session_id)
        if not session_status:
            await websocket.send_json({
                "type": "error",
                "message": "Session not found in memory",
                "sessionId": session_id,
                "connection_id": connection_id,
                "error_code": "SESSION_NOT_FOUND"
            })
            return
        
        # Get expected words from current ayah
        current_ayah = session_status["current_ayah"]
        current_position = session_status["position"]
        words_array = current_ayah["words_array"] or current_ayah["arabic"].split()
        
        # Compare transcript with expected words (next 10 words from current position)
        expected_words = words_array[current_position:current_position + 10]
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
            "connection_id": connection_id,
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
            "total_words": session_status["total_words"],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Send response to requesting client
        await websocket.send_json(response)
        
        # Log transcript processing
        await transcript_logger.log_transcript(
            session_id, transcript, is_final, results, summary
        )
        
        logger.info(f"Processed transcript ({'final' if is_final else 'provisional'}) via WebSocket {connection_id}")
        
    except Exception as e:
        logger.error(f"Error processing transcript via WebSocket: {e}")
        await websocket.send_json({
            "type": "error",
            "message": f"Transcript processing error: {str(e)}",
            "sessionId": session_id,
            "connection_id": connection_id,
            "error_code": "TRANSCRIPT_ERROR"
        })

async def handle_session_status_request(websocket: WebSocket, session_id: str, connection_id: str):
    """Handle request for current session status"""
    try:
        session_status = await memory_live_session_service.get_session_status(session_id)
        if session_status:
            await websocket.send_json({
                "type": "session_status",
                "sessionId": session_id,
                "connection_id": connection_id,
                "data": session_status,
                "timestamp": datetime.utcnow().isoformat()
            })
        else:
            await websocket.send_json({
                "type": "error",
                "message": "Session not found in memory",
                "sessionId": session_id,
                "connection_id": connection_id,
                "error_code": "SESSION_NOT_FOUND"
            })
    except Exception as e:
        logger.error(f"Error getting session status: {e}")
        await websocket.send_json({
            "type": "error",
            "message": f"Error getting session status: {str(e)}",
            "sessionId": session_id,
            "connection_id": connection_id,
            "error_code": "SESSION_STATUS_ERROR"
        })

async def handle_ping_message(websocket: WebSocket, session_id: str, connection_id: str):
    """Handle ping/keepalive messages"""
    await websocket.send_json({
        "type": "pong",
        "sessionId": session_id,
        "connection_id": connection_id,
        "timestamp": datetime.utcnow().isoformat()
    })

@router.websocket("/ws/monitor")
async def websocket_monitor(websocket: WebSocket):
    """
    WebSocket endpoint for monitoring all active sessions
    Useful for admin dashboard
    """
    await websocket.accept()
    
    try:
        while True:
            # Get memory statistics
            memory_stats = memory_live_session_service.get_memory_stats()
            websocket_stats = websocket_manager.get_stats()
            all_sessions = memory_live_session_service.get_all_active_sessions()
            
            # Create monitoring data
            monitor_data = {
                "type": "monitor_update",
                "memory_stats": memory_stats,
                "websocket_stats": websocket_stats,
                "active_sessions": {
                    session_id: {
                        "surah_id": session["surah_id"],
                        "ayah": session["ayah"],
                        "position": session["position"],
                        "status": session["status"],
                        "is_persisted": session["is_persisted"],
                        "updated_at": session["updated_at"].isoformat()
                    }
                    for session_id, session in all_sessions.items()
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Send monitoring data
            await websocket.send_json(monitor_data)
            
            # Wait 5 seconds before next update
            await asyncio.sleep(5)
            
    except WebSocketDisconnect:
        logger.info("Monitor WebSocket disconnected")
    except Exception as e:
        logger.error(f"Monitor WebSocket error: {e}")
        await websocket.send_json({
            "type": "error",
            "message": str(e),
            "error_code": "MONITOR_ERROR"
        })