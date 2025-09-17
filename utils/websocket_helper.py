"""
WebSocket helper classes for connection management and audio processing
Separated from the original sockets/helpers_ws.py for clarity
"""
from typing import Dict, List, Any, Optional
from datetime import datetime
import asyncio
import logging
from fastapi import WebSocket
import json

logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    Enhanced connection manager for WebSocket sessions
    Handles multiple connections per session and broadcasting
    """
    
    def __init__(self):
        # Active connections: session_id -> list of websockets
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # Connection metadata: connection_id -> metadata
        self.connection_metadata: Dict[str, Dict[str, Any]] = {}
        # Connection counter for unique IDs
        self._connection_counter = 0
    
    def _generate_connection_id(self) -> str:
        """Generate unique connection ID"""
        self._connection_counter += 1
        return f"conn_{self._connection_counter}_{int(datetime.utcnow().timestamp())}"
    
    async def connect(self, websocket: WebSocket, session_id: str) -> str:
        """Connect WebSocket to session and return connection ID"""
        await websocket.accept()
        
        # Generate unique connection ID
        connection_id = self._generate_connection_id()
        
        # Add to session connections
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        
        self.active_connections[session_id].append(websocket)
        
        # Store connection metadata
        self.connection_metadata[connection_id] = {
            "session_id": session_id,
            "websocket": websocket,
            "connected_at": datetime.utcnow(),
            "message_count": 0
        }
        
        logger.info(f"WebSocket connected: {connection_id} -> session {session_id}")
        return connection_id
    
    def disconnect(self, session_id: str, websocket: WebSocket = None, connection_id: str = None):
        """Disconnect WebSocket from session"""
        
        # Remove from session connections
        if session_id in self.active_connections:
            if websocket and websocket in self.active_connections[session_id]:
                self.active_connections[session_id].remove(websocket)
            
            # Clean up empty session lists
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
        
        # Remove from metadata
        if connection_id and connection_id in self.connection_metadata:
            del self.connection_metadata[connection_id]
        
        # If no connection_id provided, find it by websocket
        if not connection_id and websocket:
            for conn_id, metadata in list(self.connection_metadata.items()):
                if metadata["websocket"] == websocket:
                    del self.connection_metadata[conn_id]
                    connection_id = conn_id
                    break
        
        logger.info(f"WebSocket disconnected: {connection_id or 'unknown'} from session {session_id}")
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send message to specific WebSocket connection"""
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
    
    async def broadcast_to_session(self, session_id: str, message: dict):
        """Broadcast message to all connections in a session"""
        if session_id not in self.active_connections:
            return
        
        # Get all connections for this session
        connections = self.active_connections[session_id][:]  # Create copy
        
        # Send to all connections
        for websocket in connections:
            try:
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error broadcasting to session {session_id}: {e}")
                # Remove broken connection
                if websocket in self.active_connections.get(session_id, []):
                    self.active_connections[session_id].remove(websocket)
    
    async def broadcast_to_all(self, message: dict, exclude_session: str = None):
        """Broadcast message to all active connections"""
        for session_id, connections in self.active_connections.items():
            if exclude_session and session_id == exclude_session:
                continue
                
            await self.broadcast_to_session(session_id, message)
    
    def get_session_connections(self, session_id: str) -> List[WebSocket]:
        """Get all WebSocket connections for a session"""
        return self.active_connections.get(session_id, [])
    
    def get_connection_count(self, session_id: str = None) -> int:
        """Get connection count for session or total"""
        if session_id:
            return len(self.active_connections.get(session_id, []))
        else:
            return sum(len(conns) for conns in self.active_connections.values())
    
    def get_active_sessions(self) -> List[str]:
        """Get list of sessions with active connections"""
        return list(self.active_connections.keys())
    
    def get_stats(self) -> Dict[str, Any]:
        """Get connection manager statistics"""
        session_connection_counts = {
            session_id: len(connections) 
            for session_id, connections in self.active_connections.items()
        }
        
        return {
            "total_connections": sum(session_connection_counts.values()),
            "active_sessions": len(self.active_connections),
            "session_connection_counts": session_connection_counts,
            "connection_metadata_count": len(self.connection_metadata)
        }
    
    def cleanup_broken_connections(self):
        """Remove any broken WebSocket connections"""
        cleanup_count = 0
        
        for session_id, connections in list(self.active_connections.items()):
            valid_connections = []
            
            for websocket in connections:
                # Check if connection is still valid
                try:
                    # This is a simple check - in practice you might want a more sophisticated method
                    if hasattr(websocket, 'client_state') and websocket.client_state.name == 'DISCONNECTED':
                        cleanup_count += 1
                        continue
                    valid_connections.append(websocket)
                except:
                    cleanup_count += 1
                    continue
            
            if valid_connections:
                self.active_connections[session_id] = valid_connections
            else:
                del self.active_connections[session_id]
        
        logger.info(f"Cleaned up {cleanup_count} broken connections")
        return cleanup_count

