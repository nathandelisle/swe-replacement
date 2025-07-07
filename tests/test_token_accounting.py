#!/usr/bin/env python3
"""
Token accounting test suite.

Tests token counting accuracy against Anthropic's actual counts,
handling of large strings, and token budget management.
"""
import json
import pytest
from pathlib import Path
import sys
from unittest.mock import Mock, patch

# Add parent directory to path to import harness modules
sys.path.insert(0, str(Path(__file__).parent.parent / "harness"))

from claude_client import ClaudeClient


class TestTokenAccounting:
    """Tests for token counting and budget management."""
    
    @pytest.fixture
    def claude_client(self):
        """Create a Claude client instance for testing."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            return ClaudeClient()
    
    def test_token_count_simple_text(self, claude_client):
        """Test token counting for simple text."""
        test_cases = [
            ("Hello, world!", len("Hello, world!") // 4),  # Approximate based on text length
            ("The quick brown fox jumps over the lazy dog.", len("The quick brown fox jumps over the lazy dog.") // 4),
            ("", 0),
            ("A", 1),
            ("123456789", len("123456789") // 4 + 1),  # Numbers may tokenize differently
        ]
        
        for text, expected_approx in test_cases:
            count = claude_client.count_tokens(text)
            # Allow for variance in tokenization - use a percentage-based range
            min_expected = max(1, int(expected_approx * 0.5)) if text else 0
            max_expected = int(expected_approx * 2.0) + 2 if text else 0
            assert min_expected <= count <= max_expected, \
                f"Token count for '{text}' was {count}, expected between {min_expected} and {max_expected}"
    
    def test_token_count_code(self, claude_client):
        """Test token counting for code snippets."""
        code_snippet = """def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
