"""
Logging utilities for transcript events
"""
import os
import logging
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

from models.session import TranscriptResult

# Create logs directory if it doesn't exist
logs_dir = Path("logs")
logs_dir.mkdir(exist_ok=True)

class TranscriptLogger:
    def __init__(self):
        self.log_file = logs_dir / "transcript.log"
        
        # Setup file logger
        self.logger = logging.getLogger("transcript")
        self.logger.setLevel(logging.INFO)
        
        # Create file handler
        if not self.logger.handlers:
            handler = logging.FileHandler(self.log_file, encoding='utf-8')
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    async def log_transcript(
        self, 
        session_id: str, 
        transcript: str, 
        is_final: bool,
        results: List[TranscriptResult],
        summary: Dict[str, int]
    ):
        """Log transcript comparison results"""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": session_id,
            "transcript": transcript,
            "is_final": is_final,
            "results": [
                {
                    "position": r.position,
                    "expected": r.expected,
                    "spoken": r.spoken,
                    "status": r.status.value,
                    "similarity_score": r.similarity_score
                }
                for r in results
            ],
            "summary": summary
        }
        
        # Log to file
        self.logger.info(f"TRANSCRIPT: {json.dumps(log_data, ensure_ascii=False)}")
        
        # Could also log to external service here (e.g., Elasticsearch, CloudWatch)
    
    async def log_session_event(
        self, 
        session_id: str, 
        event_type: str, 
        message: str,
        additional_data: Optional[Dict[str, Any]] = None
    ):
        """Log session events (start, end, errors, etc.)"""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": session_id,
            "event_type": event_type,
            "message": message,
            "additional_data": additional_data or {}
        }
        
        # Log to file
        self.logger.info(f"SESSION_EVENT: {json.dumps(log_data, ensure_ascii=False)}")
    
    async def log_error(
        self, 
        session_id: str, 
        error_type: str, 
        error_message: str,
        stack_trace: Optional[str] = None
    ):
        """Log errors"""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": session_id,
            "error_type": error_type,
            "error_message": error_message,
            "stack_trace": stack_trace
        }
        
        # Log to file
        self.logger.error(f"ERROR: {json.dumps(log_data, ensure_ascii=False)}")
    
    def get_log_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get logging statistics for the last N hours"""
        # This is a simple implementation - in production you might want
        # to use a proper log analysis tool
        try:
            if not self.log_file.exists():
                return {"error": "Log file not found"}
            
            cutoff_time = datetime.utcnow().timestamp() - (hours * 3600)
            stats = {
                "total_entries": 0,
                "transcript_entries": 0,
                "session_events": 0,
                "errors": 0,
                "sessions": set(),
                "period_hours": hours
            }
            
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        # Extract JSON from log line
                        json_start = line.find('{"timestamp"')
                        if json_start == -1:
                            continue
                        
                        json_data = json.loads(line[json_start:])
                        entry_time = datetime.fromisoformat(
                            json_data["timestamp"].replace('Z', '+00:00')
                        ).timestamp()
                        
                        if entry_time >= cutoff_time:
                            stats["total_entries"] += 1
                            
                            if "TRANSCRIPT:" in line:
                                stats["transcript_entries"] += 1
                            elif "SESSION_EVENT:" in line:
                                stats["session_events"] += 1
                            elif "ERROR:" in line:
                                stats["errors"] += 1
                            
                            if "session_id" in json_data:
                                stats["sessions"].add(json_data["session_id"])
                    
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue
            
            stats["unique_sessions"] = len(stats["sessions"])
            del stats["sessions"]  # Remove set before returning
            
            return stats
            
        except Exception as e:
            return {"error": f"Failed to analyze logs: {str(e)}"}

# Global instance
transcript_logger = TranscriptLogger()