class AudioProcessor:
    """
    Audio processing helper for WebSocket audio data
    Basic implementation for monitoring and validation
    """
    
    def __init__(self):
        self.processed_chunks = 0
        self.total_bytes_processed = 0
        self.processing_errors = 0
        
        # Audio format settings
        self.sample_rate = 16000
        self.channels = 1
        self.bit_depth = 16
    
    async def preprocess_audio(self, audio_bytes: bytes, session_id: str = None) -> Optional[bytes]:
        """
        Preprocess audio data from WebSocket
        Since Vosk is running on frontend, this is mainly for monitoring
        """
        try:
            if not audio_bytes:
                return None
            
            # Basic validation
            if len(audio_bytes) < 32:  # Minimum chunk size
                logger.warning(f"Audio chunk too small: {len(audio_bytes)} bytes")
                return None
            
            # Update statistics
            self.processed_chunks += 1
            self.total_bytes_processed += len(audio_bytes)
            
            # Log processing (can be made optional for performance)
            if session_id:
                logger.debug(f"Processed audio chunk for {session_id}: {len(audio_bytes)} bytes")
            
            # Return original bytes (no actual processing needed since Vosk is frontend)
            return audio_bytes
            
        except Exception as e:
            logger.error(f"Audio preprocessing error: {e}")
            self.processing_errors += 1
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get audio processing statistics"""
        return {
            "processed_chunks": self.processed_chunks,
            "total_bytes_processed": self.total_bytes_processed,
            "processing_errors": self.processing_errors,
            "avg_chunk_size": (
                self.total_bytes_processed / self.processed_chunks 
                if self.processed_chunks > 0 else 0
            ),
            "settings": {
                "sample_rate": self.sample_rate,
                "channels": self.channels,
                "bit_depth": self.bit_depth
            }
        }
    
    def reset_stats(self):
        """Reset processing statistics"""
        self.processed_chunks = 0
        self.total_bytes_processed = 0
        self.processing_errors = 0

class MessageHandler:
    """
    Helper class for handling different types of WebSocket messages
    """
    
    def __init__(self):
        self.message_handlers = {}
        self.message_count = 0
        self.error_count = 0
    
    def register_handler(self, message_type: str, handler_func):
        """Register a handler function for a message type"""
        self.message_handlers[message_type] = handler_func
    
    async def handle_message(self, message_data: dict, websocket: WebSocket, session_id: str, connection_id: str):
        """Handle incoming WebSocket message"""
        try:
            message_type = message_data.get("type")
            self.message_count += 1
            
            if not message_type:
                await self._send_error(websocket, "Missing message type", session_id, connection_id)
                return
            
            # Get handler for message type
            handler = self.message_handlers.get(message_type)
            if not handler:
                await self._send_error(
                    websocket, 
                    f"Unknown message type: {message_type}", 
                    session_id, 
                    connection_id
                )
                return
            
            # Call handler
            await handler(message_data, websocket, session_id, connection_id)
            
        except Exception as e:
            logger.error(f"Message handling error: {e}")
            self.error_count += 1
            await self._send_error(
                websocket, 
                f"Message processing error: {str(e)}", 
                session_id, 
                connection_id
            )
    
    async def _send_error(self, websocket: WebSocket, error_message: str, session_id: str, connection_id: str):
        """Send error message to WebSocket client"""
        error_response = {
            "type": "error",
            "message": error_message,
            "sessionId": session_id,
            "connection_id": connection_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        try:
            await websocket.send_text(json.dumps(error_response))
        except Exception as e:
            logger.error(f"Error sending error message: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get message handling statistics"""
        return {
            "total_messages": self.message_count,
            "total_errors": self.error_count,
            "registered_handlers": list(self.message_handlers.keys()),
            "error_rate": (
                self.error_count / self.message_count 
                if self.message_count > 0 else 0
            )
        }

