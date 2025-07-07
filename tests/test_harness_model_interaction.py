"""
Comprehensive tests for harness model interaction and parsing.
Tests the actual model responses and parser behavior to ensure correctness.
"""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys
import os

# Add harness to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../harness'))

from schema import (
    validate_action, ReadFilesAction, PatchAction, RunTestsAction, 
    ListDirectoryAction, WriteNotesAction, MessageOnlyAction
)
from scratchpad import parse_scratchpad, validate_response_format
from observation_builder import build_observation, count_tokens_anthropic, truncate_notes
from claude_client import ClaudeClient


class TestScratchpadParsing:
    """Test parsing of model responses to extract scratchpad and actions."""
    
    def test_parse_valid_response(self):
        """Test parsing a well-formed response."""
        response = """<scratchpad>
I need to analyze the test failures and fix them.
First, let me read the test file to understand what's expected.
</scratchpad>
ACTION: {"read_files": ["tests/test_main.py", "src/main.py"]}"""
        
        scratchpad, action_json = parse_scratchpad(response)
        
        assert scratchpad == """I need to analyze the test failures and fix them.
First, let me read the test file to understand what's expected."""
        assert action_json == '{"read_files": ["tests/test_main.py", "src/main.py"]}'
        
    def test_parse_response_with_message(self):
        """Test parsing response with message field."""
        response = """<scratchpad>
Running tests to check current status.
</scratchpad>
ACTION: {"run_tests": true, "message": "Initial test run complete"}"""
        
        scratchpad, action_json = parse_scratchpad(response)
        
        assert scratchpad == "Running tests to check current status."
        assert action_json == '{"run_tests": true, "message": "Initial test run complete"}'
        
    def test_parse_multiline_action(self):
        """Test parsing action JSON that spans multiple lines."""
        response = """<scratchpad>
Applying a patch to fix the issue.
</scratchpad>
ACTION: {
    "patch": "--- a/main.py\\n+++ b/main.py\\n@@ -1,3 +1,3 @@\\n def add(a, b):\\n-    return a + b\\n+    return a + b + 1",
    "message": "Applied fix"
}"""
        
        scratchpad, action_json = parse_scratchpad(response)
        
        assert scratchpad == "Applying a patch to fix the issue."
        assert '"patch"' in action_json
        assert '"message": "Applied fix"' in action_json
        
    def test_parse_empty_scratchpad(self):
        """Test parsing response with empty scratchpad."""
        response = """<scratchpad>
</scratchpad>
ACTION: {"list_directory": "/workspace"}"""
        
        scratchpad, action_json = parse_scratchpad(response)
        
        assert scratchpad == ""
        assert action_json == '{"list_directory": "/workspace"}'
        
    def test_parse_missing_scratchpad(self):
        """Test parsing response without scratchpad tags."""
        response = """Let me check the files.
ACTION: {"read_files": ["main.py"]}"""
        
        scratchpad, action_json = parse_scratchpad(response)
        
        assert scratchpad is None
        assert action_json == '{"read_files": ["main.py"]}'
        
    def test_parse_missing_action(self):
        """Test parsing response without ACTION line."""
        response = """<scratchpad>
Thinking about the problem...
</scratchpad>
I should read the files first."""
        
        scratchpad, action_json = parse_scratchpad(response)
        
        assert scratchpad == "Thinking about the problem..."
        assert action_json is None
        
    def test_validate_response_format(self):
        """Test response format validation."""
        valid_response = """<scratchpad>
Thoughts here
</scratchpad>
ACTION: {"run_tests": true}"""
        
        assert validate_response_format(valid_response) is True
        
        invalid_responses = [
            "No scratchpad or action",
            "<scratchpad>Only scratchpad</scratchpad>",
            "ACTION: {\"only_action\": true}",
            "<scratchpad>Unclosed scratchpad",
        ]
        
        for response in invalid_responses:
            assert validate_response_format(response) is False


