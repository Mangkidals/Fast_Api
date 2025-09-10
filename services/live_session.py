"""
Live session management service
"""
import uuid
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import logging

from models.session import (
    LiveSession, TranscriptLog, SessionStatus, SessionMode,
    TranscriptResult, StartSessionRequest, UpdateSessionRequest,
    StartSessionResponse, UpdateSessionResponse, EndSessionResponse,
    SessionSummary
)
from models.quran import QuranAyat
from services.supabase import supabase_service
from services.alignment import alignment_service
from utils.logging import transcript_logger

logger = logging.getLogger(__name__)

class LiveSessionService:
    def __init__(self):
        self.active_sessions: Dict[str, Dict[str, Any]] = {}  # In-memory cache for active sessions
    
    async def start_session(self, request: StartSessionRequest) -> StartSessionResponse:
        """Start a new live session"""
        try:
            # Generate session ID
            session_id = str(uuid.uuid4())
            
            # Get initial ayah data to validate
            ayah_data = await supabase_service.get_ayat(request.surah_id, request.ayah)
            if not ayah_data:
                raise ValueError(f"Ayah {request.surah_id}:{request.ayah} not found")
            
            # Create session object
            session = LiveSession(
                id=session_id,
                user_id=request.user_id,
                surah_id=request.surah_id,
                ayah=request.ayah,
                position=0,
                mode=request.mode,
                data=request.data or {},
                status=SessionStatus.ACTIVE
            )
            
            # Save to database
            created_session = await supabase_service.create_live_session(session)
            
            # Cache session data including ayah words
            self.active_sessions[session_id] = {
                "session": created_session,
                "current_ayah": ayah_data,
                "current_words": ayah_data.words_array or ayah_data.arabic.split(),
                "position": 0,
                "provisional_results": []
            }
            
            # Log session start
            await transcript_logger.log_session_event(
                session_id, "session_started", 
                f"Started session for {request.surah_id}:{request.ayah}"
            )
            
            return StartSessionResponse(
                sessionId=session_id,
                surah_id=request.surah_id,
                ayah=request.ayah,
                status=SessionStatus.ACTIVE,
                position=0
            )
            
        except Exception as e:
            logger.error(f"Error starting session: {e}")
            raise

    async def update_session(self, session_id: str, request: UpdateSessionRequest) -> UpdateSessionResponse:
        """Update session with new transcript"""
        try:
            # Get session from cache or database
            session_data = await self._get_session_data(session_id)
            if not session_data:
                raise ValueError(f"Session {session_id} not found or inactive")
            
            session = session_data["session"]
            current_words = session_data["current_words"]
            current_position = session_data["position"]
            
            # Compare transcript with expected words
            results, summary = alignment_service.compare_transcript(
                expected_words=current_words[current_position:current_position + 10],  # Next 10 words
                spoken_transcript=request.transcript,
                is_final=request.is_final
            )
            
            # Adjust position indices
            for result in results:
                result.position = current_position + result.position
            
            if request.is_final:
                # Save final transcript to database
                transcript_log = TranscriptLog(
                    session_id=session_id,
                    transcript=request.transcript,
                    is_final=True
                )
                await supabase_service.save_transcript_log(transcript_log, overwrite=True)
                
                # Update position based on matched words
                matched_words = sum(1 for r in results if r.status.value in ["matched"])
                new_position = current_position + matched_words
                
                # Update session position
                await supabase_service.update_live_session(session_id, {"position": new_position})
                
                # Update cache
                self.active_sessions[session_id]["position"] = new_position
                self.active_sessions[session_id]["provisional_results"] = []
                
                # Check if ayah is complete
                if new_position >= len(current_words):
                    await self._advance_to_next_ayah(session_id)
                
                # Log final transcript
                await transcript_logger.log_transcript(
                    session_id, request.transcript, True, results, summary
                )
                
                return UpdateSessionResponse(
                    sessionId=session_id,
                    status="final",
                    results=results,
                    summary=summary
                )
            else:
                # Provisional update - store in cache only
                self.active_sessions[session_id]["provisional_results"] = results
                
                # Log provisional transcript (no database save)
                await transcript_logger.log_transcript(
                    session_id, request.transcript, False, results, {}
                )
                
                return UpdateSessionResponse(
                    sessionId=session_id,
                    status="provisional",
                    results=results
                )
                
        except Exception as e:
            logger.error(f"Error updating session {session_id}: {e}")
            raise

    async def end_session(self, session_id: str) -> EndSessionResponse:
        """End live session"""
        try:
            # Update session status in database
            await supabase_service.end_live_session(session_id)
            
            # Remove from cache
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
            
            # Log session end
            await transcript_logger.log_session_event(
                session_id, "session_ended", "Session ended by user"
            )
            
            return EndSessionResponse(
                sessionId=session_id,
                status=SessionStatus.ENDED
            )
            
        except Exception as e:
            logger.error(f"Error ending session {session_id}: {e}")
            raise

    async def get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get current session status"""
        session_data = await self._get_session_data(session_id)
        if not session_data:
            return None
        
        session = session_data["session"]
        current_ayah = session_data["current_ayah"]
        
        return {
            "sessionId": session_id,
            "status": session.status.value,
            "surah_id": session.surah_id,
            "ayah": session.ayah,
            "position": session_data["position"],
            "total_words": len(session_data["current_words"]),
            "current_ayah": {
                "arabic": current_ayah.arabic,
                "transliteration": current_ayah.transliteration,
                "words_array": current_ayah.words_array
            },
            "provisional_results": session_data.get("provisional_results", [])
        }

    async def _get_session_data(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data from cache or database"""
        # Try cache first
        if session_id in self.active_sessions:
            return self.active_sessions[session_id]
        
        # Load from database
        session = await supabase_service.get_live_session(session_id)
        if not session or session.status != SessionStatus.ACTIVE:
            return None
        
        # Load current ayah data
        current_ayah = await supabase_service.get_ayat(session.surah_id, session.ayah)
        if not current_ayah:
            return None
        
        # Restore to cache
        session_data = {
            "session": session,
            "current_ayah": current_ayah,
            "current_words": current_ayah.words_array or current_ayah.arabic.split(),
            "position": session.position,
            "provisional_results": []
        }
        
        self.active_sessions[session_id] = session_data
        return session_data

    async def _advance_to_next_ayah(self, session_id: str) -> bool:
        """Advance to next ayah based on session mode"""
        try:
            session_data = self.active_sessions.get(session_id)
            if not session_data:
                return False
            
            session = session_data["session"]
            
            if session.mode == SessionMode.SURAH:
                # Get next ayah in same surah
                next_ayah = session.ayah + 1
                surat_info = await supabase_service.get_surat_info(session.surah_id)
                
                if next_ayah <= surat_info.jumlahayat:
                    await self._update_session_ayah(session_id, session.surah_id, next_ayah)
                    return True
                else:
                    # End of surah
                    await self.end_session(session_id)
                    return False
            
            elif session.mode == SessionMode.PAGE:
                # Find next ayah on same page
                current_page = session_data["current_ayah"].page
                next_ayahs = await supabase_service.get_ayat_by_page(current_page)
                
                current_found = False
                for ayah in next_ayahs:
                    if current_found:
                        await self._update_session_ayah(session_id, ayah.surah_id, ayah.ayah)
                        return True
                    if ayah.surah_id == session.surah_id and ayah.ayah == session.ayah:
                        current_found = True
                
                # End of page
                await self.end_session(session_id)
                return False
            
            elif session.mode == SessionMode.JUZ:
                # Find next ayah in same juz
                current_juz = session_data["current_ayah"].juz
                juz_ayahs = await supabase_service.get_ayat_by_juz(current_juz)
                
                current_found = False
                for ayah in juz_ayahs:
                    if current_found:
                        await self._update_session_ayah(session_id, ayah.surah_id, ayah.ayah)
                        return True
                    if ayah.surah_id == session.surah_id and ayah.ayah == session.ayah:
                        current_found = True
                
                # End of juz
                await self.end_session(session_id)
                return False
            
            return False
            
        except Exception as e:
            logger.error(f"Error advancing to next ayah for session {session_id}: {e}")
            return False

    async def _update_session_ayah(self, session_id: str, surah_id: int, ayah: int):
        """Update session to new ayah"""
        # Get new ayah data
        new_ayah = await supabase_service.get_ayat(surah_id, ayah)
        if not new_ayah:
            raise ValueError(f"Ayah {surah_id}:{ayah} not found")
        
        # Update database
        await supabase_service.update_live_session(session_id, {
            "surah_id": surah_id,
            "ayah": ayah,
            "position": 0
        })
        
        # Update cache
        self.active_sessions[session_id].update({
            "current_ayah": new_ayah,
            "current_words": new_ayah.words_array or new_ayah.arabic.split(),
            "position": 0,
            "provisional_results": []
        })
        
        # Log ayah change
        await transcript_logger.log_session_event(
            session_id, "ayah_advanced", 
            f"Advanced to {surah_id}:{ayah}"
        )

    async def cleanup_inactive_sessions(self, hours: int = 24):
        """Cleanup sessions that have been inactive for specified hours"""
        try:
            # This would be called by a background task
            cutoff_time = datetime.utcnow().timestamp() - (hours * 3600)
            
            # Remove from cache (simple cleanup)
            inactive_sessions = []
            for session_id, session_data in self.active_sessions.items():
                session = session_data["session"]
                if session.updated_at and session.updated_at.timestamp() < cutoff_time:
                    inactive_sessions.append(session_id)
            
            for session_id in inactive_sessions:
                await self.end_session(session_id)
                logger.info(f"Cleaned up inactive session: {session_id}")
                
        except Exception as e:
            logger.error(f"Error cleaning up inactive sessions: {e}")

# Global instance
live_session_service = LiveSessionService()