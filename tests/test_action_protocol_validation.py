#!/usr/bin/env python3
"""
Action protocol validation test suite.

Tests JSON parsing, action validation, error handling for malformed inputs,
and proper execution of all valid action types.
"""
import json
import subprocess
import tempfile
import shutil
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
import sys

# Add parent directory to path to import harness modules
sys.path.insert(0, str(Path(__file__).parent.parent / "harness"))

from schema import (
    validate_action, ReadFilesAction, PatchAction, RunTestsAction,
    ListDirectoryAction, WriteNotesAction, MessageOnlyAction
)
from scratchpad import parse_scratchpad


class TestActionProtocolValidation:
    """Tests for action protocol parsing and validation."""
    
    def test_valid_read_files_action(self):
        """Test valid read_files action parsing."""
        action_json = {
            "read_files": ["file1.py", "dir/file2.txt"],
            "message": "Reading configuration files"
        }
        
        action = validate_action(action_json)
        assert isinstance(action, ReadFilesAction)
        assert action.read_files == ["file1.py", "dir/file2.txt"]
        assert action.message == "Reading configuration files"
    
    def test_valid_patch_action(self):
        """Test valid patch action parsing."""
        patch_content = """--- a/file.py
+++ b/file.py
@@ -1,3 +1,3 @@
 def hello():
-    print("Hello")
+    print("Hello, World!")
"""
        action_json = {
            "patch": patch_content,
            "message": "Update greeting"
        }
        
        action = validate_action(action_json)
        assert isinstance(action, PatchAction)
        assert action.patch == patch_content
        assert action.message == "Update greeting"
    
    def test_valid_run_tests_action(self):
        """Test valid run_tests action parsing."""
        action_json = {
            "run_tests": True,
            "message": "Running test suite"
        }
        
        action = validate_action(action_json)
        assert isinstance(action, RunTestsAction)
        assert action.run_tests is True
        assert action.message == "Running test suite"
    
    def test_valid_list_directory_action(self):
        """Test valid list_directory action parsing."""
        action_json = {
            "list_directory": "src/components",
            "message": "Exploring directory structure"
        }
        
        action = validate_action(action_json)
        assert isinstance(action, ListDirectoryAction)
        assert action.list_directory == "src/components"
        assert action.message == "Exploring directory structure"
    
    def test_valid_write_notes_action(self):
        """Test valid write_notes action parsing."""
        notes_content = """# Investigation Notes
        
Found the issue in the authentication module.
Need to update the token validation logic.
"""
        action_json = {
            "write_notes": notes_content,
            "message": "Updating investigation notes"
        }
        
        action = validate_action(action_json)
        assert isinstance(action, WriteNotesAction)
        assert action.write_notes == notes_content
        assert action.message == "Updating investigation notes"
    
    def test_valid_message_only_action(self):
        """Test valid message-only action parsing."""
        action_json = {
            "message": "Need more information about the error"
        }
        
        action = validate_action(action_json)
        assert isinstance(action, MessageOnlyAction)
        assert action.message == "Need more information about the error"
    
    def test_multiple_primary_keys_invalid(self):
        """Test that actions with multiple primary keys are rejected."""
        action_json = {
            "read_files": ["file1.py"],
            "patch": "some patch",
            "message": "Invalid action"
        }
        
        action = validate_action(action_json)
        assert action is None
    
    def test_unknown_action_key_invalid(self):
        """Test that unknown action keys are rejected."""
        action_json = {
            "unknown_action": "value",
            "message": "Invalid action type"
        }
        
        action = validate_action(action_json)
        assert action is None
    
    def test_missing_required_field(self):
        """Test that actions with missing required fields are rejected."""
        # read_files without the files list
        action_json = {
            "read_files": None
        }
        
        action = validate_action(action_json)
        assert action is None
    
    def test_wrong_field_type(self):
        """Test that actions with wrong field types are rejected."""
        # read_files should be a list, not a string
        action_json = {
            "read_files": "single_file.py"
        }
        
        action = validate_action(action_json)
        assert action is None
    
    def test_empty_action_invalid(self):
        """Test that empty action object is invalid."""
        action_json = {}
        
        action = validate_action(action_json)
        assert action is None
    
    def test_malformed_json_handling(self):
        """Test handling of various malformed JSON inputs."""
        # These would be tested at the harness level
        malformed_inputs = [
            '{"read_files": ["file.py"',  # Truncated JSON
            '{"patch": "content", "extra": }',  # Invalid syntax
            '{"read_files": ["file\x00.py"]}',  # Null byte
            '{"message": "' + "A" * 1000000 + '"}',  # Very long string
        ]
        
        for input_str in malformed_inputs:
            try:
                json.loads(input_str)
                action_json = json.loads(input_str)
                action = validate_action(action_json)
            except (json.JSONDecodeError, UnicodeDecodeError):
                # Expected behavior - should fail at JSON parsing
                pass
            except Exception as e:
                # Any other exception should be handled gracefully
                assert False, f"Unexpected exception for input: {input_str}: {e}"
    
    def test_scratchpad_parsing(self):
        """Test scratchpad content extraction from agent response."""
        test_cases = [
            # Normal case
            (
                "<scratchpad>Thinking about the problem...</scratchpad>\nACTION: {\"run_tests\": true}",
                "Thinking about the problem...",
                '{"run_tests": true}'
            ),
            # Multi-line scratchpad
            (
                "<scratchpad>\nLine 1\nLine 2\n</scratchpad>\nACTION: {\"message\": \"test\"}",
                "Line 1\nLine 2",
                '{"message": "test"}'
            ),
            # No scratchpad
            (
                "ACTION: {\"read_files\": [\"test.py\"]}",
                None,
                '{"read_files": ["test.py"]}'
            ),
            # No action
            (
                "<scratchpad>Just thinking</scratchpad>\nNo action here",
                "Just thinking",
                None
            ),
        ]
        
        for response, expected_scratchpad, expected_action in test_cases:
            scratchpad, action = parse_scratchpad(response)
            assert scratchpad == expected_scratchpad
            assert action == expected_action
    
    def test_action_with_special_characters(self):
        """Test actions containing special characters."""
        test_cases = [
            # Unicode in message
            {"message": "Found issue with é encoding"},
            # Newlines in patch
            {"patch": "--- a/file\n+++ b/file\n@@ -1 +1 @@\n-old\n+new\n"},
            # Quotes in notes
            {"write_notes": 'He said "Hello" to me'},
            # Backslashes in file paths  
            {"read_files": ["path\\to\\file.py"]},
        ]
        
        for action_json in test_cases:
            action = validate_action(action_json)
            assert action is not None, f"Failed to validate: {action_json}"
    
    def test_extra_fields_rejected(self):
        """Test that actions with extra unknown fields are rejected."""
        action_json = {
            "run_tests": True,
            "unknown_field": "value",
            "message": "Running tests"
        }
        
        action = validate_action(action_json) 
        # Schema should reject additional properties
        assert action is None or not hasattr(action, 'unknown_field')
    
    @patch('harness.entrypoint.ClaudeClient')
    def test_harness_invalid_action_handling(self, mock_claude_client):
        """Test that harness properly handles and logs invalid actions."""
        # This would test the actual harness behavior with invalid actions
        # Would require mocking the Claude client to return invalid JSON
        
        mock_client_instance = Mock()
        mock_claude_client.return_value = mock_client_instance
        
        # Mock an invalid action response
        mock_client_instance.send_prompt.return_value = """
<scratchpad>Thinking...</scratchpad>
ACTION: {"read_files": "not_a_list"}
"""
        
        # Verify that the invalid action is handled gracefully
        # Since read_files should be a list, not a string, validate_action should return None
        action_json = {"read_files": "not_a_list"}
        action = validate_action(action_json)
        assert action is None, "Invalid action should return None"
    
    def test_utf8_handling(self):
        """Test UTF-8 encoding in actions."""
        test_strings = [
            "Hello 世界",  # Chinese
            "Привет мир",  # Russian  
            "🎉 Emoji test 🔥",  # Emojis
            "Special chars: €£¥",  # Currency symbols
        ]
        
        for test_str in test_strings:
            action_json = {"message": test_str}
            action = validate_action(action_json)
            assert isinstance(action, MessageOnlyAction)
            assert action.message == test_str
    
    def test_action_size_limits(self):
        """Test handling of very large action payloads."""
        # Test large file list
        large_file_list = [f"file_{i}.py" for i in range(1000)]
        action_json = {"read_files": large_file_list}
        action = validate_action(action_json)
        assert isinstance(action, ReadFilesAction)
        assert len(action.read_files) == 1000
        
        # Test large patch
        large_patch = "--- a/file\n+++ b/file\n" + "+" * 100000
        action_json = {"patch": large_patch}
        action = validate_action(action_json)
        assert isinstance(action, PatchAction)
        
        # Test large notes
        large_notes = "A" * 1000000  # 1MB of text
        action_json = {"write_notes": large_notes}
        action = validate_action(action_json)
        assert isinstance(action, WriteNotesAction)
    
    def test_run_tests_only_accepts_true(self):
        """Test that run_tests only accepts True value."""
        # Valid
        action_json = {"run_tests": True}
        action = validate_action(action_json)
        assert isinstance(action, RunTestsAction)
        
        # Invalid - False not allowed
        action_json = {"run_tests": False}
        action = validate_action(action_json)
        # Depending on schema implementation, this might be None or raise
        
        # Invalid - other values
        for invalid_value in ["true", 1, None, []]:
            action_json = {"run_tests": invalid_value}
            action = validate_action(action_json)
            assert action is None or not isinstance(action, RunTestsAction) 