class TestActionValidation:
    """Test validation of action JSON objects."""
    
    def test_validate_read_files_action(self):
        """Test validation of read_files action."""
        action = validate_action({"read_files": ["file1.py", "file2.py"]})
        assert isinstance(action, ReadFilesAction)
        assert action.read_files == ["file1.py", "file2.py"]
        assert action.message is None
        
        # With message
        action = validate_action({
            "read_files": ["test.py"],
            "message": "Reading test file"
        })
        assert isinstance(action, ReadFilesAction)
        assert action.message == "Reading test file"
        
    def test_validate_patch_action(self):
        """Test validation of patch action."""
        patch_str = "--- a/file.py\\n+++ b/file.py\\n@@ -1 +1 @@\\n-old\\n+new"
        action = validate_action({"patch": patch_str})
        assert isinstance(action, PatchAction)
        assert action.patch == patch_str
        
    def test_validate_run_tests_action(self):
        """Test validation of run_tests action."""
        action = validate_action({"run_tests": True})
        assert isinstance(action, RunTestsAction)
        assert action.run_tests is True
        
        # Should reject false value
        action = validate_action({"run_tests": False})
        assert action is None
        
    def test_validate_list_directory_action(self):
        """Test validation of list_directory action."""
        action = validate_action({"list_directory": "/workspace/src"})
        assert isinstance(action, ListDirectoryAction)
        assert action.list_directory == "/workspace/src"
        
    def test_validate_write_notes_action(self):
        """Test validation of write_notes action."""
        notes_content = "# My Notes\\n\\nThis is the new content"
        action = validate_action({"write_notes": notes_content})
        assert isinstance(action, WriteNotesAction)
        assert action.write_notes == notes_content
        
    def test_validate_message_only_action(self):
        """Test validation of message-only action."""
        action = validate_action({"message": "Passing info to next turn"})
        assert isinstance(action, MessageOnlyAction)
        assert action.message == "Passing info to next turn"
        
    def test_reject_multiple_primary_keys(self):
        """Test that actions with multiple primary keys are rejected."""
        invalid_actions = [
            {"read_files": ["a.py"], "patch": "diff"},
            {"run_tests": True, "list_directory": "/"},
            {"write_notes": "content", "read_files": ["b.py"]},
        ]
        
        for action_json in invalid_actions:
            action = validate_action(action_json)
            assert action is None
            
    def test_reject_invalid_types(self):
        """Test that actions with wrong types are rejected."""
        invalid_actions = [
            {"read_files": "not_a_list"},  # Should be list
            {"run_tests": "yes"},  # Should be boolean true
            {"list_directory": ["not", "string"]},  # Should be string
            {"patch": {"not": "string"}},  # Should be string
        ]
        
        for action_json in invalid_actions:
            action = validate_action(action_json)
            assert action is None
            
    def test_reject_empty_action(self):
        """Test that empty action objects are rejected."""
        action = validate_action({})
        assert action is None


class TestObservationBuilder:
    """Test observation building and token management."""
    
    @patch('subprocess.run')
    @patch('pathlib.Path.iterdir')
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.is_dir')
    @patch('pathlib.Path.read_text')
    def test_build_basic_observation(self, mock_read_text, mock_is_dir, 
                                   mock_exists, mock_iterdir, mock_run):
        """Test building a basic observation."""
        # Mock file system
        mock_exists.return_value = True
        mock_is_dir.return_value = False
        mock_iterdir.return_value = []
        
        # Mock git and pytest
        mock_run.return_value = Mock(
            returncode=0,
            stdout="No changes",
            stderr=""
        )
        
        # Mock agent state
        mock_read_text.side_effect = lambda: '{"last_message": "Previous message"}'
        
        obs = build_observation(turn_number=1)
        
        assert "directory_tree" in obs
        assert "git_diff" in obs
        assert "test_results" in obs
        assert "previous_message" in obs
        assert obs["previous_message"] == "Previous message"
        
    def test_count_tokens_code_vs_text(self):
        """Test that token counting differentiates between code and text."""
        # Code sample
        code = """def calculate_sum(numbers):
    total = 0
    for num in numbers:
        total += num
    return total
    
class Calculator:
    def __init__(self):
        self.result = 0"""
        
        # Natural language sample of similar length
        text = """This is a natural language paragraph that describes something in detail.
It has multiple sentences and uses normal English words and grammar.
The purpose is to test token counting for different content types."""
        
        code_tokens = count_tokens_anthropic(code)
        text_tokens = count_tokens_anthropic(text)
        
        # Code should have more tokens due to special characters and density
        assert code_tokens > text_tokens
        
    def test_truncate_notes_by_turns(self):
        """Test that notes truncation keeps most recent turns."""
        notes = """### Turn 1
Old thoughts that should be truncated.
This is very old content.

### Turn 2
Slightly newer content.
Still might be truncated.

### Turn 3
Recent thoughts.
This should be kept.

### Turn 4
Most recent thoughts.
This must be kept."""
        
        truncated = truncate_notes(notes, max_tokens=100)
        
        assert "Turn 4" in truncated
        assert "Turn 3" in truncated
        assert "Turn 1" not in truncated
        assert "truncated" in truncated  # Should have truncation notice
        
    def test_truncate_notes_no_turns(self):
        """Test truncation when notes don't have turn markers."""
        notes = "A" * 10000  # Very long content
        
        truncated = truncate_notes(notes, max_tokens=100)
        
        assert len(truncated) < len(notes)
        assert "truncated" in truncated
        assert truncated.endswith("A" * 100)  # Should keep end
        
    @patch('subprocess.run')
    @patch('pathlib.Path.read_text')
    @patch('pathlib.Path.exists')
    def test_observation_too_large(self, mock_exists, mock_read_text, mock_run):
        """Test handling of observations that exceed token limit."""
        # Create a very large notes file
        huge_notes = "X" * 50000
        
        mock_exists.return_value = True
        mock_read_text.return_value = huge_notes
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        
        with patch('observation_builder.PROMPT_MAX', 100):
            obs = build_observation(turn_number=1)
            
            # Should truncate notes to fit
            if "error" not in obs:
                assert "notes_preview" in obs
                assert len(obs["notes_preview"]) < len(huge_notes)


