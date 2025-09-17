"""
Supabase REST API service for database operations
"""
import httpx
import os
from typing import List, Dict, Any, Optional, Union
from fastapi import HTTPException
import json
import logging
from datetime import datetime

from models.quran import QuranAyat, Surat
from models.session import LiveSession, TranscriptLog

logger = logging.getLogger(__name__)

class SupabaseService:
    def __init__(self):
        self.base_url = os.getenv("SUPABASE_URL")
        self.api_key = os.getenv("SUPABASE_API_KEY")
        self.service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        
        if not all([self.base_url, self.api_key, self.service_role_key]):
            raise ValueError("Missing Supabase configuration. Please set SUPABASE_URL, SUPABASE_API_KEY, and SUPABASE_SERVICE_ROLE_KEY")
        
        self.rest_url = f"{self.base_url}/rest/v1"
        
        # Headers for different types of operations
        self.headers_anon = {
            "apikey": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        self.headers_service = {
            "apikey": self.api_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json"
        }

    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict] = None, 
        params: Optional[Dict] = None,
        use_service_role: bool = False,
        headers_override: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to Supabase REST API"""
        url = f"{self.rest_url}/{endpoint}"
        headers = headers_override or (self.headers_service if use_service_role else self.headers_anon)
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=data,
                    params=params,
                    timeout=30.0
                )
                
                if response.status_code >= 400:
                    logger.error(f"Supabase API error: {response.status_code} - {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Supabase API error: {response.text}"
                    )
                
                return response.json() if response.content else {}
                
        except httpx.RequestError as e:
            logger.error(f"Request error to Supabase: {e}")
            raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

    # Quran Data Methods
    async def get_ayat(self, surah_id: int, ayah: int) -> Optional[QuranAyat]:
        """Get specific ayah from quran_ayat table"""
        params = {"surah_id": f"eq.{surah_id}", "ayah": f"eq.{ayah}"}
        result = await self._make_request("GET", "m10_quran_ayah", params=params)
        
        if result and len(result) > 0:
            return QuranAyat(**result[0])
        return None

    async def get_ayat_by_juz(self, juz: int) -> List[QuranAyat]:
        """Get all ayat in a specific juz"""
        params = {"juz": f"eq.{juz}", "order": "surah_id.asc,ayah.asc"}
        result = await self._make_request("GET", "m10_quran_ayah", params=params)
        
        return [QuranAyat(**item) for item in result] if result else []

    async def get_ayat_by_page(self, page: int) -> List[QuranAyat]:
        """Get all ayat in a specific page"""
        params = {"page": f"eq.{page}", "order": "surah_id.asc,ayah.asc"}
        result = await self._make_request("GET", "m10_quran_ayah", params=params)
        
        return [QuranAyat(**item) for item in result] if result else []

    async def get_surat_info(self, surah_id: int) -> Optional[Surat]:
        """Get surat information"""
        params = {"id": f"eq.{surah_id}"}
        result = await self._make_request("GET", "surat", params=params)
        
        if result and len(result) > 0:
            return Surat(**result[0])
        return None

    # Live Session Methods
    async def create_live_session(self, session: LiveSession) -> LiveSession:
        """Create new live session"""
        session_data = {
            "user_id": session.user_id,
            "surah_id": session.surah_id,
            "ayah": session.ayah,
            "position": session.position,
            "mode": session.mode.value,
            "data": session.data,
            "status": session.status.value,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        await self._make_request(
            "POST", 
            "live_sessions", 
            data=session_data,
            use_service_role=True
        )
        
        return session

    async def get_live_session(self, session_id: str) -> Optional[LiveSession]:
        """Get live session by ID"""
        params = {"session_id": f"eq.{session_id}"}
        result = await self._make_request("GET", "live_sessions", params=params, use_service_role=True)
        
        if result and len(result) > 0:
            data = result[0]
            return LiveSession(
                id=data["id"],
                user_id=data["user_id"],
                surah_id=data["surah_id"],
                ayah=data["ayah"],
                position=data["position"],
                mode=data["mode"],
                data=data["data"] or {},
                status=data["status"],
                created_at=data.get("created_at"),
                updated_at=data.get("updated_at")
            )
        return None

    async def update_live_session(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """Update live session"""
        updates["updated_at"] = datetime.utcnow().isoformat()
        
        await self._make_request(
            "PATCH",
            f"live_sessions?session_id=eq.{session_id}",
            data=updates,
            use_service_role=True
        )
        return True

    async def end_live_session(self, session_id: str) -> bool:
        """End live session"""
        return await self.update_live_session(session_id, {"status": "ended"})

    # Transcript Log Methods
    async def save_transcript_log(self, log: TranscriptLog, overwrite: bool = True) -> TranscriptLog:
        """Save transcript log with optional overwrite"""
        log_data = {
            "session_id": log.session_id,
            "transcript": log.transcript,
            "is_final": log.is_final,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        if overwrite:
            # First, delete existing logs with same session_id if is_final=True
            if log.is_final:
                await self._make_request(
                    "DELETE",
                    f"transcript_logs?session_id=eq.{log.session_id}",
                    use_service_role=True
                )
            
            # Insert new log
            headers = self.headers_service.copy()
            if overwrite:
                headers["Prefer"] = "resolution=merge-duplicates"
            
            result = await self._make_request(
                "POST",
                "transcript_logs",
                data=log_data,
                use_service_role=True,
                headers_override=headers
            )
        else:
            result = await self._make_request(
                "POST",
                "transcript_logs",
                data=log_data,
                use_service_role=True
            )
        
        # Return the created log (Supabase returns the inserted data)
        if isinstance(result, list) and len(result) > 0:
            created_log = result[0]
            return TranscriptLog(
                id=created_log.get("id"),
                session_id=created_log["session_id"],
                transcript=created_log["transcript"],
                is_final=created_log["is_final"],
                created_at=created_log.get("created_at"),
                updated_at=created_log.get("updated_at")
            )
        
        return log

    async def get_transcript_logs(self, session_id: str) -> List[TranscriptLog]:
        """Get all transcript logs for a session"""
        params = {
            "session_id": f"eq.{session_id}",
            "order": "created_at.asc"
        }
        result = await self._make_request("GET", "transcript_logs", params=params, use_service_role=True)
        
        logs = []
        if result:
            for item in result:
                logs.append(TranscriptLog(
                    id=item.get("id"),
                    session_id=item["session_id"],
                    transcript=item["transcript"],
                    is_final=item["is_final"],
                    created_at=item.get("created_at"),
                    updated_at=item.get("updated_at")
                ))
        
        return logs

# Global instance
supabase_service = SupabaseService()