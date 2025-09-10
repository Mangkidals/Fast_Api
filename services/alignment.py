"""
Alignment service for transcript comparison using fuzzy matching
"""
from typing import List, Dict, Any, Tuple, Optional
import re
from difflib import SequenceMatcher
from Levenshtein import distance as levenshtein_distance
import unicodedata
import logging

from models.session import TranscriptResult, TranscriptStatus

logger = logging.getLogger(__name__)

class AlignmentService:
    def __init__(self, similarity_threshold: float = 0.7):
        self.similarity_threshold = similarity_threshold
        
    def normalize_arabic_text(self, text: str) -> str:
        """Normalize Arabic text for comparison"""
        if not text:
            return ""
            
        # Remove diacritics (tashkeel)
        normalized = ''.join(c for c in unicodedata.normalize('NFKD', text)
                           if not unicodedata.combining(c))
        
        # Remove extra spaces and normalize
        normalized = re.sub(r'\s+', ' ', normalized.strip())
        
        # Convert to lowercase for better matching
        return normalized.lower()
    
    def normalize_latin_text(self, text: str) -> str:
        """Normalize Latin/transliteration text for comparison"""
        if not text:
            return ""
            
        # Convert to lowercase and remove extra spaces
        normalized = re.sub(r'\s+', ' ', text.strip().lower())
        
        # Remove common punctuation
        normalized = re.sub(r'[.,;:!?()"\'\-]', '', normalized)
        
        return normalized
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts using multiple methods"""
        if not text1 or not text2:
            return 0.0
        
        # Normalize texts
        norm_text1 = self.normalize_arabic_text(text1)
        norm_text2 = self.normalize_arabic_text(text2)
        
        # If one text is Latin, try both normalizations
        if not self._is_arabic(text1) or not self._is_arabic(text2):
            norm_text1 = self.normalize_latin_text(text1)
            norm_text2 = self.normalize_latin_text(text2)
        
        # Method 1: Sequence Matcher (built-in difflib)
        seq_similarity = SequenceMatcher(None, norm_text1, norm_text2).ratio()
        
        # Method 2: Levenshtein distance
        max_len = max(len(norm_text1), len(norm_text2))
        if max_len == 0:
            lev_similarity = 1.0
        else:
            lev_distance = levenshtein_distance(norm_text1, norm_text2)
            lev_similarity = 1.0 - (lev_distance / max_len)
        
        # Method 3: Word-based similarity for longer texts
        words1 = norm_text1.split()
        words2 = norm_text2.split()
        
        if len(words1) > 1 or len(words2) > 1:
            word_similarity = self._calculate_word_similarity(words1, words2)
            # Weighted average
            final_similarity = (seq_similarity * 0.4 + lev_similarity * 0.4 + word_similarity * 0.2)
        else:
            # For single words, use sequence matcher and levenshtein
            final_similarity = (seq_similarity * 0.6 + lev_similarity * 0.4)
        
        return final_similarity
    
    def _is_arabic(self, text: str) -> bool:
        """Check if text contains Arabic characters"""
        arabic_pattern = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]')
        return bool(arabic_pattern.search(text))
    
    def _calculate_word_similarity(self, words1: List[str], words2: List[str]) -> float:
        """Calculate similarity between two lists of words"""
        if not words1 and not words2:
            return 1.0
        if not words1 or not words2:
            return 0.0
        
        # Find matching words
        matches = 0
        total_words = max(len(words1), len(words2))
        
        used_indices = set()
        for word1 in words1:
            best_match_idx = -1
            best_similarity = 0.0
            
            for i, word2 in enumerate(words2):
                if i in used_indices:
                    continue
                    
                similarity = SequenceMatcher(None, word1, word2).ratio()
                if similarity > best_similarity and similarity >= self.similarity_threshold:
                    best_similarity = similarity
                    best_match_idx = i
            
            if best_match_idx >= 0:
                matches += best_similarity
                used_indices.add(best_match_idx)
        
        return matches / total_words if total_words > 0 else 0.0
    
    def compare_transcript(
        self, 
        expected_words: List[str], 
        spoken_transcript: str,
        is_final: bool = True
    ) -> Tuple[List[TranscriptResult], Dict[str, int]]:
        """
        Compare spoken transcript with expected words
        Returns results and summary statistics
        """
        if not expected_words:
            return [], {"matched": 0, "mismatched": 0, "skipped": 0, "total": 0}
        
        # Normalize and split spoken transcript into words
        normalized_transcript = self.normalize_arabic_text(spoken_transcript)
        if not self._is_arabic(spoken_transcript):
            normalized_transcript = self.normalize_latin_text(spoken_transcript)
        
        spoken_words = normalized_transcript.split() if normalized_transcript else []
        
        results = []
        summary = {"matched": 0, "mismatched": 0, "skipped": 0, "total": len(expected_words)}
        
        # Track which spoken words have been used
        used_spoken_indices = set()
        
        for position, expected_word in enumerate(expected_words):
            result = TranscriptResult(
                position=position,
                expected=expected_word,
                spoken=None,
                status=TranscriptStatus.SKIPPED
            )
            
            if not spoken_words:
                # No spoken words available
                if is_final:
                    result.status = TranscriptStatus.SKIPPED
                    summary["skipped"] += 1
                else:
                    result.status = TranscriptStatus.SKIPPED  # Keep as skipped for provisional
                results.append(result)
                continue
            
            # Find best matching spoken word
            best_match_idx = -1
            best_similarity = 0.0
            
            # Look for matches starting from current position in spoken words
            search_start = min(position, len(spoken_words) - 1)
            search_range = list(range(search_start, len(spoken_words))) + \
                          list(range(0, search_start))
            
            for spoken_idx in search_range:
                if spoken_idx in used_spoken_indices:
                    continue
                    
                similarity = self.calculate_similarity(expected_word, spoken_words[spoken_idx])
                
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match_idx = spoken_idx
            
            # Determine status based on similarity
            if best_match_idx >= 0 and best_similarity >= self.similarity_threshold:
                result.spoken = spoken_words[best_match_idx]
                result.similarity_score = best_similarity
                
                if is_final:
                    result.status = TranscriptStatus.MATCHED
                    summary["matched"] += 1
                else:
                    result.status = TranscriptStatus.PROVIS_MATCHED
                
                used_spoken_indices.add(best_match_idx)
                
            elif best_match_idx >= 0 and best_similarity > 0.3:  # Partial match
                result.spoken = spoken_words[best_match_idx]
                result.similarity_score = best_similarity
                
                if is_final:
                    result.status = TranscriptStatus.MISMATCHED
                    summary["mismatched"] += 1
                else:
                    result.status = TranscriptStatus.PROVIS_MISMATCHED
                
                used_spoken_indices.add(best_match_idx)
                
            else:
                # No good match found
                if is_final:
                    result.status = TranscriptStatus.SKIPPED
                    summary["skipped"] += 1
                else:
                    result.status = TranscriptStatus.SKIPPED
            
            results.append(result)
        
        return results, summary
    
    def generate_position_index(self, surah_id: int, ayah: int, word_position: int) -> str:
        """Generate position index in format: suratke.ayake.arrayke"""
        return f"{surah_id}.{ayah}.{word_position}"
    
    def parse_position_index(self, index: str) -> Tuple[int, int, int]:
        """Parse position index string to extract surah_id, ayah, word_position"""
        try:
            parts = index.split('.')
            if len(parts) != 3:
                raise ValueError("Invalid index format")
            return int(parts[0]), int(parts[1]), int(parts[2])
        except (ValueError, IndexError) as e:
            logger.error(f"Error parsing position index '{index}': {e}")
            raise ValueError(f"Invalid position index format: {index}")

# Global instance
alignment_service = AlignmentService()