class TestEndToEndScenarios:
    """Test complete scenarios with model responses."""
    
    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_deterministic_model_response_validation(self):
        """Test that we can validate model responses deterministically."""
        # Create a mock client that returns deterministic responses
        with patch('anthropic.Anthropic') as mock_anthropic:
            mock_client = Mock()
            mock_anthropic.return_value = mock_client
            
            # Define a sequence of model responses for a typical workflow
            responses = [
                # First: Read files
                """<scratchpad>
I need to understand the test failures. Let me read the test file first.
</scratchpad>
ACTION: {"read_files": ["tests/test_example.py"], "message": "Reading tests"}""",
                
                # Second: Apply a fix
                """<scratchpad>
I see the issue. The function is returning the wrong value. Let me fix it.
</scratchpad>
ACTION: {"patch": "--- a/example.py\\n+++ b/example.py\\n@@ -1,3 +1,3 @@\\n def get_value():\\n-    return 41\\n+    return 42"}""",
                
                # Third: Run tests
                """<scratchpad>
Let me run the tests to see if my fix worked.
</scratchpad>
ACTION: {"run_tests": true, "message": "Fix applied, checking tests"}""",
            ]
            
            # Configure mock to return responses in sequence
            mock_response = Mock()
            mock_response.content = [Mock(text=r) for r in responses]
            mock_client.messages.create.side_effect = [
                Mock(content=[Mock(text=responses[0])]),
                Mock(content=[Mock(text=responses[1])]),
                Mock(content=[Mock(text=responses[2])]),
            ]
            
            client = ClaudeClient()
            
            # Validate each response
            for i, expected_response in enumerate(responses):
                response = client.send_prompt(f"Prompt {i}")
                
                # Parse the response
                scratchpad, action_json = parse_scratchpad(response)
                
                # Validate format
                assert validate_response_format(response)
                assert scratchpad is not None
                assert action_json is not None
                
                # Validate action
                action = validate_action(json.loads(action_json))
                assert action is not None
                
                # Check specific action types
                if i == 0:
                    assert isinstance(action, ReadFilesAction)
                    assert action.message == "Reading tests"
                elif i == 1:
                    assert isinstance(action, PatchAction)
                    assert "return 42" in action.patch
                elif i == 2:
                    assert isinstance(action, RunTestsAction)
                    assert action.message == "Fix applied, checking tests"
    
    def test_malformed_model_responses(self):
        """Test handling of various malformed model responses."""
        malformed_responses = [
            # Missing closing tag
            """<scratchpad>
Thinking...
ACTION: {"run_tests": true}""",
            
            # Invalid JSON
            """<scratchpad>
Analyzing
</scratchpad>
ACTION: {run_tests: true}""",
            
            # Wrong action format
            """<scratchpad>
Working
</scratchpad>
ACTION: run_tests""",
            
            # Multiple actions (invalid)
            """<scratchpad>
Doing multiple things
</scratchpad>
ACTION: {"read_files": ["a.py"], "run_tests": true}""",
        ]
        
        for response in malformed_responses:
            scratchpad, action_json = parse_scratchpad(response)
            
            if action_json:
                try:
                    action = validate_action(json.loads(action_json))
                except:
                    action = None
            else:
                action = None
                
            # At least one part should fail for malformed responses
            assert (
                not validate_response_format(response) or 
                action is None or
                scratchpad is None
            )
    
    def test_edge_case_file_paths(self):
        """Test handling of edge case file paths in actions."""
        edge_cases = [
            {"read_files": ["../../../etc/passwd"]},  # Path traversal
            {"read_files": ["/etc/shadow"]},  # Absolute system path
            {"read_files": ["file with spaces.py"]},  # Spaces
            {"read_files": ["file\\nwith\\nnewlines.py"]},  # Newlines
            {"list_directory": "../../.."},  # Parent directory traversal
        ]
        
        for action_json in edge_cases:
            action = validate_action(action_json)
            # Validation should pass - security is handled in execution
            assert action is not None
    
    def test_large_patch_handling(self):
        """Test handling of very large patches."""
        # Create a large patch
        large_diff = "--- a/big.py\\n+++ b/big.py\\n"
        for i in range(1000):
            large_diff += f"@@ -{i},1 +{i},1 @@\\n-line{i}\\n+newline{i}\\n"
        
        action = validate_action({"patch": large_diff})
        assert isinstance(action, PatchAction)
        assert len(action.patch) > 10000


