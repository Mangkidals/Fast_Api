"""
Pydantic models for Quran data structures
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

class Surat(BaseModel):
    id: int
    nama: str
    arti: str
    deskripsi: Optional[str] = None
    namalatin: str
    tempatturun: str
    jumlahayat: int

class Ayat(BaseModel):
    id: int
    nomorayat: int
    teksarab: str
    tekslatin: str
    teksindonesia: str
    surat_id: int

class QuranAyat(BaseModel):
    rowid: int
    surah_id: int
    ayah: int
    arabic: str
    transliteration: str
    page: int
    juz: int
    quarter_hizb: int
    manzil: int
    no_tashkeel: str
    words_array: List[str] = Field(default_factory=list)
    words_array_nt: Optional[List[str]] = Field(default_factory=list)  # Changed here
    has_asbabun: bool = False


class AudioAyat(BaseModel):
    id: int
    surat_id: int
    ayat_id: int
    audio: str

class AudioFull(BaseModel):
    id: int
    surat_id: int
    audio: str

class QuranResponse(BaseModel):
    success: bool = True
    data: Optional[Any] = None
    message: Optional[str] = None
    count: Optional[int] = None

class AyatWithSurat(BaseModel):
    ayat: QuranAyat
    surat: Optional[Surat] = None

class JuzResponse(BaseModel):
    juz: int
    ayat_list: List[QuranAyat]
    total_ayat: int
    surat_info: List[Dict[str, Any]]

class PageResponse(BaseModel):
    page: int
    ayat_list: List[QuranAyat]
    total_ayat: int
    surat_info: List[Dict[str, Any]]