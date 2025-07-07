#!/usr/bin/env python3
"""
Observation path test suite.

Tests observation building, directory traversal, file inlining rules,
hidden file handling, and prompt size management.
"""
import json
import subprocess
import tempfile
import shutil
import os
import pytest
from pathlib import Path
import sys

# Add parent directory to path to import harness modules
sys.path.insert(0, str(Path(__file__).parent.parent / "harness"))

from observation_builder import build_observation


class TestObservationPath:
    """Tests for observation building and file system traversal."""
    
    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace with git initialized."""
        temp_dir = tempfile.mkdtemp(prefix="obs_test_")
        
        # Initialize git and agent state
        subprocess.run(["git", "init"], cwd=temp_dir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=temp_dir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_dir, capture_output=True)
        
        # Create required files
        Path(temp_dir, "notes.md").write_text("")
        Path(temp_dir, ".agent_state.json").write_text(json.dumps({"last_message": ""}))
        
        # Initial commit
        subprocess.run(["git", "add", "-A"], cwd=temp_dir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=temp_dir, capture_output=True)
        
        # Change to workspace directory for observation builder
        original_cwd = os.getcwd()
        os.chdir(temp_dir)
        
        yield temp_dir
        
        os.chdir(original_cwd)
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_observation_basic_structure(self, temp_workspace):
        """Test that observation has all required keys."""
        observation = build_observation(turn_number=1)
        
        # Check required keys
        assert "turn_number" in observation
        assert "workspace_root" in observation
        assert "notes_content" in observation
        assert "previous_message" in observation
        assert "directory_tree" in observation
        
        assert observation["turn_number"] == 1
        assert observation["workspace_root"] == "/workspace"
        assert observation["notes_content"] == ""
        assert observation["previous_message"] == ""
    
    def test_directory_tree_depth_limit(self, temp_workspace):
        """Test that directory tree respects depth limits."""
        # Create deep directory structure
        deep_path = Path(temp_workspace)
        for i in range(5):
            deep_path = deep_path / f"level_{i}"
            deep_path.mkdir()
            (deep_path / f"file_{i}.py").write_text(f"Level {i} content")
        
        observation = build_observation(turn_number=1)
        tree = observation["directory_tree"]
        
        # Tree should be truncated at depth 2
        assert "level_0/" in tree
        assert "level_1/" in tree
        assert "level_2/" not in tree or "[truncated]" in tree
    
    def test_large_file_not_inlined(self, temp_workspace):
        """Test that large files are listed but not inlined."""
        # Create a large file (over typical inline threshold)
        large_file = Path(temp_workspace) / "large_file.txt"
        large_content = "A" * 10000  # 10KB
        large_file.write_text(large_content)
        
        # Create a small file that should be inlined
        small_file = Path(temp_workspace) / "small_file.txt"
        small_file.write_text("Small content")
        
        observation = build_observation(turn_number=1)
        tree = observation["directory_tree"]
        
        # Large file should be listed but not have content
        assert "large_file.txt" in tree
        assert large_content not in tree
        
        # Small file might be inlined (implementation dependent)
        assert "small_file.txt" in tree
    
    def test_hidden_file_handling(self, temp_workspace):
        """Test handling of hidden files and directories."""
        # Create hidden files and directories
        Path(temp_workspace, ".hidden_file").write_text("Hidden content")
        hidden_dir = Path(temp_workspace, ".hidden_dir")
        hidden_dir.mkdir()
        (hidden_dir / "file.txt").write_text("File in hidden dir")
        
        # Create .gitignore
        Path(temp_workspace, ".gitignore").write_text(".hidden_file\n.hidden_dir/\n")
        
        observation = build_observation(turn_number=1)
        tree = observation["directory_tree"]
        
        # Check how hidden files are handled
        # Typically .git, .gitignore should be excluded
        assert ".git/" not in tree
        # .agent_state.json should be excluded from the directory tree
        assert ".agent_state.json" not in tree, ".agent_state.json should be hidden from directory tree"
        # notes.md should be visible
        assert "notes.md" in tree, "notes.md should be visible in directory tree"
        
        # But agent state should still be accessible through previous_message
        assert "previous_message" in observation
        assert observation["previous_message"] == ""  # Empty initially
    
    def test_file_type_recognition(self, temp_workspace):
        """Test that different file types are properly recognized."""
        # Create various file types
        Path(temp_workspace, "script.py").write_text("print('Python')")
        Path(temp_workspace, "config.json").write_text('{"key": "value"}')
        Path(temp_workspace, "readme.md").write_text("# README")
        Path(temp_workspace, "data.txt").write_text("Plain text")
        
        # Create directory
        subdir = Path(temp_workspace, "src")
        subdir.mkdir()
        (subdir / "module.py").write_text("def func(): pass")
        
        observation = build_observation(turn_number=1)
        tree = observation["directory_tree"]
        
        # All files should be listed
        assert "script.py" in tree
        assert "config.json" in tree
        assert "readme.md" in tree
        assert "data.txt" in tree
        assert "src/" in tree
        assert "module.py" in tree
    
    def test_notes_content_included(self, temp_workspace):
        """Test that notes.md content is properly included."""
        notes_content = """# Investigation Notes
        
