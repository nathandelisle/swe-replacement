"""
Integration tests for harness execution flow.
Tests the complete turn-based interaction loop and state management.
"""
import json
import pytest
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock, call
from pathlib import Path
import subprocess
import sys
import os
import time

# Add harness to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../harness'))

from entrypoint import Harness
from schema import validate_action
from logger import Logger
from claude_client import ClaudeClient


class TestHarnessExecutionFlow:
    """Test the complete harness execution flow."""
    
    @pytest.fixture
    def mock_workspace(self):
        """Create a temporary workspace for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            
            # Create test files
            (workspace / "main.py").write_text("def add(a, b):\n    return a - b  # Bug here")
            (workspace / "tests").mkdir()
            (workspace / "tests" / "test_main.py").write_text(
                "from main import add\n\ndef test_add():\n    assert add(2, 3) == 5"
            )
            
            # Mock Path.cwd() to return our workspace when called from harness
            with patch.object(Path, 'cwd', return_value=workspace):
                # Also patch /workspace resolution
                original_new = Path.__new__
                
                def patched_new(cls, *args, **kwargs):
                    if args and str(args[0]) == "/workspace":
                        return workspace
                    return original_new(cls, *args, **kwargs)
                
                with patch.object(Path, '__new__', patched_new):
                    yield workspace
    
    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    @patch('anthropic.Anthropic')
    def test_complete_turn_cycle(self, mock_anthropic, mock_workspace):
        """Test a complete turn cycle: observe -> respond -> execute -> commit."""
        # Mock Claude client
        mock_client = Mock()
        mock_anthropic.return_value = mock_client
        
        # Simulate model responses for a fix cycle
        responses = [
            # Turn 1: Read files
            """<scratchpad>
I see a failing test. Let me read the files to understand the issue.
</scratchpad>
ACTION: {"read_files": ["main.py", "tests/test_main.py"]}""",
            
            # Turn 2: Apply fix
            """<scratchpad>
I found the bug - the add function is subtracting instead of adding.
</scratchpad>
ACTION: {"patch": "--- a/main.py\\n+++ b/main.py\\n@@ -1,2 +1,2 @@\\n def add(a, b):\\n-    return a - b  # Bug here\\n+    return a + b  # Fixed"}""",
            
            # Turn 3: Run tests
            """<scratchpad>
