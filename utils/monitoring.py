"""
Monitoring service untuk track performance, latency, dan metrics
"""
import time
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict, deque
import asyncio
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

class PerformanceMonitor:
    """
    Monitor performance metrics untuk berbagai operasi
    """
    
    def __init__(self, max_history_size: int = 1000):
        self.max_history_size = max_history_size
        
        # Metrics storage
        self.operation_times = defaultdict(lambda: deque(maxlen=max_history_size))
        self.operation_counts = defaultdict(int)
        self.error_counts = defaultdict(int)
        self.active_operations = defaultdict(int)
        
        # WebSocket metrics
        self.websocket_connections = 0
        self.websocket_messages = defaultdict(int)
        self.websocket_errors = defaultdict(int)
        
        # Database metrics
        self.db_query_times = deque(maxlen=max_history_size)
        self.db_query_counts = defaultdict(int)
        self.db_errors = defaultdict(int)
        
        # Audio processing metrics
        self.audio_chunks_processed = 0
        self.audio_processing_times = deque(maxlen=max_history_size)
        self.audio_quality_scores = deque(maxlen=max_history_size)
        
        # Session metrics
        self.active_sessions = set()
        self.session_durations = deque(maxlen=max_history_size)
        self.session_transcript_counts = defaultdict(int)
        
        # System start time
        self.start_time = datetime.utcnow()
    
    @asynccontextmanager
    async def track_operation(self, operation_name: str):
        """
        Context manager untuk track operation time
        Usage: async with monitor.track_operation("db_query"):
        """
        start_time = time.time()
        self.active_operations[operation_name] += 1
        
        try:
            yield
            # Success
            execution_time = time.time() - start_time
            self.operation_times[operation_name].append(execution_time)
            self.operation_counts[operation_name] += 1
            
        except Exception as e:
            # Error occurred
            self.error_counts[operation_name] += 1
            logger.error(f"Error in operation {operation_name}: {e}")
            raise
        finally:
            self.active_operations[operation_name] -= 1
    
    def track_websocket_connection(self, session_id: str, connected: bool = True):
        """Track WebSocket connections"""
        if connected:
            self.websocket_connections += 1
            self.active_sessions.add(session_id)
        else:
            self.websocket_connections = max(0, self.websocket_connections - 1)
            self.active_sessions.discard(session_id)
    
    def track_websocket_message(self, session_id: str, message_type: str):
        """Track WebSocket messages"""
        self.websocket_messages[message_type] += 1
        self.websocket_messages["total"] += 1
    
    def track_websocket_error(self, session_id: str, error_type: str):
        """Track WebSocket errors"""
        self.websocket_errors[error_type] += 1
        self.websocket_errors["total"] += 1
    
    def track_db_query(self, query_type: str, execution_time: float, success: bool = True):
        """Track database query performance"""
        self.db_query_times.append(execution_time)
        self.db_query_counts[query_type] += 1
        
        if not success:
            self.db_errors[query_type] += 1
    
    def track_audio_processing(self, processing_time: float, quality_score: float = None):
        """Track audio processing metrics"""
        self.audio_chunks_processed += 1
        self.audio_processing_times.append(processing_time)
        
        if quality_score is not None:
            self.audio_quality_scores.append(quality_score)
    
    def track_session_duration(self, session_id: str, duration_seconds: float):
        """Track session duration when ended"""
        self.session_durations.append(duration_seconds)
        if session_id in self.active_sessions:
            self.active_sessions.remove(session_id)
    
    def track_transcript_processed(self, session_id: str):
        """Track transcript processing"""
        self.session_transcript_counts[session_id] += 1
        self.session_transcript_counts["total"] += 1
    
    def get_operation_stats(self, operation_name: str = None) -> Dict[str, Any]:
        """Get statistics for specific operation or all operations"""
        if operation_name:
            times = list(self.operation_times[operation_name])
            if not times:
                return {"operation": operation_name, "no_data": True}
            
            return {
                "operation": operation_name,
                "count": self.operation_counts[operation_name],
                "errors": self.error_counts[operation_name],
                "active": self.active_operations[operation_name],
                "avg_time": sum(times) / len(times),
                "min_time": min(times),
                "max_time": max(times),
                "last_10_avg": sum(times[-10:]) / min(10, len(times))
            }
        else:
            # Return stats for all operations
            all_stats = {}
            for op_name in self.operation_times.keys():
                all_stats[op_name] = self.get_operation_stats(op_name)
            return all_stats
    
    def get_websocket_stats(self) -> Dict[str, Any]:
        """Get WebSocket statistics"""
        return {
            "active_connections": self.websocket_connections,
            "active_sessions": len(self.active_sessions),
            "message_counts": dict(self.websocket_messages),
            "error_counts": dict(self.websocket_errors),
            "sessions": list(self.active_sessions)
        }
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        query_times = list(self.db_query_times)
        
        stats = {
            "total_queries": sum(self.db_query_counts.values()),
            "query_counts": dict(self.db_query_counts),
            "error_counts": dict(self.db_errors),
        }
        
        if query_times:
            stats.update({
                "avg_query_time": sum(query_times) / len(query_times),
                "min_query_time": min(query_times),
                "max_query_time": max(query_times),
                "recent_avg": sum(query_times[-10:]) / min(10, len(query_times))
            })
        
        return stats
    
    def get_audio_stats(self) -> Dict[str, Any]:
        """Get audio processing statistics"""
        processing_times = list(self.audio_processing_times)
        quality_scores = list(self.audio_quality_scores)
        
        stats = {
            "total_chunks": self.audio_chunks_processed,
        }
        
        if processing_times:
            stats.update({
                "avg_processing_time": sum(processing_times) / len(processing_times),
                "min_processing_time": min(processing_times),
                "max_processing_time": max(processing_times)
            })
        
        if quality_scores:
            stats.update({
                "avg_quality_score": sum(quality_scores) / len(quality_scores),
                "min_quality_score": min(quality_scores),
                "max_quality_score": max(quality_scores)
            })
        
        return stats
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get session statistics"""
        durations = list(self.session_durations)
        
        stats = {
            "active_sessions": len(self.active_sessions),
            "total_transcripts": self.session_transcript_counts.get("total", 0),
            "transcript_counts": dict(self.session_transcript_counts)
        }
        
        if durations:
            stats.update({
                "avg_session_duration": sum(durations) / len(durations),
                "min_session_duration": min(durations),
                "max_session_duration": max(durations)
            })
        
        return stats
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Get overall system statistics"""
        uptime = (datetime.utcnow() - self.start_time).total_seconds()
        
        return {
            "uptime_seconds": uptime,
            "uptime_formatted": str(timedelta(seconds=int(uptime))),
            "start_time": self.start_time.isoformat(),
            "current_time": datetime.utcnow().isoformat()
        }
    
    def get_comprehensive_stats(self) -> Dict[str, Any]:
        """Get all statistics in one call"""
        return {
            "system": self.get_system_stats(),
            "operations": self.get_operation_stats(),
            "websocket": self.get_websocket_stats(),
            "database": self.get_database_stats(),
            "audio": self.get_audio_stats(),
            "sessions": self.get_session_stats()
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get system health status
        Returns: healthy, warning, critical
        """
        health_status = "healthy"
        issues = []
        warnings = []
        
        # Check error rates
        total_ops = sum(self.operation_counts.values())
        total_errors = sum(self.error_counts.values())
        
        if total_ops > 0:
            error_rate = total_errors / total_ops
            if error_rate > 0.1:  # More than 10% error rate
                health_status = "critical"
                issues.append(f"High error rate: {error_rate:.2%}")
            elif error_rate > 0.05:  # More than 5% error rate
                health_status = "warning"
                warnings.append(f"Elevated error rate: {error_rate:.2%}")
        
        # Check response times
        db_stats = self.get_database_stats()
        if "avg_query_time" in db_stats:
            if db_stats["avg_query_time"] > 2.0:  # More than 2 seconds
                health_status = "critical"
                issues.append(f"Slow database queries: {db_stats['avg_query_time']:.2f}s avg")
            elif db_stats["avg_query_time"] > 1.0:  # More than 1 second
                if health_status == "healthy":
                    health_status = "warning"
                warnings.append(f"Slow database queries: {db_stats['avg_query_time']:.2f}s avg")
        
        # Check WebSocket errors
        ws_stats = self.get_websocket_stats()
        ws_total_errors = ws_stats["error_counts"].get("total", 0)
        ws_total_messages = ws_stats["message_counts"].get("total", 0)
        
        if ws_total_messages > 0 and ws_total_errors / ws_total_messages > 0.05:
            if health_status == "healthy":
                health_status = "warning"
            warnings.append(f"WebSocket error rate: {ws_total_errors/ws_total_messages:.2%}")
        
        return {
            "status": health_status,
            "issues": issues,
            "warnings": warnings,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def reset_metrics(self):
        """Reset all metrics (useful for testing)"""
        self.operation_times.clear()
        self.operation_counts.clear()
        self.error_counts.clear()
        self.active_operations.clear()
        
        self.websocket_connections = 0
        self.websocket_messages.clear()
        self.websocket_errors.clear()
        
        self.db_query_times.clear()
        self.db_query_counts.clear()
        self.db_errors.clear()
        
        self.audio_chunks_processed = 0
        self.audio_processing_times.clear()
        self.audio_quality_scores.clear()
        
        self.active_sessions.clear()
        self.session_durations.clear()
        self.session_transcript_counts.clear()
        
        self.start_time = datetime.utcnow()

# Global monitor instance
performance_monitor = PerformanceMonitor()

# Utility functions for easy access
async def track_operation(operation_name: str):
    """Convenience function to track operations"""
    return performance_monitor.track_operation(operation_name)

def track_websocket_event(session_id: str, event_type: str, is_error: bool = False):
    """Convenience function to track WebSocket events"""
    if is_error:
        performance_monitor.track_websocket_error(session_id, event_type)
    else:
        performance_monitor.track_websocket_message(session_id, event_type)

def track_db_operation(query_type: str, execution_time: float, success: bool = True):
    """Convenience function to track database operations"""
    performance_monitor.track_db_query(query_type, execution_time, success)