"""
FastAPI routes for Quran data endpoints
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional

from models.quran import QuranResponse, AyatWithSurat, JuzResponse, PageResponse, QuranAyat, Surat
from services.supabase import supabase_service

router = APIRouter()


@router.get("/juz/{juz_number}", response_model=QuranResponse)
async def get_juz(juz_number: int):
    """Get all ayat in a specific juz"""
    try:
        # Validate juz number
        if juz_number < 1 or juz_number > 30:
            raise HTTPException(status_code=400, detail="Juz number must be between 1 and 30")
        
        # Get ayat for juz
        ayat_list = await supabase_service.get_ayat_by_juz(juz_number)
        
        if not ayat_list:
            raise HTTPException(status_code=404, detail=f"No ayat found for juz {juz_number}")
        
        # Get unique surat info
        surat_ids = list(set(ayat.surah_id for ayat in ayat_list))
        surat_info = []
        
        for surah_id in surat_ids:
            surat = await supabase_service.get_surat_info(surah_id)
            if surat:
                surat_info.append({
                    "id": surat.id,
                    "nama": surat.nama,
                    "namalatin": surat.namalatin,
                    "arti": surat.arti
                })
        
        result = JuzResponse(
            juz=juz_number,
            ayat_list=ayat_list,
            total_ayat=len(ayat_list),
            surat_info=surat_info
        )
        
        return QuranResponse(
            success=True,
            data=result.dict(),
            message=f"Successfully retrieved juz {juz_number}",
            count=len(ayat_list)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/page/{page_number}", response_model=QuranResponse)
async def get_page(page_number: int):
    """Get all ayat in a specific page of mushaf"""
    try:
        # Validate page number
        if page_number < 1 or page_number > 604:  # Standard mushaf has 604 pages
            raise HTTPException(status_code=400, detail="Page number must be between 1 and 604")
        
        # Get ayat for page
        ayat_list = await supabase_service.get_ayat_by_page(page_number)
        
        if not ayat_list:
            raise HTTPException(status_code=404, detail=f"No ayat found for page {page_number}")
        
        # Get unique surat info
        surat_ids = list(set(ayat.surah_id for ayat in ayat_list))
        surat_info = []
        
        for surah_id in surat_ids:
            surat = await supabase_service.get_surat_info(surah_id)
            if surat:
                surat_info.append({
                    "id": surat.id,
                    "nama": surat.nama,
                    "namalatin": surat.namalatin,
                    "arti": surat.arti
                })
        
        result = PageResponse(
            page=page_number,
            ayat_list=ayat_list,
            total_ayat=len(ayat_list),
            surat_info=surat_info
        )
        
        return QuranResponse(
            success=True,
            data=result.dict(),
            message=f"Successfully retrieved page {page_number}",
            count=len(ayat_list)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    
@router.get("/{surah_id}/{ayah}", response_model=QuranResponse)
async def get_ayat(surah_id: int, ayah: int):
    """Get specific ayah from Quran"""
    try:
        # Validate parameters
        if surah_id < 1 or surah_id > 114:
            raise HTTPException(status_code=400, detail="Surah ID must be between 1 and 114")
            
        if ayah < 1:
            raise HTTPException(status_code=400, detail="Ayah number must be greater than 0")
        
        # Get ayah data
        ayat_data = await supabase_service.get_ayat(surah_id, ayah)
        if not ayat_data:
            raise HTTPException(
                status_code=404, 
                detail=f"Ayah {surah_id}:{ayah} not found"
            )
        
        # Get surat info
        surat_info = await supabase_service.get_surat_info(surah_id)
        
        result = AyatWithSurat(
            ayat=ayat_data,
            surat=surat_info
        )
        
        return QuranResponse(
            success=True,
            data=result.dict(),
            message=f"Successfully retrieved ayah {surah_id}:{ayah}",
            count=1
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/surat/{surah_id}", response_model=QuranResponse)
async def get_surat_info_endpoint(surah_id: int):
    """Get information about a specific surat"""
    try:
        if surah_id < 1 or surah_id > 114:
            raise HTTPException(status_code=400, detail="Surah ID must be between 1 and 114")
        
        surat_info = await supabase_service.get_surat_info(surah_id)
        if not surat_info:
            raise HTTPException(status_code=404, detail=f"Surat {surah_id} not found")
        
        return QuranResponse(
            success=True,
            data=surat_info.dict(),
            message=f"Successfully retrieved surat info for {surah_id}",
            count=1
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/search")
async def search_ayat(
    query: str = Query(..., min_length=2, description="Search query"),
    language: str = Query("arabic", regex="^(arabic|transliteration|translation)$"),
    surah_id: Optional[int] = Query(None, ge=1, le=114),
    limit: int = Query(20, ge=1, le=100)
):
    """Search for ayat by text content"""
    try:
        # This is a basic implementation - you might want to use full-text search
        # capabilities from your database for better performance
        
        search_params = {
            "order": "surah_id.asc,ayah.asc",
            "limit": limit
        }
        
        # Add surah filter if specified
        if surah_id:
            search_params["surah_id"] = f"eq.{surah_id}"
        
        # Search based on language
        if language == "arabic":
            search_params["arabic"] = f"ilike.%{query}%"
        elif language == "transliteration":
            search_params["transliteration"] = f"ilike.%{query}%"
        else:
            # For translation, you might need to join with other tables
            # This is a simplified implementation
            search_params["transliteration"] = f"ilike.%{query}%"
        
        # Make request to Supabase
        result = await supabase_service._make_request("GET", "quran_ayat", params=search_params)
        
        ayat_list = [QuranAyat(**item) for item in result] if result else []
        
        return QuranResponse(
            success=True,
            data=ayat_list,
            message=f"Found {len(ayat_list)} ayat matching '{query}'",
            count=len(ayat_list)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")