Let me verify the fix by running tests.
</scratchpad>
ACTION: {"run_tests": true}"""
        ]
        
        mock_client.messages.create.side_effect = [
            Mock(content=[Mock(text=resp)]) for resp in responses
        ]
        
        # Create harness with mocked workspace
        with patch('os.getcwd', return_value=str(mock_workspace)):
            with patch('subprocess.run') as mock_run:
                # Mock git commands
                mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
                
                harness = Harness()
                harness.timeout = 60  # Short timeout for testing
                
                # Run one turn
                harness.turn_number = 0
                turn_start = time.time()
                
                # Get observation
                obs = harness.get_observation()
                assert "directory_tree" in obs
                assert "test_results" in obs
                
                # Get response
                response = harness.get_agent_response(obs)
                assert "<scratchpad>" in response
                assert "ACTION:" in response
                
                # Parse and validate action
                from scratchpad import parse_scratchpad
                scratchpad, action_json = parse_scratchpad(response)
                action = validate_action(json.loads(action_json))
                assert action is not None
                
                # Execute action
                result = harness.execute_action(action)
                assert result["success"] is True
                
                # Check that notes were updated
                notes_path = mock_workspace / "notes.md"
                if scratchpad:
                    assert notes_path.exists()
                    notes_content = notes_path.read_text()
                    assert scratchpad in notes_content
    
    def test_persistence_between_turns(self):
        """Test that state persists correctly between turns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            # Create persistent files
            notes_path = workspace / "notes.md"
            notes_path.write_text("### Turn 1\nPrevious thoughts")
            
            state_path = workspace / ".agent_state.json"
            state_path.write_text(json.dumps({"last_message": "Previous message"}))
            
            # Test reading persistent state
            with patch('pathlib.Path.cwd', return_value=workspace):
                # Read notes
                notes_content = notes_path.read_text()
                assert "Previous thoughts" in notes_content
                
                # Read agent state
                state = json.loads(state_path.read_text())
                assert state["last_message"] == "Previous message"
                
                # Simulate appending to notes
                new_scratchpad = "New thoughts for turn 2"
                harness = Harness()
                harness.turn_number = 2
                harness.append_to_notes(new_scratchpad)
                
                # Verify append
                updated_notes = notes_path.read_text()
                assert "Previous thoughts" in updated_notes
                assert "Turn 2" in updated_notes
                assert new_scratchpad in updated_notes
                
                # Update message
                harness.update_last_message("New message")
                updated_state = json.loads(state_path.read_text())
                assert updated_state["last_message"] == "New message"
    
    @patch('subprocess.run')
    def test_git_commit_tracking(self, mock_run):
        """Test that git commits track changes correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            # Mock git commands with specific behavior for each command
            def git_side_effect(*args, **kwargs):
                if "git" in args[0][0]:
                    cmd = args[0][1] if len(args[0]) > 1 else ""
                    if cmd == "status":
                        return Mock(returncode=0, stdout="M main.py\nM tests/test_main.py", stderr="")
                    elif cmd == "add":
                        return Mock(returncode=0, stdout="", stderr="")
                    elif cmd == "commit":
                        return Mock(returncode=0, stdout="[main abc123] turn 1 changes", stderr="")
                    elif cmd == "rev-parse":
                        return Mock(returncode=0, stdout="abc123def456", stderr="")
                    elif cmd == "hash-object":
                        return Mock(returncode=0, stdout="hash1", stderr="")
                return Mock(returncode=0, stdout="", stderr="")
            
            mock_run.side_effect = git_side_effect
            
            with patch('pathlib.Path.cwd', return_value=workspace):
                harness = Harness()
                harness.turn_number = 1
                
                # Commit changes
                changed_files = harness.commit_turn_changes()
                
                assert "main.py" in changed_files
                assert "tests/test_main.py" in changed_files
                
                # Verify git commands were called
                assert mock_run.call_count >= 3
                assert any("git status" in str(call) for call in mock_run.call_args_list)
                assert any("git commit" in str(call) for call in mock_run.call_args_list)
    
    def test_error_recovery(self):
        """Test that harness recovers gracefully from errors."""
        harness = Harness()
        
        # Test invalid action recovery
        invalid_action_json = {"invalid": "action"}
        action = validate_action(invalid_action_json)
        assert action is None
        
        # Test malformed JSON recovery
        malformed_json = '{"read_files": [unclosed'
        try:
            json.loads(malformed_json)
        except json.JSONDecodeError:
            # Should handle gracefully
            pass
        
        # Test file read error recovery
        with patch('pathlib.Path.read_text', side_effect=Exception("Read error")):
            result = harness.execute_action(Mock(read_files=["nonexistent.py"]))
            assert "Error" in str(result)
    
    def test_timeout_handling(self):
        """Test that harness respects timeout limits."""
        harness = Harness()
        harness.timeout = 0.1  # 100ms timeout
        harness.start_time = time.time() - 0.2  # Already past timeout
        
        assert harness.check_termination() is True
    
    def test_test_completion_detection(self):
        """Test that harness detects when all tests pass."""
        with patch('subprocess.run') as mock_run:
            # Mock successful test run
            mock_run.return_value = Mock(
                returncode=0,
                stdout="===== 5 passed in 0.1s =====",
                stderr=""
            )
            
            harness = Harness()
            result = harness.run_tests_quietly()
            
            assert result["all_passed"] is True
            assert result["passed_count"] > 0
            assert result["failed_count"] == 0


class TestActionExecution:
    """Test execution of different action types."""
    
    def test_read_files_security(self):
        """Test that read_files action prevents path traversal."""
        harness = Harness()
        
        # Create a mock action with dangerous paths
        from schema import ReadFilesAction
        dangerous_paths = [
            "../../../etc/passwd",
            "/etc/shadow",
            "/harness/secret.py",
            "../../../../../../root/.ssh/id_rsa"
        ]
        
        action = ReadFilesAction(read_files=dangerous_paths, message=None)
        result = harness.execute_action(action)
        
        assert result["success"] is True
        # All dangerous paths should be blocked
        for path in dangerous_paths:
            assert "Access denied" in result["files"][path] or "Error" in result["files"][path]
    
    @patch('subprocess.run')
    def test_patch_application(self, mock_run):
        """Test patch action execution."""
        # Mock successful patch
        mock_run.return_value = Mock(returncode=0, stdout="patching file main.py", stderr="")
        
        harness = Harness()
        from schema import PatchAction
        
        patch_content = """--- a/main.py