# ===== UTILITY FUNCTIONS =====

def validate_session_id(session_id: str) -> bool:
    """Validate session ID format"""
    if not session_id or not isinstance(session_id, str):
        return False
    
    # Basic UUID format check (can be made more strict)
    if len(session_id) < 10:
        return False
    
    return True

def format_websocket_error(error_code: str, message: str, session_id: str = None, connection_id: str = None) -> dict:
    """Format standardized WebSocket error response"""
    return {
        "type": "error",
        "error_code": error_code,
        "message": message,
        "sessionId": session_id,
        "connection_id": connection_id,
        "timestamp": datetime.utcnow().isoformat()
    }

def format_websocket_success(message_type: str, data: dict, session_id: str = None, connection_id: str = None) -> dict:
    """Format standardized WebSocket success response"""
    return {
        "type": message_type,
        "sessionId": session_id,
        "connection_id": connection_id,
        "timestamp": datetime.utcnow().isoformat(),
        **data
    }

async def safe_websocket_send(websocket: WebSocket, message: dict) -> bool:
    """Safely send WebSocket message with error handling"""
    try:
        await websocket.send_text(json.dumps(message))
        return True
    except Exception as e:
        logger.error(f"Failed to send WebSocket message: {e}")
        return False

# ===== BACKGROUND TASKS =====

class WebSocketMaintenanceTask:
    """
    Background task for WebSocket connection maintenance
    """
    
    def __init__(self, connection_manager: ConnectionManager):
        self.connection_manager = connection_manager
        self.is_running = False
        self.cleanup_interval = 60  # seconds
    
    async def start(self):
        """Start the maintenance task"""
        if self.is_running:
            return
        
        self.is_running = True
        logger.info("Starting WebSocket maintenance task")
        
        try:
            while self.is_running:
                await asyncio.sleep(self.cleanup_interval)
                
                if self.is_running:  # Check again after sleep
                    await self._perform_maintenance()
                
        except Exception as e:
            logger.error(f"WebSocket maintenance task error: {e}")
        finally:
            self.is_running = False
    
    async def stop(self):
        """Stop the maintenance task"""
        self.is_running = False
        logger.info("WebSocket maintenance task stopped")
    
    async def _perform_maintenance(self):
        """Perform maintenance tasks"""
        try:
            # Clean up broken connections
            cleanup_count = self.connection_manager.cleanup_broken_connections()
            
            if cleanup_count > 0:
                logger.info(f"WebSocket maintenance: cleaned up {cleanup_count} connections")
            
            # Log connection statistics
            stats = self.connection_manager.get_stats()
            logger.debug(f"WebSocket stats: {stats}")
            
        except Exception as e:
            logger.error(f"WebSocket maintenance error: {e}")

# Create global instances that can be imported
default_connection_manager = ConnectionManager()
default_audio_processor = AudioProcessor()
default_message_handler = MessageHandler()