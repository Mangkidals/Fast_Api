"""
Audio preprocessing service
Meskipun Vosk ada di frontend, tetap diperlukan untuk monitoring,
validation, dan preprocessing jika diperlukan di backend
"""
import io
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)

class AudioProcessingService:
    """
    Service untuk preprocessing audio data yang diterima dari WebSocket
    Berguna untuk monitoring, validation, dan basic preprocessing
    """
    
    def __init__(self):
        self.sample_rate = 16000  # Standard untuk speech recognition
        self.channels = 1  # Mono
        self.bit_depth = 16  # 16-bit PCM
        self.chunk_duration = 0.1  # 100ms chunks
        self.min_chunk_size = 32  # Minimum bytes untuk valid audio
        self.max_chunk_size = 8192  # Maximum bytes per chunk
        
        # Stats tracking
        self.processing_stats = {
            "total_chunks_processed": 0,
            "total_bytes_processed": 0,
            "invalid_chunks": 0,
            "last_processed": None
        }
    
    def validate_audio_chunk(self, audio_bytes: bytes) -> Dict[str, Any]:
        """
        Validate incoming audio chunk
        Return validation result dengan detail info
        """
        validation_result = {
            "is_valid": False,
            "size": len(audio_bytes) if audio_bytes else 0,
            "errors": [],
            "warnings": []
        }
        
        try:
            # Check if audio_bytes exists
            if not audio_bytes:
                validation_result["errors"].append("Empty audio data")
                return validation_result
            
            # Check size constraints
            if len(audio_bytes) < self.min_chunk_size:
                validation_result["errors"].append(f"Audio chunk too small: {len(audio_bytes)} bytes (min: {self.min_chunk_size})")
            
            if len(audio_bytes) > self.max_chunk_size:
                validation_result["warnings"].append(f"Audio chunk very large: {len(audio_bytes)} bytes (max recommended: {self.max_chunk_size})")
            
            # Check if size is reasonable for PCM16 data
            if len(audio_bytes) % 2 != 0:
                validation_result["warnings"].append("Audio data size is odd, might not be valid PCM16")
            
            # Basic header validation (if present)
            if len(audio_bytes) >= 4:
                # Check for common audio formats
                header = audio_bytes[:4]
                if header == b'RIFF':
                    validation_result["format"] = "WAV"
                elif header[:2] == b'\xff\xf' or header[:2] == b'\xff\xe':
                    validation_result["format"] = "MP3"
                else:
                    validation_result["format"] = "RAW_PCM"
            
            # Mark as valid if no critical errors
            validation_result["is_valid"] = len(validation_result["errors"]) == 0
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Audio validation error: {e}")
            validation_result["errors"].append(f"Validation exception: {str(e)}")
            return validation_result
    
    async def preprocess_audio(self, audio_bytes: bytes, session_id: str = None) -> Optional[bytes]:
        """
        Preprocess audio data
        Basic preprocessing untuk monitoring dan logging
        """
        try:
            # Validate first
            validation = self.validate_audio_chunk(audio_bytes)
            if not validation["is_valid"]:
                logger.warning(f"Invalid audio chunk for session {session_id}: {validation['errors']}")
                self.processing_stats["invalid_chunks"] += 1
                return None
            
            # Update stats
            self.processing_stats["total_chunks_processed"] += 1
            self.processing_stats["total_bytes_processed"] += len(audio_bytes)
            self.processing_stats["last_processed"] = datetime.utcnow().isoformat()
            
            # Log audio info untuk monitoring
            if session_id:
                logger.info(f"Processed audio chunk for {session_id}: {len(audio_bytes)} bytes, format: {validation.get('format', 'unknown')}")
            
            # Return original bytes (no actual processing since Vosk is in frontend)
            # Bisa ditambahkan actual preprocessing di sini jika diperlukan
            return audio_bytes
            
        except Exception as e:
            logger.error(f"Audio preprocessing error: {e}")
            self.processing_stats["invalid_chunks"] += 1
            return None
    
    def analyze_audio_quality(self, audio_bytes: bytes) -> Dict[str, Any]:
        """
        Analyze audio quality metrics
        Berguna untuk monitoring dan debugging
        """
        quality_metrics = {
            "size": len(audio_bytes),
            "estimated_duration": 0.0,
            "estimated_samples": 0,
            "quality_score": 0.0,
            "issues": []
        }
        
        try:
            if not audio_bytes or len(audio_bytes) < 16:
                quality_metrics["issues"].append("Audio too short for analysis")
                return quality_metrics
            
            # Estimate duration (assuming PCM16, mono, 16kHz)
            bytes_per_sample = 2  # 16-bit = 2 bytes
            estimated_samples = len(audio_bytes) // bytes_per_sample
            estimated_duration = estimated_samples / self.sample_rate
            
            quality_metrics["estimated_samples"] = estimated_samples
            quality_metrics["estimated_duration"] = estimated_duration
            
            # Basic quality scoring based on size and consistency
            if estimated_duration < 0.05:  # Less than 50ms
                quality_metrics["issues"].append("Very short audio chunk")
                quality_metrics["quality_score"] = 0.3
            elif estimated_duration > 1.0:  # More than 1 second
                quality_metrics["issues"].append("Very long audio chunk")
                quality_metrics["quality_score"] = 0.7
            else:
                quality_metrics["quality_score"] = 0.9
            
            # Check for silence (all zeros)
            if audio_bytes.count(b'\x00') == len(audio_bytes):
                quality_metrics["issues"].append("Audio appears to be silence")
                quality_metrics["quality_score"] = 0.1
            
            return quality_metrics
            
        except Exception as e:
            logger.error(f"Audio quality analysis error: {e}")
            quality_metrics["issues"].append(f"Analysis error: {str(e)}")
            return quality_metrics
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""
        return self.processing_stats.copy()
    
    def reset_processing_stats(self):
        """Reset processing statistics"""
        self.processing_stats = {
            "total_chunks_processed": 0,
            "total_bytes_processed": 0,
            "invalid_chunks": 0,
            "last_processed": None
        }
    
    def get_recommended_settings(self) -> Dict[str, Any]:
        """
        Get recommended audio settings untuk frontend
        """
        return {
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "bit_depth": self.bit_depth,
            "format": "PCM16",
            "chunk_duration_ms": int(self.chunk_duration * 1000),
            "min_chunk_size": self.min_chunk_size,
            "max_chunk_size": self.max_chunk_size,
            "encoding": "little-endian"
        }
    
    def calculate_bandwidth_usage(self, session_duration_seconds: float) -> Dict[str, Any]:
        """
        Calculate estimated bandwidth usage
        Berguna untuk monitoring dan optimization
        """
        try:
            # Calculate based on recommended settings
            bytes_per_second = self.sample_rate * self.channels * (self.bit_depth // 8)
            total_bytes = bytes_per_second * session_duration_seconds
            
            # Convert to different units
            kilobytes = total_bytes / 1024
            megabytes = kilobytes / 1024
            
            # Calculate for different quality levels
            return {
                "duration_seconds": session_duration_seconds,
                "bytes_per_second": bytes_per_second,
                "total_bytes": total_bytes,
                "total_kb": round(kilobytes, 2),
                "total_mb": round(megabytes, 2),
                "settings": {
                    "sample_rate": self.sample_rate,
                    "channels": self.channels,
                    "bit_depth": self.bit_depth
                }
            }
            
        except Exception as e:
            logger.error(f"Bandwidth calculation error: {e}")
            return {"error": str(e)}
    
    async def monitor_audio_stream(self, session_id: str, audio_bytes: bytes) -> Dict[str, Any]:
        """
        Monitor audio stream untuk real-time feedback
        Return monitoring data yang bisa dikirim ke frontend
        """
        try:
            # Validate and analyze
            validation = self.validate_audio_chunk(audio_bytes)
            quality = self.analyze_audio_quality(audio_bytes)
            
            monitoring_data = {
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat(),
                "validation": validation,
                "quality": quality,
                "recommendations": []
            }
            
            # Add recommendations based on analysis
            if not validation["is_valid"]:
                monitoring_data["recommendations"].append("Check audio input configuration")
            
            if quality["quality_score"] < 0.5:
                monitoring_data["recommendations"].append("Audio quality is low, check microphone")
            
            if quality["estimated_duration"] > 0.5:
                monitoring_data["recommendations"].append("Consider smaller audio chunks for better latency")
            
            return monitoring_data
            
        except Exception as e:
            logger.error(f"Audio monitoring error for {session_id}: {e}")
            return {
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e)
            }

# Global instance
audio_processing_service = AudioProcessingService()