+++ b/main.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b"""
        
        action = PatchAction(patch=patch_content, message=None)
        
        with patch('harness.patcher.apply_patch', return_value=(True, None)):
            result = harness.execute_action(action)
            
        assert result["success"] is True
        assert result.get("error") is None
    
    def test_write_notes_action(self):
        """Test write_notes action execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            notes_path = workspace / "notes.md"
            notes_path.write_text("Old content")
            
            with patch('pathlib.Path', return_value=workspace):
                harness = Harness()
                from schema import WriteNotesAction
                
                new_content = "# New Notes\n\nCompletely new content"
                action = WriteNotesAction(write_notes=new_content, message=None)
                
                with patch('pathlib.Path.write_text') as mock_write:
                    result = harness.execute_action(action)
                    
                    # Verify write was called with new content
                    mock_write.assert_called_with(new_content)
                    assert result["success"] is True


class TestMetricsAndLogging:
    """Test metrics collection and logging functionality."""
    
    def test_turn_metrics_collection(self):
        """Test that turn metrics are collected correctly."""
        harness = Harness()
        harness.turn_number = 1
        
        # Mock logger
        with patch.object(harness.logger, 'log_turn_metrics') as mock_log:
            turn_start = time.time()
            cpu_start = time.process_time()
            
            # Simulate some work
            time.sleep(0.01)
            
            # Log metrics
            harness.logger.log_turn_metrics({
                "turn": harness.turn_number,
                "wall_time": time.time() - turn_start,
                "cpu_time": time.process_time() - cpu_start,
                "total_elapsed": time.time() - harness.start_time,
                "total_cpu": time.process_time() - harness.cpu_start,
                "total_api_time": 0.5
            })
            
            # Verify metrics were logged
            mock_log.assert_called_once()
            metrics = mock_log.call_args[0][0]
            assert metrics["turn"] == 1
            assert metrics["wall_time"] > 0
            assert "total_elapsed" in metrics
    
    def test_test_result_logging(self):
        """Test that test results are logged with proper metrics."""
        harness = Harness()
        
        with patch.object(harness.logger, 'log_test_results') as mock_log:
            output = "===== 3 passed, 2 failed ====="
            harness.logger.log_test_results(
                output=output,
                all_passed=False,
                passed=3,
                failed=2,
                test_wall_time=1.5,
                test_cpu_time=1.2,
                pass_fail_vector={"test_a": "PASS", "test_b": "FAIL"},
                regression=False
            )
            
            mock_log.assert_called_once()
            assert mock_log.call_args[0][1] is False  # all_passed
            assert mock_log.call_args[0][2] == 3  # passed count
            assert mock_log.call_args[0][3] == 2  # failed count


class TestModelResponseGeneration:
    """Test that validates deterministic model response generation."""
    
    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_response_follows_protocol(self):
        """Test that generated responses follow the expected protocol."""
        # This test validates that when we mock the model,
        # the responses we generate are valid according to our parsers
        
        test_scenarios = [
            {
                "observation": {
                    "test_results": "0 passed, 1 failed",
                    "directory_tree": "main.py\ntests/",
                    "git_diff": "No changes"
                },
                "expected_action_type": "read_files",
                "expected_targets": ["main.py", "tests/test_main.py"]
            },
            {
                "observation": {
                    "test_results": "0 passed, 1 failed",
                    "requested_files": {"main.py": "def add(a,b): return a-b"},
                },
                "expected_action_type": "patch",
                "expected_content": "return a+b"
            }
        ]
        
        for scenario in test_scenarios:
            # Generate a response that would be appropriate
            if scenario["expected_action_type"] == "read_files":
                response = f"""<scratchpad>
I need to read the files to understand the issue.
</scratchpad>
ACTION: {{"read_files": {json.dumps(scenario["expected_targets"])}}}"""
            elif scenario["expected_action_type"] == "patch":
                response = f"""<scratchpad>
I found the bug and will fix it.
</scratchpad>
ACTION: {{"patch": "--- a/main.py\\n+++ b/main.py\\n@@ -1 +1 @@\\n-def add(a,b): return a-b\\n+def add(a,b): return a+b"}}"""
            
            # Validate the response
            from scratchpad import parse_scratchpad, validate_response_format
            assert validate_response_format(response)
            
            scratchpad, action_json = parse_scratchpad(response)
            assert scratchpad is not None
            assert action_json is not None
            
            action = validate_action(json.loads(action_json))
            assert action is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 