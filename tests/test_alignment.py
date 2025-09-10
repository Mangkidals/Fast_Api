"""
Unit tests for alignment service
"""
import pytest
from services.alignment import AlignmentService
from models.session import TranscriptStatus

@pytest.fixture
def alignment_service():
    return AlignmentService(similarity_threshold=0.7)

class TestAlignmentService:
    
    def test_normalize_arabic_text(self, alignment_service):
        """Test Arabic text normalization"""
        # Test with diacritics
        text_with_diacritics = "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ"
        expected = "بسم الله الرحمٰن الرحيم"
        
        result = alignment_service.normalize_arabic_text(text_with_diacritics)
        # Note: actual result may vary depending on Unicode normalization
        assert len(result) <= len(text_with_diacritics)
        assert "بسم" in result.lower()
    
    def test_normalize_latin_text(self, alignment_service):
        """Test Latin text normalization"""
        text = "Bismillah-ir-Rahman, ir-Raheem!"
        expected = "bismillahirrahman irraheem"
        
        result = alignment_service.normalize_latin_text(text)
        assert result == "bismillahirrahman irraheem"
    
    def test_calculate_similarity_exact_match(self, alignment_service):
        """Test similarity calculation for exact matches"""
        text1 = "بسم"
        text2 = "بسم"
        
        similarity = alignment_service.calculate_similarity(text1, text2)
        assert similarity == 1.0
    
    def test_calculate_similarity_no_match(self, alignment_service):
        """Test similarity calculation for no matches"""
        text1 = "بسم"
        text2 = "xyz"
        
        similarity = alignment_service.calculate_similarity(text1, text2)
        assert similarity < 0.3
    
    def test_calculate_similarity_partial_match(self, alignment_service):
        """Test similarity calculation for partial matches"""
        text1 = "بسم"
        text2 = "بسملله"  # Contains the first word
        
        similarity = alignment_service.calculate_similarity(text1, text2)
        assert 0.3 < similarity < 1.0
    
    def test_compare_transcript_perfect_match(self, alignment_service):
        """Test transcript comparison with perfect match"""
        expected_words = ["بسم", "الله", "الرحمن"]
        spoken_transcript = "بسم الله الرحمن"
        
        results, summary = alignment_service.compare_transcript(
            expected_words, spoken_transcript, is_final=True
        )
        
        assert len(results) == 3
        assert summary["matched"] == 3
        assert summary["mismatched"] == 0
        assert summary["skipped"] == 0
        
        for result in results:
            assert result.status == TranscriptStatus.MATCHED
            assert result.similarity_score >= 0.7
    
    def test_compare_transcript_partial_match(self, alignment_service):
        """Test transcript comparison with partial match"""
        expected_words = ["بسم", "الله", "الرحمن", "الرحيم"]
        spoken_transcript = "بسم الله"  # Missing last two words
        
        results, summary = alignment_service.compare_transcript(
            expected_words, spoken_transcript, is_final=True
        )
        
        assert len(results) == 4
        assert summary["matched"] >= 2
        assert summary["skipped"] >= 1
    
    def test_compare_transcript_provisional(self, alignment_service):
        """Test transcript comparison in provisional mode"""
        expected_words = ["بسم", "الله", "الرحمن"]
        spoken_transcript = "بسم الله"
        
        results, summary = alignment_service.compare_transcript(
            expected_words, spoken_transcript, is_final=False
        )
        
        # In provisional mode, should use provisional status
        matched_results = [r for r in results if r.status == TranscriptStatus.PROVIS_MATCHED]
        assert len(matched_results) >= 1
    
    def test_compare_transcript_empty_input(self, alignment_service):
        """Test transcript comparison with empty input"""
        expected_words = ["بسم", "الله"]
        spoken_transcript = ""
        
        results, summary = alignment_service.compare_transcript(
            expected_words, spoken_transcript, is_final=True
        )
        
        assert len(results) == 2
        assert summary["matched"] == 0
        assert summary["skipped"] == 2
        
        for result in results:
            assert result.status == TranscriptStatus.SKIPPED
            assert result.spoken is None
    
    def test_compare_transcript_mixed_results(self, alignment_service):
        """Test transcript comparison with mixed results"""
        expected_words = ["بسم", "الله", "الرحمن", "الرحيم"]
        spoken_transcript = "بسم xyz الرحيم"  # One correct, one wrong, one missing, one correct
        
        results, summary = alignment_service.compare_transcript(
            expected_words, spoken_transcript, is_final=True
        )
        
        assert len(results) == 4
        assert summary["total"] == 4
        
        # Should have at least some matches and some mismatches/skips
        assert summary["matched"] >= 1
        assert (summary["mismatched"] + summary["skipped"]) >= 1
    
    def test_generate_position_index(self, alignment_service):
        """Test position index generation"""
        index = alignment_service.generate_position_index(2, 255, 10)
        assert index == "2.255.10"
    
    def test_parse_position_index(self, alignment_service):
        """Test position index parsing"""
        surah_id, ayah, position = alignment_service.parse_position_index("2.255.10")
        assert surah_id == 2
        assert ayah == 255
        assert position == 10
    
    def test_parse_position_index_invalid(self, alignment_service):
        """Test position index parsing with invalid input"""
        with pytest.raises(ValueError):
            alignment_service.parse_position_index("invalid.format")
        
        with pytest.raises(ValueError):
            alignment_service.parse_position_index("1.2")  # Missing third part
    
    def test_word_similarity(self, alignment_service):
        """Test word-based similarity calculation"""
        words1 = ["hello", "world"]
        words2 = ["hello", "earth"]
        
        similarity = alignment_service._calculate_word_similarity(words1, words2)
        assert 0.4 < similarity < 0.8  # Should have partial match
    
    def test_is_arabic_detection(self, alignment_service):
        """Test Arabic text detection"""
        assert alignment_service._is_arabic("بسم الله") == True
        assert alignment_service._is_arabic("Bismillah") == False
        assert alignment_service._is_arabic("بسم mixed text") == True
        assert alignment_service._is_arabic("123456") == False
        assert alignment_service._is_arabic("") == False

if __name__ == "__main__":
    pytest.main([__file__])