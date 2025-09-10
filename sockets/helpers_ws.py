"""
WebSocket helper classes untuk connection management, audio processing,
queue handling, dan reconnect logic
"""
from fastapi import WebSocket
from typing import Dict, List, Optional, Any
import asyncio
import json
import logging
from datetime import datetime
import queue
import threading
from collections import deque

logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    Manages WebSocket connections for multiple sessions
    Handle multiple users, broadcast, reconnect
    """
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_metadata: Dict[str, Dict[str, Any]] = {}
        self.session_queues: Dict[str, asyncio.Queue] = {}
    
    async def connect(self, websocket: WebSocket, session_id: str):
        """Accept new WebSocket connection"""
        await websocket.accept()
        self.active_connections[session_id] = websocket
        self.connection_metadata[session_id] = {
            "connected_at": datetime.utcnow(),
            "last_activity": datetime.utcnow(),
            "message_count": 0,
            "reconnect_count": 0
        }
        
        # Create message queue for this session
        self.session_queues[session_id] = asyncio.Queue(maxsize=100)
        
        logger.info(f"WebSocket connected for session: {session_id}")
    
    def disconnect(self, session_id: str):
        """Disconnect and cleanup WebSocket connection"""
        if session_id in self.active_connections:
            del self.active_connections[session_id]
        
        if session_id in self.connection_metadata:
            del self.connection_metadata[session_id]
            
        if session_id in self.session_queues:
            del self.session_queues[session_id]
        
        logger.info(f"WebSocket disconnected for session: {session_id}")
    
    async def send_personal_message(self, message: Dict[str, Any], session_id: str):
        """Send message to specific session"""
        if session_id in self.active_connections:
            try:
                websocket = self.active_connections[session_id]
                await websocket.send_json(message)
                
                # Update metadata
                if session_id in self.connection_metadata:
                    self.connection_metadata[session_id]["last_activity"] = datetime.utcnow()
                    self.connection_metadata[session_id]["message_count"] += 1
                
                return True
            except Exception as e:
                logger.error(f"Error sending message to {session_id}: {e}")
                self.disconnect(session_id)
                return False
        return False
    
    async def broadcast_to_session(self, session_id: str, message: Dict[str, Any]):
        """Broadcast message to specific session (for multi-device support)"""
        return await self.send_personal_message(message, session_id)
    
    async def broadcast_to_all(self, message: Dict[str, Any]):
        """Broadcast message to all connected sessions"""
        disconnected = []
        
        for session_id, websocket in self.active_connections.items():
            try:
                await websocket.send_json(message)
                
                if session_id in self.connection_metadata:
                    self.connection_metadata[session_id]["last_activity"] = datetime.utcnow()
                    self.connection_metadata[session_id]["message_count"] += 1
                    
            except Exception as e:
                logger.error(f"Error broadcasting to {session_id}: {e}")
                disconnected.append(session_id)
        
        # Cleanup failed connections
        for session_id in disconnected:
            self.disconnect(session_id)
    
    def get_connection_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get connection information for session"""
        if session_id in self.connection_metadata:
            metadata = self.connection_metadata[session_id].copy()
            metadata["is_connected"] = session_id in self.active_connections
            return metadata
        return None
    
    def get_all_connections(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all connections"""
        return {
            session_id: self.get_connection_info(session_id)
            for session_id in self.connection_metadata
        }
    
    async def cleanup_inactive_connections(self, inactive_seconds: int = 300):
        """Cleanup connections that have been inactive"""
        current_time = datetime.utcnow()
        inactive_sessions = []
        
        for session_id, metadata in self.connection_metadata.items():
            last_activity = metadata.get("last_activity")
            if last_activity:
                seconds_inactive = (current_time - last_activity).total_seconds()
                if seconds_inactive > inactive_seconds:
                    inactive_sessions.append(session_id)
        
        for session_id in inactive_sessions:
            logger.info(f"Cleaning up inactive session: {session_id}")
            self.disconnect(session_id)

class AudioProcessor:
    """
    Process audio data received from WebSocket
    Meskipun Vosk di frontend, tetap bisa digunakan untuk monitoring atau fallback
    """
    def __init__(self):
        self.sample_rate = 16000
        self.chunk_size = 4096
        self.audio_buffers: Dict[str, deque] = {}
    
    async def preprocess_audio(self, audio_bytes: bytes, session_id: str = None) -> Optional[bytes]:
        """
        Preprocess audio data (noise reduction, normalization)
        Ini optional karena processing utama di frontend
        """
        try:
            if not audio_bytes:
                return None
            
            # Basic audio validation
            if len(audio_bytes) < 16:  # Too small to be valid audio
                return None
            
            # Store in buffer if session_id provided
            if session_id:
                if session_id not in self.audio_buffers:
                    self.audio_buffers[session_id] = deque(maxlen=100)  # Keep last 100 chunks
                
                self.audio_buffers[session_id].append({
                    "timestamp": datetime.utcnow(),
                    "size": len(audio_bytes),
                    "data": audio_bytes[:100]  # Store only first 100 bytes for monitoring
                })
            
            # Return original data (no actual processing since Vosk is in frontend)
            return audio_bytes
            
        except Exception as e:
            logger.error(f"Audio preprocessing error: {e}")
            return None
    
    def get_audio_stats(self, session_id: str) -> Dict[str, Any]:
        """Get audio statistics for session"""
        if session_id not in self.audio_buffers:
            return {"error": "No audio data found"}
        
        buffer = self.audio_buffers[session_id]
        if not buffer:
            return {"error": "Audio buffer is empty"}
        
        total_size = sum(chunk["size"] for chunk in buffer)
        avg_size = total_size / len(buffer) if buffer else 0
        
        return {
            "total_chunks": len(buffer),
            "total_bytes": total_size,
            "average_chunk_size": avg_size,
            "latest_timestamp": buffer[-1]["timestamp"].isoformat() if buffer else None,
            "oldest_timestamp": buffer[0]["timestamp"].isoformat() if buffer else None
        }
    
    def clear_audio_buffer(self, session_id: str):
        """Clear audio buffer for session"""
        if session_id in self.audio_buffers:
            self.audio_buffers[session_id].clear()

class MessageQueue:
    """
    Handle message queuing for WebSocket connections
    Untuk handle burst messages dan ensure delivery order
    """
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.queues: Dict[str, queue.Queue] = {}
        self.processing_tasks: Dict[str, asyncio.Task] = {}
    
    def create_queue(self, session_id: str):
        """Create message queue for session"""
        self.queues[session_id] = queue.Queue(maxsize=self.max_size)
    
    def add_message(self, session_id: str, message: Dict[str, Any]) -> bool:
        """Add message to queue"""
        if session_id not in self.queues:
            self.create_queue(session_id)
        
        try:
            self.queues[session_id].put_nowait({
                "message": message,
                "timestamp": datetime.utcnow(),
                "retry_count": 0
            })
            return True
        except queue.Full:
            logger.warning(f"Message queue full for session {session_id}")
            return False
    
    async def process_queue(self, session_id: str, connection_manager: ConnectionManager):
        """Process messages in queue for session"""
        if session_id not in self.queues:
            return
        
        message_queue = self.queues[session_id]
        
        while True:
            try:
                # Get message from queue (blocking)
                queue_item = message_queue.get(timeout=1.0)
                message = queue_item["message"]
                
                # Try to send message
                success = await connection_manager.send_personal_message(message, session_id)
                
                if not success:
                    # Retry logic
                    queue_item["retry_count"] += 1
                    if queue_item["retry_count"] <= 3:
                        message_queue.put_nowait(queue_item)
                    else:
                        logger.error(f"Failed to send message after 3 retries: {session_id}")
                
                message_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error processing queue for {session_id}: {e}")
                await asyncio.sleep(1)
    
    def start_processing(self, session_id: str, connection_manager: ConnectionManager):
        """Start queue processing task for session"""
        if session_id in self.processing_tasks:
            return  # Already processing
        
        self.processing_tasks[session_id] = asyncio.create_task(
            self.process_queue(session_id, connection_manager)
        )
    
    def stop_processing(self, session_id: str):
        """Stop queue processing for session"""
        if session_id in self.processing_tasks:
            self.processing_tasks[session_id].cancel()
            del self.processing_tasks[session_id]
        
        if session_id in self.queues:
            del self.queues[session_id]
    
    def get_queue_stats(self, session_id: str) -> Dict[str, Any]:
        """Get queue statistics"""
        if session_id not in self.queues:
            return {"error": "Queue not found"}
        
        message_queue = self.queues[session_id]
        return {
            "queue_size": message_queue.qsize(),
            "max_size": self.max_size,
            "is_processing": session_id in self.processing_tasks
        }

class ReconnectHandler:
    """
    Handle WebSocket reconnection logic
    """
    def __init__(self):
        self.reconnect_attempts: Dict[str, int] = {}
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 2  # seconds
    
    def should_allow_reconnect(self, session_id: str) -> bool:
        """Check if reconnection should be allowed"""
        attempts = self.reconnect_attempts.get(session_id, 0)
        return attempts < self.max_reconnect_attempts
    
    def record_reconnect_attempt(self, session_id: str):
        """Record reconnection attempt"""
        self.reconnect_attempts[session_id] = self.reconnect_attempts.get(session_id, 0) + 1
    
    def reset_reconnect_count(self, session_id: str):
        """Reset reconnection count on successful connection"""
        if session_id in self.reconnect_attempts:
            del self.reconnect_attempts[session_id]
    
    def get_reconnect_delay(self, session_id: str) -> int:
        """Get delay before next reconnection attempt"""
        attempts = self.reconnect_attempts.get(session_id, 0)
        # Exponential backoff: 2, 4, 8, 16, 32 seconds
        return min(self.reconnect_delay * (2 ** attempts), 32)
    
    def cleanup_old_attempts(self, hours: int = 1):
        """Cleanup old reconnection attempts"""
        # This would need timestamp tracking to implement properly
        # For now, just clear all attempts
        self.reconnect_attempts.clear()

class RateLimiter:
    """
    Rate limiting for WebSocket messages
    Prevent spam dan abuse
    """
    def __init__(self, max_messages_per_second: int = 10):
        self.max_messages_per_second = max_messages_per_second
        self.message_timestamps: Dict[str, deque] = {}
    
    def is_rate_limited(self, session_id: str) -> bool:
        """Check if session is rate limited"""
        current_time = datetime.utcnow()
        
        if session_id not in self.message_timestamps:
            self.message_timestamps[session_id] = deque(maxlen=100)
        
        timestamps = self.message_timestamps[session_id]
        
        # Remove old timestamps (older than 1 second)
        while timestamps and (current_time - timestamps[0]).total_seconds() > 1.0:
            timestamps.popleft()
        
        # Check if rate limit exceeded
        if len(timestamps) >= self.max_messages_per_second:
            return True
        
        # Record this message
        timestamps.append(current_time)
        return False
    
    def get_rate_info(self, session_id: str) -> Dict[str, Any]:
        """Get rate limiting info for session"""
        if session_id not in self.message_timestamps:
            return {"messages_in_last_second": 0, "rate_limited": False}
        
        current_time = datetime.utcnow()
        timestamps = self.message_timestamps[session_id]
        
        # Count messages in last second
        recent_messages = sum(
            1 for ts in timestamps 
            if (current_time - ts).total_seconds() <= 1.0
        )
        
        return {
            "messages_in_last_second": recent_messages,
            "max_allowed": self.max_messages_per_second,
            "rate_limited": recent_messages >= self.max_messages_per_second
        }