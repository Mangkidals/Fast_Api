"""
Unit tests for live session service
"""
import pytest
import uuid
from unittest.mock import AsyncMock, patch
from datetime import datetime

from services.live_session import LiveSessionService
from models.session import (
    StartSessionRequest, UpdateSessionRequest, SessionMode, 
    SessionStatus, LiveSession
)
from models.quran import QuranAyat

@pytest.fixture
def live_session_service():
    return LiveSessionService()

@pytest.fixture
def sample_ayat():
    return QuranAyat(
        rowid=1,
        surah_id=1,
        ayah=1,
        arabic="بِسۡمِ ٱللَّهِ ٱلرَّحۡمَـٰنِ ٱلرَّحِيمِ",
        transliteration="Bismillahir Rahmanir Raheem",
        page=1,
        juz=1,
        quarter_hizb=1,
        manzil=1,
        no_tashkeel="بسم الله الرحمن الرحيم",
        words_array=["بسم", "الله", "الرحمن", "الرحيم"],
        words_array_nt=["بسم", "الله", "الرحمن", "الرحيم"],
        has_asbabun=False
    )

@pytest.fixture
def start_session_request():
    return StartSessionRequest(
        user_id="test-user-123",
        surah_id=1,
        ayah=1,
        mode=SessionMode.SURAH,
        data={"test": "data"}
    )