class TestModelUnderstanding:
    """Test that validates the model's understanding of the harness protocol."""
    
    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_model_protocol_understanding(self):
        """Use API to verify model understands the protocol."""
        with patch('anthropic.Anthropic') as mock_anthropic:
            # This test simulates checking if model "understands" by
            # validating response structure
            mock_client = Mock()
            mock_anthropic.return_value = mock_client
            
            # Test system prompt understanding
            test_prompt = """Current observation:

Directory tree:
src/
└── main.py (45 bytes)
tests/
└── test_main.py (120 bytes)

Git diff:
No changes

Test results:
Test Summary: 0 passed, 1 failed
Failed tests: test_main::test_addition

Previous message from yourself: Starting to fix tests

Please analyze the situation and take an action.

You must respond in the following format:
<scratchpad>
Your analysis and thoughts here...
</scratchpad>
ACTION: {"action_type": "...", ...}"""
            
            # Model should understand it needs to read files first
            expected_response = """<scratchpad>
I see there's a failing test. I should read both the test file and the implementation to understand what's wrong.
</scratchpad>
ACTION: {"read_files": ["tests/test_main.py", "src/main.py"]}"""
            
            mock_response = Mock()
            mock_response.content = [Mock(text=expected_response)]
            mock_client.messages.create.return_value = mock_response
            
            client = ClaudeClient()
            response = client.send_prompt(test_prompt, client.get_system_prompt())
            
            # Validate the response follows protocol
            scratchpad, action_json = parse_scratchpad(response)
            assert scratchpad is not None
            assert "failing test" in scratchpad.lower()
            
            action = validate_action(json.loads(action_json))
            assert isinstance(action, ReadFilesAction)
            assert "test_main.py" in action.read_files
            assert "main.py" in action.read_files
            
    def test_model_action_sequencing(self):
        """Test that model responses follow logical action sequences."""
        # Common patterns the model should follow
        logical_sequences = [
            # Pattern 1: Read -> Patch -> Test
            [
                {"read_files": ["file.py"]},
                {"patch": "--- a/file.py\\n+++ b/file.py\\n..."},
                {"run_tests": True}
            ],
            # Pattern 2: List -> Read -> Write Notes
            [
                {"list_directory": "src/"},
                {"read_files": ["src/module.py"]},
                {"write_notes": "Found the issue in module.py..."}
            ],
            # Pattern 3: Test -> Read -> Patch -> Test
            [
                {"run_tests": True},
                {"read_files": ["failing_test.py", "implementation.py"]},
                {"patch": "..."},
                {"run_tests": True}
            ]
        ]
        
        for sequence in logical_sequences:
            # Validate each action in sequence
            for action_json in sequence:
                action = validate_action(action_json)
                assert action is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 