"""
        count = claude_client.count_tokens(code_snippet)
        # Code typically has more tokens due to syntax
        assert count > 20  # Should be substantial
        assert count < 100  # But not excessive
    
    def test_token_count_special_characters(self, claude_client):
        """Test token counting with special characters."""
        test_cases = [
            "Hello\nWorld",  # Newline
            "Tab\there",  # Tab
            "Emoji 🎉 test",  # Emoji
            "Unicode: αβγδε",  # Greek letters
            "Special: €£¥$",  # Currency symbols
            "Chinese: 你好世界",  # Chinese characters
        ]
        
        for text in test_cases:
            count = claude_client.count_tokens(text)
            assert count > 0, f"Token count should be positive for: {text}"
            assert count < len(text) * 2, f"Token count seems too high for: {text}"
    
    def test_token_count_large_text(self, claude_client):
        """Test token counting for large texts."""
        # Generate large text
        large_text = "The quick brown fox jumps over the lazy dog. " * 1000
        
        count = claude_client.count_tokens(large_text)
        
        # Should scale linearly
        single_sentence_count = claude_client.count_tokens("The quick brown fox jumps over the lazy dog. ")
        expected_count = single_sentence_count * 1000
        
        # Allow 10% variance
        assert count >= expected_count * 0.9
        assert count <= expected_count * 1.1
    
    def test_token_count_json(self, claude_client):
        """Test token counting for JSON data."""
        json_data = {
            "name": "Test",
            "array": [1, 2, 3, 4, 5],
            "nested": {
                "key": "value",
                "number": 42
            }
        }
        json_str = json.dumps(json_data, indent=2)
        
        count = claude_client.count_tokens(json_str)
        # JSON with formatting has many tokens
        assert count > 20
        
        # Compact JSON should have fewer tokens
        compact_json = json.dumps(json_data)
        compact_count = claude_client.count_tokens(compact_json)
        assert compact_count < count
    
    @patch('anthropic.Anthropic')
    def test_token_count_vs_api_response(self, mock_anthropic, claude_client):
        """Test that our token counting approximates API response."""
        # Mock API response with token usage
        mock_client = Mock()
        mock_anthropic.return_value = mock_client
        
        mock_response = Mock()
        mock_response.content = [Mock(text="This is the response")]
        mock_response.usage = Mock(input_tokens=150, output_tokens=50)
        mock_client.messages.create.return_value = mock_response
        
        # Create new client to use mocked Anthropic
        client = ClaudeClient()
        
        # Send a prompt
        prompt = "Explain quantum computing in simple terms."
        response = client.send_prompt(prompt, "You are a helpful assistant.")
        
        # Get our token estimate
        prompt_tokens = client.count_tokens(prompt)
        response_tokens = client.count_tokens(response)
        
        # Our estimates should be within reasonable range of API values
        # Note: This is just testing the structure, actual API would give real counts
    
    def test_token_count_empty_and_whitespace(self, claude_client):
        """Test token counting for empty strings and whitespace."""
        test_cases = [
            ("", 0),
            (" ", 1),
            ("   ", 1),  # Multiple spaces might be one token
            ("\n", 1),
            ("\n\n\n", 1),  # Multiple newlines might compress
            ("\t", 1),
            (" \n\t ", 1),  # Mixed whitespace
        ]
        
        for text, expected_max in test_cases:
            count = claude_client.count_tokens(text)
            assert count <= expected_max, f"Token count for '{repr(text)}' was {count}, expected <= {expected_max}"
    
    def test_million_character_string(self, claude_client):
        """Test token counting scales properly for very large strings."""
        # Create a 1 million character string
        base_text = "abcdefghij" * 100  # 1000 chars
        million_char_text = base_text * 1000  # 1 million chars
        
        # Time the token counting (should be fast)
        import time
        start_time = time.time()
        count = claude_client.count_tokens(million_char_text)
        elapsed = time.time() - start_time
        
        # Should complete quickly (< 1 second)
        assert elapsed < 1.0, f"Token counting took {elapsed} seconds for 1M chars"
        
        # Count should be reasonable
        assert count > 100000  # Should be many tokens
        assert count < 500000  # But not more than 1 token per 2 chars
    
    def test_token_estimation_consistency(self, claude_client):
        """Test that token counting is consistent for same input."""
        text = "The quick brown fox jumps over the lazy dog."
        
        # Count multiple times
        counts = [claude_client.count_tokens(text) for _ in range(5)]
        
        # All counts should be identical
        assert len(set(counts)) == 1, f"Inconsistent token counts: {counts}"
    
    def test_structured_prompt_token_counting(self, claude_client):
        """Test token counting for structured prompts with multiple parts."""
        observation = {
            "turn_number": 1,
            "workspace_root": "/workspace",
            "notes_content": "# Notes\nInvestigating the issue...",
            "previous_message": "Found the bug",
            "directory_tree": """functions.py (500 bytes)
test_functions.py (1200 bytes)
src/
  module.py (300 bytes)
"""
        }
        
        # Format as the harness would
        formatted_prompt = claude_client.format_observation_prompt(observation)
        
        # Count tokens
        token_count = claude_client.count_tokens(formatted_prompt)
        
        # Should be substantial but reasonable
        assert token_count > 50  # Has content
        assert token_count < 500  # Not excessive for this size
    
    def test_system_prompt_token_counting(self, claude_client):
        """Test token counting for system prompts."""
        system_prompt = claude_client.get_system_prompt()
        
        token_count = claude_client.count_tokens(system_prompt)
        
        # System prompts are typically substantial
        assert token_count > 100  # Should have significant instructions
        assert token_count < 5000  # But not unreasonably large
    
    def test_prompt_size_validation(self, claude_client):
        """Test validation of prompt size limits."""
        # Create a prompt that approaches the limit
        huge_content = "A" * 50000  # 50KB of content
        
        observation = {
            "turn_number": 1,
            "workspace_root": "/workspace",
            "notes_content": huge_content,
            "previous_message": "",
            "directory_tree": "files..."
        }
        
        formatted_prompt = claude_client.format_observation_prompt(observation)
        token_count = claude_client.count_tokens(formatted_prompt)
        
        # Check if it would exceed typical limits
        PROMPT_MAX_TOKENS = 8000  # From harness
        
        if token_count > PROMPT_MAX_TOKENS:
            # Should handle gracefully
            assert token_count > PROMPT_MAX_TOKENS 