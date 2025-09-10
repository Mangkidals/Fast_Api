"""
Pydantic models for live session and transcript data
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from enum import Enum
import uuid

class SessionStatus(str, Enum):
    ACTIVE = "active"
    ENDED = "ended"

class SessionMode(str, Enum):
    SURAH = "surah"
    JUZ = "juz"
    PAGE = "page"

class TranscriptStatus(str, Enum):
    MATCHED = "matched"
    MISMATCHED = "mismatched"
    SKIPPED = "skipped"
    PROVIS_MATCHED = "provis_matched"
    PROVIS_MISMATCHED = "provis_mismatched"

class LiveSession(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    surah_id: int
    ayah: int
    position: int = 0
    mode: SessionMode
    data: Dict[str, Any] = Field(default_factory=dict)
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class TranscriptLog(BaseModel):
    id: Optional[int] = None
    session_id: str
    transcript: str
    is_final: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class TranscriptResult(BaseModel):
    position: int
    expected: str
    spoken: Optional[str]
    status: TranscriptStatus
    similarity_score: Optional[float] = None

class StartSessionRequest(BaseModel):
    user_id: str
    surah_id: int
    ayah: int
    mode: SessionMode = SessionMode.SURAH
    data: Optional[Dict[str, Any]] = Field(default_factory=dict)

class StartSessionResponse(BaseModel):
    sessionId: str
    surah_id: int
    ayah: int
    status: SessionStatus
    position: int
    message: str = "Live session started successfully"
    
class MoveAyahRequest(BaseModel):
    ayah: int
    position: int = 0

class MoveAyahResponse(BaseModel):
    sessionId: str
    surah_id: int
    ayah: int
    status: SessionStatus
    position: int
    message: str = "Moved to new ayah successfully"

class UpdateSessionRequest(BaseModel):
    transcript: str
    is_final: bool = False

class UpdateSessionResponse(BaseModel):
    sessionId: str
    status: str  # "provisional" or "final"
    results: List[TranscriptResult]
    summary: Optional[Dict[str, int]] = None

class EndSessionResponse(BaseModel):
    sessionId: str
    status: SessionStatus
    message: str = "Live session ended successfully"

class TranscriptComparisonRequest(BaseModel):
    transcript: str
    surah_id: Optional[int] = None
    ayah: Optional[int] = None

class TranscriptComparisonResponse(BaseModel):
    success: bool = True
    results: List[TranscriptResult]
    summary: Dict[str, int]
    message: Optional[str] = None

class SessionSummary(BaseModel):
    matched: int = 0
    mismatched: int = 0
    skipped: int = 0
    total: int = 0
    accuracy: float = 0.0