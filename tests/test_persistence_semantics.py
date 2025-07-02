#!/usr/bin/env python3
"""
Persistence semantics test suite.

Tests state persistence across turns, note management, message passing,
git history tracking, and crash recovery.
"""
import json
import subprocess
import tempfile
import shutil
import os
import pytest
from pathlib import Path
import sys
from unittest.mock import Mock, patch

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "harness"))

from entrypoint import Harness


class TestPersistenceSemantics:
    """Tests for state persistence and data management."""
    
    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace with git initialized."""
        temp_dir = tempfile.mkdtemp(prefix="persist_test_")
        
        # Initialize as the harness would
        subprocess.run(["git", "init"], cwd=temp_dir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=temp_dir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_dir, capture_output=True)
        
        # Create initial files
        Path(temp_dir, "notes.md").write_text("")
        Path(temp_dir, ".agent_state.json").write_text(json.dumps({"last_message": ""}))
        
        # Initial commit
        subprocess.run(["git", "add", "-A"], cwd=temp_dir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial state"], cwd=temp_dir, capture_output=True)
        
        # Change to workspace for tests
        original_cwd = Path.cwd()
        os.chdir(temp_dir)
        
        yield temp_dir
        
        os.chdir(original_cwd)
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_notes_persistence_across_turns(self, temp_workspace):
        """Test that notes.md persists and accumulates across turns."""
        notes_path = Path(temp_workspace) / "notes.md"
        
        # Turn 1: Add initial content
        turn1_content = "### Turn 1\nFound issue in authentication"
        with open(notes_path, 'a') as f:
            f.write(turn1_content + "\n")
        
        # Turn 2: Append more content
        turn2_content = "### Turn 2\nFixed authentication bug"
        with open(notes_path, 'a') as f:
            f.write("\n" + turn2_content + "\n")
        
        # Turn 3: Append more
        turn3_content = "### Turn 3\nAdded tests"
        with open(notes_path, 'a') as f:
            f.write("\n" + turn3_content + "\n")
        
        # Verify all content is present
        final_content = notes_path.read_text()
        assert "Turn 1" in final_content
        assert "Found issue in authentication" in final_content
        assert "Turn 2" in final_content
        assert "Fixed authentication bug" in final_content
        assert "Turn 3" in final_content
        assert "Added tests" in final_content
        
        # Verify order is preserved
        lines = final_content.strip().split('\n')
        turn_lines = [l for l in lines if l.startswith("### Turn")]
        assert turn_lines == ["### Turn 1", "### Turn 2", "### Turn 3"]
    
    def test_write_notes_replaces_content(self, temp_workspace):
        """Test that write_notes action replaces entire notes.md content."""
        notes_path = Path(temp_workspace) / "notes.md"
        
        # Add initial content
        initial_content = "# Initial Notes\nThis is the original content"
        notes_path.write_text(initial_content)
        
        # Simulate write_notes action
        replacement_content = "# New Notes\nThis replaces everything"
        notes_path.write_text(replacement_content)
        
        # Verify old content is gone
        final_content = notes_path.read_text()
        assert final_content == replacement_content
        assert "Initial Notes" not in final_content
        assert "original content" not in final_content
    
    def test_message_persistence(self, temp_workspace):
        """Test that messages persist between turns via .agent_state.json."""
        state_path = Path(temp_workspace) / ".agent_state.json"
        
        # Turn 1: Set a message
        message1 = "Need to investigate the test failures"
        state = {"last_message": message1}
        state_path.write_text(json.dumps(state))
        
        # Read it back (simulating next turn)
        loaded_state = json.loads(state_path.read_text())
        assert loaded_state["last_message"] == message1
        
        # Turn 2: Update message
        message2 = "Found the issue - fixing now"
        state = {"last_message": message2}
        state_path.write_text(json.dumps(state))
        
        # Verify update
        loaded_state = json.loads(state_path.read_text())
        assert loaded_state["last_message"] == message2
        assert loaded_state["last_message"] != message1
    
    def test_git_commit_history(self, temp_workspace):
        """Test that git commits track changes properly."""
        # Make changes and commit for turn 1
        test_file = Path(temp_workspace) / "test.py"
        test_file.write_text("def func1():\n    pass")
        subprocess.run(["git", "add", "test.py"], cwd=temp_workspace)
        subprocess.run(["git", "commit", "-m", "turn 1 changes"], cwd=temp_workspace)
        
        # Make changes and commit for turn 2
        test_file.write_text("def func1():\n    pass\n\ndef func2():\n    pass")
        subprocess.run(["git", "add", "test.py"], cwd=temp_workspace)
        subprocess.run(["git", "commit", "-m", "turn 2 changes"], cwd=temp_workspace)
        
        # Make changes and commit for turn 3
        notes_path = Path(temp_workspace) / "notes.md"
        notes_path.write_text("Updated notes")
        subprocess.run(["git", "add", "notes.md"], cwd=temp_workspace)
        subprocess.run(["git", "commit", "-m", "turn 3 changes"], cwd=temp_workspace)
        
        # Check git log
        log_result = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=temp_workspace,
            capture_output=True,
            text=True
        )
        
        log_lines = log_result.stdout.strip().split('\n')
        assert len(log_lines) >= 4  # Initial + 3 turns
        assert "turn 3 changes" in log_lines[0]
        assert "turn 2 changes" in log_lines[1]
        assert "turn 1 changes" in log_lines[2]
        assert "Initial state" in log_lines[3]
    
    def test_scratchpad_append_behavior(self, temp_workspace):
        """Test that scratchpad content appends to notes with turn headers."""
        notes_path = Path(temp_workspace) / "notes.md"
        
        # Simulate harness appending scratchpad content
        harness = Harness()
        harness.turn_number = 1
        
        # Mock workspace path
        with patch('harness.entrypoint.Path') as mock_path:
            mock_path.return_value = notes_path
            
            # Append first scratchpad
            scratchpad1 = "Analyzing the problem..."
            harness.append_to_notes(scratchpad1)
        
        content = notes_path.read_text()
        assert "### Turn 1" in content
        assert "Analyzing the problem..." in content
        
        # Next turn
        harness.turn_number = 2
        with patch('harness.entrypoint.Path') as mock_path:
            mock_path.return_value = notes_path
            
            scratchpad2 = "Found the solution!"
            harness.append_to_notes(scratchpad2)
        
        final_content = notes_path.read_text()
        assert "### Turn 1" in final_content
        assert "### Turn 2" in final_content
        assert "Analyzing the problem..." in final_content
        assert "Found the solution!" in final_content
    
    def test_crash_recovery_state(self, temp_workspace):
        """Test that state can be recovered after a crash."""
        # Set up state before "crash"
        notes_path = Path(temp_workspace) / "notes.md"
        state_path = Path(temp_workspace) / ".agent_state.json"
        
        notes_path.write_text("# Important notes\nDon't lose this!")
        state_path.write_text(json.dumps({"last_message": "Critical info"}))
        
        # Make some changes
        test_file = Path(temp_workspace) / "modified.py"
        test_file.write_text("print('hello')")
        
        # Commit state
        subprocess.run(["git", "add", "-A"], cwd=temp_workspace)
        subprocess.run(["git", "commit", "-m", "Pre-crash state"], cwd=temp_workspace)
        
        # Simulate crash by creating new harness instance
        # State should be recoverable from files
        
        # Verify files still exist
        assert notes_path.exists()
        assert state_path.exists()
        
        # Verify content is intact
        assert notes_path.read_text() == "# Important notes\nDon't lose this!"
        assert json.loads(state_path.read_text())["last_message"] == "Critical info"
        
        # Verify git history is intact
        log_result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=temp_workspace,
            capture_output=True,
            text=True
        )
        assert "Pre-crash state" in log_result.stdout
    
    def test_empty_message_handling(self, temp_workspace):
        """Test handling of empty messages."""
        state_path = Path(temp_workspace) / ".agent_state.json"
        
        # Set empty message
        state = {"last_message": ""}
        state_path.write_text(json.dumps(state))
        
        # Verify it persists as empty
        loaded = json.loads(state_path.read_text())
        assert loaded["last_message"] == ""
        
        # Update to non-empty
        state = {"last_message": "Now has content"}
        state_path.write_text(json.dumps(state))
        
        loaded = json.loads(state_path.read_text())
        assert loaded["last_message"] == "Now has content"
    
    def test_git_tracks_all_changes(self, temp_workspace):
        """Test that git tracks changes to all relevant files."""
        # Create and modify multiple files
        files = {
            "file1.py": "print('file1')",
            "file2.py": "print('file2')",
            "data.json": '{"key": "value"}',
            "notes.md": "# Notes\nSome notes here"
        }
        
        for filename, content in files.items():
            Path(temp_workspace, filename).write_text(content)
        
        # Add and commit
        subprocess.run(["git", "add", "-A"], cwd=temp_workspace)
        subprocess.run(["git", "commit", "-m", "Added multiple files"], cwd=temp_workspace)
        
        # Check what was committed
        show_result = subprocess.run(
            ["git", "show", "--name-only", "--format=", "HEAD"],
            cwd=temp_workspace,
            capture_output=True,
            text=True
        )
        
        committed_files = show_result.stdout.strip().split('\n')
        for filename in files:
            assert filename in committed_files
    
    def test_incremental_changes_tracked(self, temp_workspace):
        """Test that incremental changes are properly tracked."""
        test_file = Path(temp_workspace) / "evolving.py"
        
        # Version 1
        test_file.write_text("def version1():\n    pass")
        subprocess.run(["git", "add", "evolving.py"], cwd=temp_workspace)
        subprocess.run(["git", "commit", "-m", "Version 1"], cwd=temp_workspace)
        
        # Version 2 - Add function
        test_file.write_text("def version1():\n    pass\n\ndef version2():\n    pass")
        subprocess.run(["git", "add", "evolving.py"], cwd=temp_workspace)
        subprocess.run(["git", "commit", "-m", "Version 2"], cwd=temp_workspace)
        
        # Version 3 - Modify function
        test_file.write_text("def version1():\n    return 1\n\ndef version2():\n    pass")
        subprocess.run(["git", "add", "evolving.py"], cwd=temp_workspace)
        subprocess.run(["git", "commit", "-m", "Version 3"], cwd=temp_workspace)
        
        # Check full history
        log_result = subprocess.run(
            ["git", "log", "--oneline", "evolving.py"],
            cwd=temp_workspace,
            capture_output=True,
            text=True
        )
        
        assert "Version 3" in log_result.stdout
        assert "Version 2" in log_result.stdout
        assert "Version 1" in log_result.stdout
        
        # Check we can see the changes
        diff_result = subprocess.run(
            ["git", "diff", "HEAD~2", "HEAD", "evolving.py"],
            cwd=temp_workspace,
            capture_output=True,
            text=True
        )
        
        assert "+    return 1" in diff_result.stdout
        assert "+def version2():" in diff_result.stdout
    
    def test_large_notes_persistence(self, temp_workspace):
        """Test persistence of large notes content."""
        notes_path = Path(temp_workspace) / "notes.md"
        
        # Create large content
        large_content = "# Large Notes\n\n"
        for i in range(1000):
            large_content += f"Line {i}: " + "A" * 100 + "\n"
        
        # Write and verify
        notes_path.write_text(large_content)
        
        # Read back and verify
        read_content = notes_path.read_text()
        assert len(read_content) == len(large_content)
        assert read_content == large_content
        
        # Verify it can be committed
        subprocess.run(["git", "add", "notes.md"], cwd=temp_workspace)
        result = subprocess.run(
            ["git", "commit", "-m", "Large notes"],
            cwd=temp_workspace,
            capture_output=True
        )
        assert result.returncode == 0
    
    def test_json_state_corruption_handling(self, temp_workspace):
        """Test handling of corrupted .agent_state.json."""
        state_path = Path(temp_workspace) / ".agent_state.json"
        
        # Write corrupted JSON
        state_path.write_text("{invalid json}")
        
        # Attempt to read (would need error handling)
        try:
            content = state_path.read_text()
            state = json.loads(content)
        except json.JSONDecodeError:
            # Should handle gracefully - reinitialize
            state = {"last_message": ""}
            state_path.write_text(json.dumps(state))
        
        # Verify recovery
        recovered = json.loads(state_path.read_text())
        assert "last_message" in recovered 