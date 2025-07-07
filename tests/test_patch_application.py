#!/usr/bin/env python3
"""
Patch application battery test suite.

Tests unified diff patch application, git integration, security boundaries,
and error handling for malformed patches.
"""
import subprocess
import tempfile
import shutil
import os
import pytest
from pathlib import Path
import sys

# Add parent directory to path to import harness modules
sys.path.insert(0, str(Path(__file__).parent.parent / "harness"))

from patcher import apply_patch


class TestPatchApplication:
    """Tests for patch application and git integration."""
    
    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace with git initialized."""
        temp_dir = tempfile.mkdtemp(prefix="patch_test_")
        
        # Initialize git
        subprocess.run(["git", "init"], cwd=temp_dir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=temp_dir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_dir, capture_output=True)
        
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_valid_patch_application(self, temp_workspace):
        """Test applying a valid unified diff patch."""
        # Create initial file
        test_file = Path(temp_workspace) / "test.py"
        test_file.write_text("""def hello():
    print("Hello")
    
def goodbye():
    print("Goodbye")
""")
        
        # Create patch
        patch = """--- a/test.py
+++ b/test.py
@@ -1,5 +1,5 @@
 def hello():
-    print("Hello")
+    print("Hello, World!")
     
 def goodbye():
     print("Goodbye")
"""
        
        # Apply patch
        success, error = apply_patch(temp_workspace, patch)
        assert success, f"Patch should apply successfully: {error}"
        
        # Verify file was modified
        modified_content = test_file.read_text()
        assert 'print("Hello, World!")' in modified_content
        assert 'print("Hello")' not in modified_content
    
    def test_patch_creating_new_file(self, temp_workspace):
        """Test patch that creates a new file."""
        patch = """--- /dev/null
+++ b/new_file.py
@@ -0,0 +1,3 @@
+def new_function():
+    return "Created by patch"
+    
"""
        
        success, error = apply_patch(temp_workspace, patch)
        assert success
        
        new_file = Path(temp_workspace) / "new_file.py"
        assert new_file.exists()
        assert "Created by patch" in new_file.read_text()
    
    def test_patch_deleting_file(self, temp_workspace):
        """Test patch that deletes a file."""
        # Create file to delete
        file_to_delete = Path(temp_workspace) / "delete_me.py"
        file_to_delete.write_text("This file will be deleted")
        
        patch = """--- a/delete_me.py
+++ /dev/null
@@ -1,1 +0,0 @@
-This file will be deleted
"""
        
        success, error = apply_patch(temp_workspace, patch)
        assert success
        assert not file_to_delete.exists()
    
    def test_patch_with_subdirectories(self, temp_workspace):
        """Test patch affecting files in subdirectories."""
        # Create subdirectory and file
        subdir = Path(temp_workspace) / "src" / "utils"
        subdir.mkdir(parents=True)
        util_file = subdir / "helper.py"
        util_file.write_text("def helper():\n    return 1\n")
        
        patch = """--- a/src/utils/helper.py
+++ b/src/utils/helper.py
@@ -1,2 +1,2 @@
 def helper():
-    return 1
+    return 42
"""
        
        success, error = apply_patch(temp_workspace, patch)
        assert success
        assert "return 42" in util_file.read_text()
    
    def test_malformed_patch_header(self, temp_workspace):
        """Test patch with malformed header."""
        # Create file
        test_file = Path(temp_workspace) / "test.py"
        test_file.write_text("original content")
        
        # Bad header format
        bad_patch = """-- a/test.py