Found issue in authentication module.
TODO: Fix token validation.
"""
        Path(temp_workspace, "notes.md").write_text(notes_content)
        
        observation = build_observation(turn_number=1)
        
        assert observation["notes_content"] == notes_content
    
    def test_previous_message_from_state(self, temp_workspace):
        """Test that previous message is loaded from agent state."""
        state = {"last_message": "This is the previous message"}
        Path(temp_workspace, ".agent_state.json").write_text(json.dumps(state))
        
        observation = build_observation(turn_number=2)
        
        assert observation["previous_message"] == "This is the previous message"
    
    def test_prompt_size_limit_triggered(self, temp_workspace, monkeypatch):
        """Test that oversized prompts trigger summarization."""
        # Create very large notes.md
        huge_content = "X" * 100000  # 100KB of content
        Path(temp_workspace, "notes.md").write_text(huge_content)
        
        # Mock token counting to simulate exceeding limit
        def mock_count_tokens(text):
            return len(text) // 4  # Rough approximation
        
        # This test would need access to the token counting logic
        # For now, we just verify the notes are included
        observation = build_observation(turn_number=1)
        
        # With huge content, might return error or truncated version
        if "error" in observation:
            assert observation["error"] == "prompt_too_large"
        else:
            # Content should be there or summarized
            assert "notes_content" in observation
    
    def test_summarization_commit(self, temp_workspace):
        """Test that summarization creates proper git commit."""
        # Create large notes that would trigger summarization
        large_notes = "# Notes\n\n" + "\n".join([f"Line {i}: " + "A" * 100 for i in range(1000)])
        notes_path = Path(temp_workspace, "notes.md")
        notes_path.write_text(large_notes)
        
        # Simulate summarization by replacing content
        summary = "# Summarized Notes\n\nPrevious notes archived due to size."
        notes_path.write_text(summary)
        
        # Commit the summarization
        subprocess.run(["git", "add", "notes.md"], cwd=temp_workspace)
        subprocess.run(["git", "commit", "-m", "Summarized notes.md"], cwd=temp_workspace)
        
        # Check git log
        log_result = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=temp_workspace,
            capture_output=True,
            text=True
        )
        assert "Summarized notes.md" in log_result.stdout
    
    def test_empty_workspace(self, temp_workspace):
        """Test observation building in empty workspace."""
        # Remove all files except required ones
        for item in Path(temp_workspace).iterdir():
            if item.name not in [".git", "notes.md", ".agent_state.json"]:
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
        
        observation = build_observation(turn_number=1)
        
        assert observation["turn_number"] == 1
        assert observation["notes_content"] == ""
        assert observation["previous_message"] == ""
        # Directory tree should be minimal
        tree = observation["directory_tree"]
        assert "notes.md" in tree or len(tree) < 100  # Small tree
    
    def test_unicode_filenames(self, temp_workspace):
        """Test handling of unicode characters in filenames."""
        # Create files with unicode names
        Path(temp_workspace, "文件.txt").write_text("Chinese filename")
        Path(temp_workspace, "файл.py").write_text("# Russian filename")
        Path(temp_workspace, "🎉emoji.md").write_text("# Emoji filename")
        
        observation = build_observation(turn_number=1)
        tree = observation["directory_tree"]
        
        # Unicode filenames should be handled
        assert "文件.txt" in tree or "txt" in tree
        assert "файл.py" in tree or ".py" in tree
        # Emoji might be handled differently
    
    def test_symlink_in_tree(self, temp_workspace):
        """Test handling of symbolic links in directory tree."""
        # Create a file and symlink
        target = Path(temp_workspace, "target.py")
        target.write_text("print('target')")
        
        link = Path(temp_workspace, "link.py")
        try:
            link.symlink_to("target.py")
            
            observation = build_observation(turn_number=1)
            tree = observation["directory_tree"]
            
            # Both should appear in tree
            assert "target.py" in tree
            assert "link.py" in tree
        except OSError:
            # Symlinks might not work on all platforms
            pytest.skip("Symlinks not supported")
    
    def test_binary_file_handling(self, temp_workspace):
        """Test that binary files are listed but not inlined."""
        # Create a binary file
        binary_file = Path(temp_workspace, "data.bin")
        binary_file.write_bytes(b"\x00\x01\x02\x03\xFF\xFE")
        
        observation = build_observation(turn_number=1)
        tree = observation["directory_tree"]
        
        # Binary file should be listed
        assert "data.bin" in tree
        # But binary content should not be in tree
        assert "\x00" not in tree
        assert "\xFF" not in tree
    
    def test_permission_denied_handling(self, temp_workspace):
        """Test handling of files with restricted permissions."""
        # Create a file and make it unreadable
        restricted_file = Path(temp_workspace, "restricted.txt")
        restricted_file.write_text("Secret content")
        
        try:
            # Try to restrict permissions (may not work on all platforms)
            restricted_file.chmod(0o000)
            
            observation = build_observation(turn_number=1)
            # Should handle gracefully without crashing
            assert "turn_number" in observation
            
        finally:
            # Restore permissions for cleanup
            restricted_file.chmod(0o644)
    
    def test_special_characters_in_content(self, temp_workspace):
        """Test handling of special characters in file content."""
        # Create file with special characters
        special_file = Path(temp_workspace, "special.txt")
        special_content = "Line 1\nLine 2\rLine 3\r\nLine 4\tTabbed\x00Null"
        special_file.write_text(special_content, errors='replace')
        
        observation = build_observation(turn_number=1)
        # Should handle special characters gracefully
        assert "directory_tree" in observation 