class TestLiveSessionService:
    
    @pytest.mark.asyncio
    @patch('services.live_session.supabase_service')
    @patch('services.live_session.transcript_logger')
    async def test_start_session_success(self, mock_logger, mock_supabase, live_session_service, start_session_request, sample_ayat):
        """Test successful session start"""
        # Mock dependencies
        mock_supabase.get_ayat.return_value = sample_ayat
        mock_supabase.create_live_session.return_value = AsyncMock()
        mock_logger.log_session_event.return_value = AsyncMock()
        
        # Start session
        response = await live_session_service.start_session(start_session_request)
        
        # Assertions
        assert response.surah_id == 1
        assert response.ayah == 1
        assert response.status == SessionStatus.ACTIVE
        assert response.position == 0
        assert len(response.sessionId) > 0
        
        # Check that session was cached
        assert response.sessionId in live_session_service.active_sessions
        
        # Verify mocks were called
        mock_supabase.get_ayat.assert_called_once_with(1, 1)
        mock_supabase.create_live_session.assert_called_once()
        mock_logger.log_session_event.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('services.live_session.supabase_service')
    async def test_start_session_ayat_not_found(self, mock_supabase, live_session_service, start_session_request):
        """Test session start when ayat is not found"""
        # Mock ayat not found
        mock_supabase.get_ayat.return_value = None
        
        # Should raise ValueError
        with pytest.raises(ValueError, match="Ayah 1:1 not found"):
            await live_session_service.start_session(start_session_request)
    
    @pytest.mark.asyncio
    @patch('services.live_session.supabase_service')
    @patch('services.live_session.alignment_service')
    @patch('services.live_session.transcript_logger')
    async def test_update_session_provisional(self, mock_logger, mock_alignment, mock_supabase, live_session_service, sample_ayat):
        """Test provisional session update"""
        # Setup session in cache
        session_id = str(uuid.uuid4())
        session = LiveSession(
            id=session_id,
            user_id="test-user",
            surah_id=1,
            ayah=1,
            mode=SessionMode.SURAH
        )
        
        live_session_service.active_sessions[session_id] = {
            "session": session,
            "current_ayah": sample_ayat,
            "current_words": sample_ayat.words_array,
            "position": 0,
            "provisional_results": []
        }
        
        # Mock alignment service
        mock_results = []
        mock_summary = {}
        mock_alignment.compare_transcript.return_value = (mock_results, mock_summary)
        mock_logger.log_transcript.return_value = AsyncMock()
        
        # Update session with provisional transcript
        request = UpdateSessionRequest(transcript="بسم", is_final=False)
        response = await live_session_service.update_session(session_id, request)
        
        # Assertions
        assert response.sessionId == session_id
        assert response.status == "provisional"
        assert response.results == mock_results
        
        # Should not save to database for provisional
        mock_supabase.save_transcript_log.assert_not_called()
        mock_supabase.update_live_session.assert_not_called()
    
    @pytest.mark.asyncio
    @patch('services.live_session.supabase_service')
    @patch('services.live_session.alignment_service')
    @patch('services.live_session.transcript_logger')
    async def test_update_session_final(self, mock_logger, mock_alignment, mock_supabase, live_session_service, sample_ayat):
        """Test final session update"""
        # Setup session in cache
        session_id = str(uuid.uuid4())
        session = LiveSession(
            id=session_id,
            user_id="test-user",
            surah_id=1,
            ayah=1,
            mode=SessionMode.SURAH
        )
        
        live_session_service.active_sessions[session_id] = {
            "session": session,
            "current_ayah": sample_ayat,
            "current_words": sample_ayat.words_array,
            "position": 0,
            "provisional_results": []
        }
        
        # Mock alignment service with matches
        from models.session import TranscriptResult, TranscriptStatus
        mock_results = [
            TranscriptResult(position=0, expected="بسم", spoken="بسم", status=TranscriptStatus.MATCHED),
            TranscriptResult(position=1, expected="الله", spoken="الله", status=TranscriptStatus.MATCHED)
        ]
        mock_summary = {"matched": 2, "mismatched": 0, "skipped": 0}
        mock_alignment.compare_transcript.return_value = (mock_results, mock_summary)
        
        # Mock database operations
        mock_supabase.save_transcript_log.return_value = AsyncMock()
        mock_supabase.update_live_session.return_value = AsyncMock()
        mock_logger.log_transcript.return_value = AsyncMock()
        
        # Update session with final transcript
        request = UpdateSessionRequest(transcript="بسم الله", is_final=True)
        response = await live_session_service.update_session(session_id, request)
        
        # Assertions
        assert response.sessionId == session_id
        assert response.status == "final"
        assert response.results == mock_results
        assert response.summary == mock_summary
        
        # Should save to database for final
        mock_supabase.save_transcript_log.assert_called_once()
        mock_supabase.update_live_session.assert_called_once()
        
        # Position should be updated
        assert live_session_service.active_sessions[session_id]["position"] == 2
    
    @pytest.mark.asyncio
    @patch('services.live_session.supabase_service')
    @patch('services.live_session.transcript_logger')
    async def test_end_session(self, mock_logger, mock_supabase, live_session_service):
        """Test ending a session"""
        # Setup session in cache
        session_id = str(uuid.uuid4())
        live_session_service.active_sessions[session_id] = {"test": "data"}
        
        # Mock database operation
        mock_supabase.end_live_session.return_value = True
        mock_logger.log_session_event.return_value = AsyncMock()
        
        # End session
        response = await live_session_service.end_session(session_id)
        
        # Assertions
        assert response.sessionId == session_id
        assert response.status == SessionStatus.ENDED
        
        # Should be removed from cache
        assert session_id not in live_session_service.active_sessions
        
        # Should call database and logger
        mock_supabase.end_live_session.assert_called_once_with(session_id)
        mock_logger.log_session_event.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_session_not_found(self, live_session_service):
        """Test updating non-existent session"""
        session_id = "non-existent-session"
        request = UpdateSessionRequest(transcript="test", is_final=False)
        
        with patch('services.live_session.live_session_service._get_session_data') as mock_get_session:
            mock_get_session.return_value = None
            
            with pytest.raises(ValueError, match="Session .* not found or inactive"):
                await live_session_service.update_session(session_id, request)
    
    @pytest.mark.asyncio
    @patch('services.live_session.supabase_service')
    async def test_get_session_status_cached(self, mock_supabase, live_session_service, sample_ayat):
        """Test getting session status from cache"""
        # Setup session in cache
        session_id = str(uuid.uuid4())
        session = LiveSession(
            id=session_id,
            user_id="test-user",
            surah_id=1,
            ayah=1,
            mode=SessionMode.SURAH,
            status=SessionStatus.ACTIVE
        )
        
        live_session_service.active_sessions[session_id] = {
            "session": session,
            "current_ayah": sample_ayat,
            "current_words": sample_ayat.words_array,
            "position": 2,
            "provisional_results": []
        }
        
        # Get status
        status = await live_session_service.get_session_status(session_id)
        
        # Assertions
        assert status is not None
        assert status["sessionId"] == session_id
        assert status["status"] == "active"
        assert status["surah_id"] == 1
        assert status["ayah"] == 1
        assert status["position"] == 2
        assert status["total_words"] == len(sample_ayat.words_array)
    
    @pytest.mark.asyncio
    async def test_get_session_status_not_found(self, live_session_service):
        """Test getting status of non-existent session"""
        session_id = "non-existent-session"
        
        with patch('services.live_session.live_session_service._get_session_data') as mock_get_session:
            mock_get_session.return_value = None
            
            status = await live_session_service.get_session_status(session_id)
            assert status is None
    
    @pytest.mark.asyncio
    @patch('services.live_session.supabase_service')
    @patch('services.live_session.transcript_logger')
    async def test_advance_to_next_ayah_surah_mode(self, mock_logger, mock_supabase, live_session_service, sample_ayat):
        """Test advancing to next ayah in surah mode"""
        # Setup session
        session_id = str(uuid.uuid4())
        session = LiveSession(
            id=session_id,
            user_id="test-user",
            surah_id=1,
            ayah=1,
            mode=SessionMode.SURAH
        )
        
        live_session_service.active_sessions[session_id] = {
            "session": session,
            "current_ayah": sample_ayat,
            "current_words": sample_ayat.words_array,
            "position": 0,
            "provisional_results": []
        }
        
        # Mock surat info (Al-Fatihah has 7 ayat)
        from models.quran import Surat
        surat_info = Surat(
            id=1, nama="الفاتحة", arti="The Opening", 
            namalatin="Al-Fatihah", tempatturun="Makkah", 
            jumlahayat=7, deskripsi="The Opening"
        )
        
        # Next ayah data
        next_ayat = QuranAyat(
            rowid=2, surah_id=1, ayah=2,
            arabic="ٱلْحَمْدُ لِلَّهِ رَبِّ ٱلْعَـٰلَمِينَ",
            transliteration="Alhamdu lillahi rabbil alameen",
            page=1, juz=1, quarter_hizb=1, manzil=1,
            no_tashkeel="الحمد لله رب العالمين",
            words_array=["الحمد", "لله", "رب", "العالمين"],
            words_array_nt=["الحمد", "لله", "رب", "العالمين"],
            has_asbabun=False
        )
        
        # Mock database calls
        mock_supabase.get_surat_info.return_value = surat_info
        mock_supabase.get_ayat.return_value = next_ayat
        mock_supabase.update_live_session.return_value = True
        mock_logger.log_session_event.return_value = AsyncMock()
        
        # Advance to next ayah
        result = await live_session_service._advance_to_next_ayah(session_id)
        
        # Assertions
        assert result == True
        
        # Session should be updated to next ayah
        session_data = live_session_service.active_sessions[session_id]
        assert session_data["current_ayah"] == next_ayat
        assert session_data["position"] == 0
        
        # Database should be updated
        mock_supabase.update_live_session.assert_called_once()
        mock_logger.log_session_event.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('services.live_session.supabase_service')
    async def test_advance_to_next_ayah_end_of_surah(self, mock_supabase, live_session_service, sample_ayat):
        """Test advancing when at end of surah"""
        # Setup session at last ayah of Al-Fatihah (ayah 7)
        session_id = str(uuid.uuid4())
        session = LiveSession(
            id=session_id,
            user_id="test-user",
            surah_id=1,
            ayah=7,  # Last ayah of Al-Fatihah
            mode=SessionMode.SURAH
        )
        
        live_session_service.active_sessions[session_id] = {
            "session": session,
            "current_ayah": sample_ayat,
            "current_words": sample_ayat.words_array,
            "position": 0,
            "provisional_results": []
        }
        
        # Mock surat info
        from models.quran import Surat
        surat_info = Surat(
            id=1, nama="الفاتحة", arti="The Opening", 
            namalatin="Al-Fatihah", tempatturun="Makkah", 
            jumlahayat=7, deskripsi="The Opening"
        )
        mock_supabase.get_surat_info.return_value = surat_info
        
        with patch.object(live_session_service, 'end_session') as mock_end_session:
            mock_end_session.return_value = AsyncMock()
            
            # Try to advance (should end session instead)
            result = await live_session_service._advance_to_next_ayah(session_id)
            
            # Assertions
            assert result == False
            mock_end_session.assert_called_once_with(session_id)
    
    @pytest.mark.asyncio
    @patch('services.live_session.live_session_service.end_session')
    async def test_cleanup_inactive_sessions(self, mock_end_session, live_session_service):
        """Test cleanup of inactive sessions"""
        # Setup old session in cache
        old_session_id = str(uuid.uuid4())
        old_session = LiveSession(
            id=old_session_id,
            user_id="test-user",
            surah_id=1,
            ayah=1,
            mode=SessionMode.SURAH,
            updated_at=datetime.fromtimestamp(datetime.utcnow().timestamp() - 25 * 3600)  # 25 hours ago
        )
        
        live_session_service.active_sessions[old_session_id] = {
            "session": old_session,
            "current_ayah": None,
            "current_words": [],
            "position": 0,
            "provisional_results": []
        }
        
        # Mock end_session to return success
        mock_end_session.return_value = AsyncMock()
        
        # Run cleanup (24 hour threshold)
        await live_session_service.cleanup_inactive_sessions(24)
        
        # Should have called end_session for old session
        mock_end_session.assert_called_once_with(old_session_id)

    @pytest.mark.asyncio
    @patch('services.live_session.supabase_service')
    async def test_get_session_data_from_cache(self, mock_supabase, live_session_service, sample_ayat):
        """Test getting session data from cache"""
        session_id = str(uuid.uuid4())
        session = LiveSession(
            id=session_id,
            user_id="test-user",
            surah_id=1,
            ayah=1,
            mode=SessionMode.SURAH
        )
        
        # Setup cache
        expected_data = {
            "session": session,
            "current_ayah": sample_ayat,
            "current_words": sample_ayat.words_array,
            "position": 0,
            "provisional_results": []
        }
        live_session_service.active_sessions[session_id] = expected_data
        
        # Get session data
        result = await live_session_service._get_session_data(session_id)
        
        # Should return cached data
        assert result == expected_data
        
        # Should not call database
        mock_supabase.get_live_session.assert_not_called()

    @pytest.mark.asyncio
    @patch('services.live_session.supabase_service')
    async def test_get_session_data_from_database(self, mock_supabase, live_session_service, sample_ayat):
        """Test getting session data from database when not cached"""
        session_id = str(uuid.uuid4())
        session = LiveSession(
            id=session_id,
            user_id="test-user",
            surah_id=1,
            ayah=1,
            mode=SessionMode.SURAH,
            position=2,
            status=SessionStatus.ACTIVE
        )
        
        # Mock database calls
        mock_supabase.get_live_session.return_value = session
        mock_supabase.get_ayat.return_value = sample_ayat
        
        # Get session data (not in cache)
        result = await live_session_service._get_session_data(session_id)
        
        # Assertions
        assert result is not None
        assert result["session"] == session
        assert result["current_ayah"] == sample_ayat
        assert result["position"] == session.position
        
        # Should be added to cache
        assert session_id in live_session_service.active_sessions
        
        # Should call database
        mock_supabase.get_live_session.assert_called_once_with(session_id)
        mock_supabase.get_ayat.assert_called_once_with(1, 1)

    @pytest.mark.asyncio
    @patch('services.live_session.supabase_service')
    async def test_update_session_ayah(self, mock_supabase, live_session_service):
        """Test updating session to new ayah"""
        session_id = str(uuid.uuid4())
        
        # New ayah data
        new_ayah = QuranAyat(
            rowid=2, surah_id=1, ayah=2,
            arabic="ٱلْحَمْدُ لِلَّهِ رَبِّ ٱلْعَـٰلَمِينَ",
            transliteration="Alhamdu lillahi rabbil alameen",
            page=1, juz=1, quarter_hizb=1, manzil=1,
            no_tashkeel="الحمد لله رب العالمين",
            words_array=["الحمد", "لله", "رب", "العالمين"],
            words_array_nt=["الحمد", "لله", "رب", "العالمين"],
            has_asbabun=False
        )
        
        # Setup initial cache
        live_session_service.active_sessions[session_id] = {
            "session": None,
            "current_ayah": None,
            "current_words": [],
            "position": 5,
            "provisional_results": ["old_results"]
        }
        
        # Mock database calls
        mock_supabase.get_ayat.return_value = new_ayah
        mock_supabase.update_live_session.return_value = True
        
        with patch('services.live_session.transcript_logger.log_session_event') as mock_logger:
            mock_logger.return_value = AsyncMock()
            
            # Update session to new ayah
            await live_session_service._update_session_ayah(session_id, 1, 2)
            
            # Verify database update
            mock_supabase.update_live_session.assert_called_once_with(session_id, {
                "surah_id": 1,
                "ayah": 2,
                "position": 0
            })
            
            # Verify cache update
            cache_data = live_session_service.active_sessions[session_id]
            assert cache_data["current_ayah"] == new_ayah
            assert cache_data["current_words"] == new_ayah.words_array
            assert cache_data["position"] == 0
            assert cache_data["provisional_results"] == []
            
            # Verify logging
            mock_logger.assert_called_once()

if __name__ == "__main__":
    pytest.main([__file__])