++ b/test.py
@@ -1 +1 @@
-original content
+new content
"""
        
        success, error = apply_patch(temp_workspace, bad_patch)
        assert not success
        assert error is not None
    
    def test_patch_context_mismatch(self, temp_workspace):
        """Test patch with context that doesn't match."""
        # Create file
        test_file = Path(temp_workspace) / "test.py" 
        test_file.write_text("line 1\nline 2\nline 3\n")
        
        # Patch expects different context
        patch = """--- a/test.py
+++ b/test.py
@@ -1,3 +1,3 @@
 line 1
-different line 2
+modified line 2
 line 3
"""
        
        success, error = apply_patch(temp_workspace, patch)
        assert not success
        assert "failed" in error.lower() or "hunk" in error.lower()
    
    def test_directory_traversal_prevention(self, temp_workspace):
        """Test that patches cannot escape workspace via directory traversal."""
        # Attempt to write outside workspace
        malicious_patches = [
            # Absolute path
            """--- a/test.py
+++ /etc/passwd
@@ -0,0 +1 @@
+malicious content
""",
            # Parent directory traversal
            """--- a/test.py
+++ b/../../../etc/passwd  
@@ -0,0 +1 @@
+malicious content
""",
            # Complex traversal
            """--- a/test.py
+++ b/./../../../../../../tmp/evil.txt
@@ -0,0 +1 @@
+malicious content
""",
        ]
        
        for patch in malicious_patches:
            success, error = apply_patch(temp_workspace, patch)
            # Should either fail or sanitize the path
            if success:
                # Check that no files were created outside workspace
                assert not Path("/etc/passwd").exists() or Path("/etc/passwd").stat().st_mtime < Path(temp_workspace).stat().st_mtime
                assert not Path("/tmp/evil.txt").exists()
    
    def test_git_commit_after_patch(self, temp_workspace):
        """Test that patches are properly committed to git."""
        # Create and commit initial file
        test_file = Path(temp_workspace) / "test.py"
        test_file.write_text("initial content")
        subprocess.run(["git", "add", "test.py"], cwd=temp_workspace)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=temp_workspace)
        
        # Apply patch
        patch = """--- a/test.py
+++ b/test.py
@@ -1 +1 @@
-initial content
+modified content
"""
        
        success, error = apply_patch(temp_workspace, patch)
        assert success
        
        # Commit the change
        subprocess.run(["git", "add", "-A"], cwd=temp_workspace)
        subprocess.run(["git", "commit", "-m", "Applied patch"], cwd=temp_workspace)
        
        # Check git log
        log_result = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=temp_workspace,
            capture_output=True,
            text=True
        )
        assert "Applied patch" in log_result.stdout
        assert "Initial commit" in log_result.stdout
    
    def test_patch_flip_flop_detection(self, temp_workspace):
        """Test detection of flip-flop edits (same line changed back and forth)."""
        # Create file
        test_file = Path(temp_workspace) / "test.py"
        test_file.write_text("value = 1")
        subprocess.run(["git", "add", "-A"], cwd=temp_workspace)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=temp_workspace)
        
        # First change
        patch1 = """--- a/test.py
+++ b/test.py
@@ -1 +1 @@
-value = 1
+value = 2
"""
        success, _ = apply_patch(temp_workspace, patch1)
        assert success
        subprocess.run(["git", "add", "-A"], cwd=temp_workspace)
        subprocess.run(["git", "commit", "-m", "Change to 2"], cwd=temp_workspace)
        
        # Change back
        patch2 = """--- a/test.py
+++ b/test.py
@@ -1 +1 @@
-value = 2
+value = 1
"""
        success, _ = apply_patch(temp_workspace, patch2)
        assert success
        subprocess.run(["git", "add", "-A"], cwd=temp_workspace)
        subprocess.run(["git", "commit", "-m", "Change back to 1"], cwd=temp_workspace)
        
        # Check git diff between commits
        diff_result = subprocess.run(
            ["git", "diff", "HEAD~2", "HEAD"],
            cwd=temp_workspace,
            capture_output=True,
            text=True
        )
        # Should show no net change
        assert diff_result.stdout.strip() == ""
    
    def test_binary_file_patch_rejection(self, temp_workspace):
        """Test that binary patches are handled properly."""
        # Create a binary file representation in patch
        binary_patch = """--- a/binary.dat
+++ b/binary.dat
Binary files differ
"""
        
        success, error = apply_patch(temp_workspace, binary_patch)
        # Should fail when encountering binary patches
        assert not success, "Binary patches should be rejected"
        if error:
            assert "binary" in error.lower() or "differ" in error.lower()
    
    def test_patch_line_endings(self, temp_workspace):
        """Test patches with different line endings (CRLF vs LF)."""
        # Create file with LF endings
        test_file = Path(temp_workspace) / "test.py"
        test_file.write_bytes(b"line1\nline2\nline3\n")
        
        # Patch with CRLF endings
        patch_crlf = b"""--- a/test.py\r\n+++ b/test.py\r\n@@ -1,3 +1,3 @@\r\n line1\r\n-line2\r\n+modified_line2\r\n line3\r\n"""
        
        # Convert to string for apply_patch
        success, error = apply_patch(temp_workspace, patch_crlf.decode('utf-8'))
        # Should handle line ending differences gracefully
        
        if success:
            content = test_file.read_text()
            assert "modified_line2" in content
    
    def test_empty_patch(self, temp_workspace):
        """Test handling of empty patch."""
        empty_patch = ""
        success, error = apply_patch(temp_workspace, empty_patch)
        # Should handle gracefully
        assert not success or error is not None
    
    def test_patch_permissions_preserved(self, temp_workspace):
        """Test that file permissions are preserved after patching."""
        # Create executable file
        script_file = Path(temp_workspace) / "script.sh"
        script_file.write_text("#!/bin/bash\necho 'Hello'")
        script_file.chmod(0o755)
        
        # Get original permissions
        orig_mode = script_file.stat().st_mode
        
        # Apply patch
        patch = """--- a/script.sh
+++ b/script.sh
@@ -1,2 +1,2 @@
 #!/bin/bash
-echo 'Hello'
+echo 'Hello, World!'
"""
        
        success, error = apply_patch(temp_workspace, patch)
        assert success
        
        # Check permissions are preserved
        new_mode = script_file.stat().st_mode
        assert new_mode == orig_mode
    
    def test_patch_symlink_handling(self, temp_workspace):
        """Test patch application on symlinks."""
        # Create a file and symlink
        target_file = Path(temp_workspace) / "target.py"
        target_file.write_text("target content")
        
        link_file = Path(temp_workspace) / "link.py"
        try:
            link_file.symlink_to("target.py")
        except OSError:
            pytest.skip("Symlinks not supported on this platform")
        
        # Try to patch the symlink
        patch = """--- a/link.py
+++ b/link.py
@@ -1 +1 @@
-target content
+modified content
"""
        
        success, error = apply_patch(temp_workspace, patch)
        # Should either follow symlink or fail gracefully
        if success:
            # If successful, target should be modified
            assert target_file.read_text() == "modified content"
        else:
            # If failed, original content should remain
            assert target_file.read_text() == "target content"
        
    def test_multiple_file_patch(self, temp_workspace):
        """Test patch affecting multiple files."""
        # Create files
        file1 = Path(temp_workspace) / "file1.py"
        file2 = Path(temp_workspace) / "file2.py"
        file1.write_text("content1")
        file2.write_text("content2")
        
        # Multi-file patch
        patch = """--- a/file1.py
+++ b/file1.py
@@ -1 +1 @@
-content1
+modified1
--- a/file2.py
+++ b/file2.py
@@ -1 +1 @@
-content2
+modified2
"""
        
        success, error = apply_patch(temp_workspace, patch)
        assert success
        assert file1.read_text() == "modified1"
        assert file2.read_text() == "modified2" 