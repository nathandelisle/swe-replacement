"""
Module for applying unified diff patches to files.
"""
import difflib
import os
import subprocess
from typing import List, Tuple, Optional
from pathlib import Path
import re


def validate_patch_paths(patch_content: str) -> Tuple[bool, str]:
    """
    Validate that patch paths don't try to escape the workspace.
    
    Args:
        patch_content: The patch content to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check for path traversal attempts in diff headers
    for line in patch_content.splitlines():
        if line.startswith(('---', '+++', 'diff --git')):
            # Check for .. sequences that could escape
            if '..' in line:
                return False, "Patch contains path traversal attempt (..)"
            # Check for absolute paths
            if line.strip().endswith(('/etc', '/usr', '/bin', '/sbin', '/harness', '/results')):
                return False, "Patch attempts to modify system directories"
                
    # Check for symlink creation
    if 'symbolic link' in patch_content or 'symlink' in patch_content:
        return False, "Patch attempts to create symbolic links"
        
    return True, ""


def apply_patch(workspace_dir: str, patch_content: str) -> Tuple[bool, str]:
    """
    Apply a unified diff patch to files in the workspace.
    
    Args:
        workspace_dir: The workspace directory
        patch_content: The unified diff content
        
    Returns:
        Tuple of (success, error_message)
    """
    try:
        # First validate the patch
        is_valid, error_msg = validate_patch_paths(patch_content)
        if not is_valid:
            return False, f"Security validation failed: {error_msg}"
            
        # Write patch to temporary file
        patch_file = Path(workspace_dir) / ".tmp_patch"
        patch_file.write_text(patch_content)
        
        # Apply patch using git apply with security flags
        # Note: --no-symlinks might not be available in all git versions
        # Try with it first, fall back if needed
        git_apply_args = [
            "git", "apply",
            "--unsafe-paths=off",  # Prevent paths outside repo
            f"--directory={workspace_dir}",  # Force working directory
            str(patch_file)
        ]
        
        # First try without --no-symlinks in case git version doesn't support it
        result = subprocess.run(
            git_apply_args,
            cwd=workspace_dir,
            capture_output=True,
            text=True
        )
        
        # Clean up temp file
        patch_file.unlink(missing_ok=True)
        
        if result.returncode == 0:
            return True, ""
        else:
            # Check if it's a security-related failure
            if "outside repository" in result.stderr or "symlink" in result.stderr:
                return False, f"Security violation: {result.stderr}"
            return False, f"Failed to apply patch: {result.stderr}"
            
    except Exception as e:
        return False, str(e)


def create_unified_diff(file_path: str, original_content: str, 
                       new_content: str) -> str:
    """
    Create a unified diff between original and new content.
    
    Args:
        file_path: Path to the file (for diff header)
        original_content: Original file content
        new_content: New file content
        
    Returns:
        Unified diff string
    """
    original_lines = original_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    
    diff = difflib.unified_diff(
        original_lines,
        new_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        lineterm=''
    )
    
    return ''.join(diff)


def parse_unified_diff(diff_text: str) -> List[dict]:
    """
    Parse a unified diff into a list of hunks.
    
    Args:
        diff_text: The unified diff text
        
    Returns:
        List of parsed hunks with line numbers and changes
    """
    # Basic implementation - can be expanded as needed
    hunks = []
    current_hunk = None
    
    for line in diff_text.splitlines():
        if line.startswith('@@'):
            # New hunk
            if current_hunk:
                hunks.append(current_hunk)
            current_hunk = {
                'header': line,
                'lines': []
            }
        elif current_hunk:
            current_hunk['lines'].append(line)
            
    if current_hunk:
        hunks.append(current_hunk)
        
    return hunks 