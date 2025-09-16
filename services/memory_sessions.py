"""
Memory-based Live Session Management Service
Keeps sessions in memory during active use, persists to database only on end
"""
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging
import asyncio

from models.session import (
    LiveSession, SessionStatus, SessionMode,
    StartSessionRequest, StartSessionResponse,
    UpdateSessionRequest, UpdateSessionResponse,
    EndSessionResponse, MoveAyahRequest, MoveAyahResponse
)
from services.supabase import supabase_service
from utils.logging import transcript_logger

logger = logging.getLogger(__name__)

class MemorySessionStore:
    """
    In-memory session storage with persistence control
    """
    def __init__(self):
        # Main session store: session_id -> session_data
        self._sessions: Dict[str, Dict[str, Any]] = {}
        
        # WebSocket connections per session: session_id -> list of websockets
        self._websocket_connections: Dict[str, List] = {}
        
        # Session metadata
        self._session_metadata: Dict[str, Dict[str, Any]] = {}
    
    def create_session(self, session_data: Dict[str, Any]) -> str:
        """Create new session in memory"""
        session_id = str(uuid.uuid4())
        
        # Create session with metadata
        self._sessions[session_id] = {
            "session_id": session_id,
            "user_id": session_data["user_id"],
            "surah_id": session_data["surah_id"],
            "ayah": session_data["ayah"],
            "position": session_data.get("position", 0),
            "mode": session_data["mode"],
            "data": session_data.get("data", {}),
            "status": SessionStatus.ACTIVE.value,
            "is_persisted": False,  # Key flag for persistence
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        # Initialize WebSocket connections list
        self._websocket_connections[session_id] = []
        
        # Session metadata for tracking
        self._session_metadata[session_id] = {
            "total_ayah_moves": 0,
            "total_transcripts": 0,
            "start_time": datetime.utcnow(),
            "last_activity": datetime.utcnow()
        }
        
        logger.info(f"Created memory session: {session_id}")
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session from memory"""
        return self._sessions.get(session_id)
    
    def update_session(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """Update session in memory"""
        if session_id not in self._sessions:
            return False
        
        # Update session data
        self._sessions[session_id].update(updates)
        self._sessions[session_id]["updated_at"] = datetime.utcnow()
        
        # Update metadata
        if session_id in self._session_metadata:
            self._session_metadata[session_id]["last_activity"] = datetime.utcnow()
            
            # Track specific updates
            if "ayah" in updates:
                self._session_metadata[session_id]["total_ayah_moves"] += 1
        
        return True
    
    def move_ayah(self, session_id: str, new_ayah: int, new_position: int = 0) -> bool:
        """Move session to different ayah"""
        if session_id not in self._sessions:
            return False
        
        # Update ayah and position
        updates = {
            "ayah": new_ayah,
            "position": new_position,
            "updated_at": datetime.utcnow()
        }
        
        return self.update_session(session_id, updates)
    
    def mark_persisted(self, session_id: str) -> bool:
        """Mark session as persisted to database"""
        if session_id not in self._sessions:
            return False
        
        self._sessions[session_id]["is_persisted"] = True
        return True
    
    def delete_session(self, session_id: str) -> bool:
        """Remove session from memory after persistence"""
        if session_id in self._sessions:
            del self._sessions[session_id]
        
        if session_id in self._websocket_connections:
            del self._websocket_connections[session_id]
        
        if session_id in self._session_metadata:
            del self._session_metadata[session_id]
        
        logger.info(f"Deleted memory session: {session_id}")
        return True
    
    def add_websocket(self, session_id: str, websocket) -> bool:
        """Add WebSocket connection to session"""
        if session_id not in self._websocket_connections:
            self._websocket_connections[session_id] = []
        
        if websocket not in self._websocket_connections[session_id]:
            self._websocket_connections[session_id].append(websocket)
            logger.info(f"Added WebSocket to session {session_id}")
            return True
        
        return False
    
    def remove_websocket(self, session_id: str, websocket) -> bool:
        """Remove WebSocket connection from session"""
        if session_id in self._websocket_connections:
            try:
                self._websocket_connections[session_id].remove(websocket)
                logger.info(f"Removed WebSocket from session {session_id}")
                return True
            except ValueError:
                pass
        
        return False
    
    def get_websockets(self, session_id: str) -> List:
        """Get all WebSocket connections for session"""
        return self._websocket_connections.get(session_id, [])
    
    def get_all_sessions(self) -> Dict[str, Dict[str, Any]]:
        """Get all active sessions"""
        return self._sessions.copy()
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get memory store statistics"""
        total_sessions = len(self._sessions)
        total_connections = sum(len(conns) for conns in self._websocket_connections.values())
        
        persisted_count = sum(1 for session in self._sessions.values() if session.get("is_persisted", False))
        active_count = total_sessions - persisted_count
        
        return {
            "total_sessions": total_sessions,
            "active_sessions": active_count,
            "persisted_sessions": persisted_count,
            "total_websocket_connections": total_connections,
            "sessions_with_connections": len([s for s in self._websocket_connections.values() if s])
        }

class MemoryLiveSessionService:
    """
    Live session service using memory storage with selective persistence
    """
    def __init__(self):
        self.memory_store = MemorySessionStore()
    
    async def start_session(self, request: StartSessionRequest) -> StartSessionResponse:
        """Start new session in memory (no database write)"""
        try:
            # Validate ayah exists
            ayah_data = await supabase_service.get_ayat(request.surah_id, request.ayah)
            if not ayah_data:
                raise ValueError(f"Ayah {request.surah_id}:{request.ayah} not found")
            
            # Create session in memory
            session_data = {
                "user_id": request.user_id,
                "surah_id": request.surah_id,
                "ayah": request.ayah,
                "position": 0,
                "mode": request.mode.value,
                "data": request.data or {}
            }
            
            session_id = self.memory_store.create_session(session_data)
            
            # Log session start (no database persistence)
            await transcript_logger.log_session_event(
                session_id, "session_started_memory", 
                f"Started memory session for {request.surah_id}:{request.ayah}"
            )
            
            return StartSessionResponse(
                sessionId=session_id,
                surah_id=request.surah_id,
                ayah=request.ayah,
                status=SessionStatus.ACTIVE,
                position=0,
                message="Session started in memory"
            )
            
        except Exception as e:
            logger.error(f"Error starting memory session: {e}")
            raise
    
    async def move_ayah(self, session_id: str, request: MoveAyahRequest) -> MoveAyahResponse:
        """Move ayah in memory and broadcast to WebSocket clients"""
        try:
            # Get current session
            session = self.memory_store.get_session(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found in memory")
            
            # Validate new ayah exists
            ayah_data = await supabase_service.get_ayat(session["surah_id"], request.ayah)
            if not ayah_data:
                raise ValueError(f"Ayah {session['surah_id']}:{request.ayah} not found")
            
            # Update ayah in memory
            success = self.memory_store.move_ayah(session_id, request.ayah, request.position)
            if not success:
                raise ValueError(f"Failed to update session {session_id} in memory")
            
            # Get updated session
            updated_session = self.memory_store.get_session(session_id)
            
            # Broadcast to WebSocket clients
            await self._broadcast_ayah_move(session_id, {
                "sessionId": session_id,
                "surah_id": updated_session["surah_id"],
                "previous_ayah": session["ayah"],
                "new_ayah": request.ayah,
                "new_position": request.position,
                "ayah_data": {
                    "arabic": ayah_data.arabic,
                    "transliteration": ayah_data.transliteration,
                    "words_array": ayah_data.words_array or [],
                    "total_words": len(ayah_data.words_array or ayah_data.arabic.split())
                },
                "message": f"Moved to ayah {request.ayah}",
                "updated_at": updated_session["updated_at"].isoformat()
            })
            
            # Log ayah move
            await transcript_logger.log_session_event(
                session_id, "ayah_moved_memory",
                f"Moved from {session['ayah']} to {request.ayah} in memory"
            )
            
            return MoveAyahResponse(
                sessionId=session_id,
                surah_id=updated_session["surah_id"],
                ayah=request.ayah,
                status=SessionStatus.ACTIVE,
                position=request.position,
                message=f"Moved to ayah {request.ayah} in memory"
            )
            
        except Exception as e:
            logger.error(f"Error moving ayah in memory: {e}")
            raise
    
    async def get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get current session status from memory"""
        session = self.memory_store.get_session(session_id)
        if not session:
            return None
        
        # Get current ayah data
        ayah_data = await supabase_service.get_ayat(session["surah_id"], session["ayah"])
        if not ayah_data:
            return None
        
        return {
            "sessionId": session_id,
            "status": session["status"],
            "surah_id": session["surah_id"],
            "ayah": session["ayah"],
            "position": session["position"],
            "mode": session["mode"],
            "is_persisted": session["is_persisted"],
            "total_words": len(ayah_data.words_array or ayah_data.arabic.split()),
            "current_ayah": {
                "arabic": ayah_data.arabic,
                "transliteration": ayah_data.transliteration,
                "words_array": ayah_data.words_array
            },
            "created_at": session["created_at"].isoformat(),
            "updated_at": session["updated_at"].isoformat()
        }
    
    async def end_session(self, session_id: str) -> EndSessionResponse:
        """End session and persist to database"""
        try:
            # Get session from memory
            session = self.memory_store.get_session(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found in memory")
            
            # Create LiveSession object for database persistence
            live_session = LiveSession(
                id=session_id,
                user_id=session["user_id"],
                surah_id=session["surah_id"],
                ayah=session["ayah"],
                position=session["position"],
                mode=SessionMode(session["mode"]),
                data=session["data"],
                status=SessionStatus.ENDED,
                created_at=session["created_at"],
                updated_at=datetime.utcnow()
            )
            
            # Persist to database
            await supabase_service.create_live_session(live_session)
            
            # Mark as persisted in memory
            self.memory_store.mark_persisted(session_id)
            
            # Broadcast session ended to WebSocket clients
            await self._broadcast_session_ended(session_id, {
                "sessionId": session_id,
                "status": "ended",
                "message": "Session ended and saved to database",
                "final_ayah": session["ayah"],
                "final_position": session["position"],
                "ended_at": datetime.utcnow().isoformat()
            })
            
            # Log session end
            await transcript_logger.log_session_event(
                session_id, "session_ended_persisted",
                f"Session ended and persisted to database"
            )
            
            # Clean up from memory after a short delay (allow WebSocket messages to send)
            asyncio.create_task(self._delayed_cleanup(session_id, 2))
            
            return EndSessionResponse(
                sessionId=session_id,
                status=SessionStatus.ENDED,
                message="Session ended and saved to database"
            )
            
        except Exception as e:
            logger.error(f"Error ending session {session_id}: {e}")
            raise
    
    async def add_websocket_connection(self, session_id: str, websocket) -> bool:
        """Add WebSocket connection to session"""
        return self.memory_store.add_websocket(session_id, websocket)
    
    async def remove_websocket_connection(self, session_id: str, websocket) -> bool:
        """Remove WebSocket connection from session"""
        return self.memory_store.remove_websocket(session_id, websocket)
    
    async def _broadcast_ayah_move(self, session_id: str, data: Dict[str, Any]):
        """Broadcast ayah move to all WebSocket clients"""
        websockets = self.memory_store.get_websockets(session_id)
        
        message = {
            "type": "ayah_moved",
            **data,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Send to all connected WebSockets
        for websocket in websockets[:]:  # Create copy to avoid modification during iteration
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to WebSocket: {e}")
                # Remove broken WebSocket
                self.memory_store.remove_websocket(session_id, websocket)
    
    async def _broadcast_session_ended(self, session_id: str, data: Dict[str, Any]):
        """Broadcast session ended to all WebSocket clients"""
        websockets = self.memory_store.get_websockets(session_id)
        
        message = {
            "type": "session_ended",
            **data,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Send to all connected WebSockets
        for websocket in websockets[:]:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting session end: {e}")
    
    async def _delayed_cleanup(self, session_id: str, delay_seconds: int):
        """Clean up session from memory after delay"""
        await asyncio.sleep(delay_seconds)
        self.memory_store.delete_session(session_id)
        logger.info(f"Cleaned up memory session: {session_id}")
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory store statistics"""
        return self.memory_store.get_session_stats()
    
    def get_all_active_sessions(self) -> Dict[str, Dict[str, Any]]:
        """Get all sessions from memory"""
        return self.memory_store.get_all_sessions()

# Global instance
memory_live_session_service = MemoryLiveSessionService()