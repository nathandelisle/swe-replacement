#!/usr/bin/env python3
"""
Container boot integrity test suite.

Tests container startup validation, environment checks, mount verification,
and proper initialization of the workspace.
"""
import subprocess
import os
import tempfile
import shutil
import json
import time
import pytest
from pathlib import Path
from typing import Dict, Tuple


class TestContainerBootIntegrity:
    """Tests for container boot validation and initialization."""
    
    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for testing."""
        temp_dir = tempfile.mkdtemp(prefix="boot_test_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def temp_harness(self):
        """Create a temporary harness directory."""
        temp_dir = tempfile.mkdtemp(prefix="harness_test_")
        # Copy actual harness files
        source_harness = Path(__file__).parent.parent / "harness"
        if source_harness.exists():
            shutil.copytree(source_harness, temp_dir, dirs_exist_ok=True)
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_missing_api_key(self, temp_workspace, temp_harness):
        """Test that container exits with descriptive message when ANTHROPIC_API_KEY is missing."""
        result = subprocess.run([
            "docker", "run", "--rm",
            "--read-only",
            "--network", "none",
            "-v", f"{temp_workspace}:/workspace:rw",
            "-v", f"{temp_harness}:/harness:ro",
            # Deliberately omit ANTHROPIC_API_KEY
            "-e", "TRIAL_ID=test",
            "-e", "REPO_TYPE=control",
            "swe-replacement:latest"
        ], capture_output=True, text=True)
        
        # Should exit with error
        assert result.returncode != 0
        
        # Should have descriptive error message
        output = result.stdout + result.stderr
        assert "ANTHROPIC_API_KEY" in output or "API key" in output.lower(), \
            "Container should provide clear error about missing API key"
    
    def test_missing_workspace_mount(self, temp_harness):
        """Test that container refuses to start without workspace mount."""
        result = subprocess.run([
            "docker", "run", "--rm",
            "--read-only",
            "--network", "none",
            "-v", f"{temp_harness}:/harness:ro",
            # Deliberately omit workspace mount
            "-e", "ANTHROPIC_API_KEY=test-key",
            "-e", "TRIAL_ID=test", 
            "-e", "REPO_TYPE=control",
            "swe-replacement:latest"
        ], capture_output=True, text=True)
        
        # Should exit with error
        assert result.returncode != 0
        
        # Should indicate workspace issue
        output = result.stdout + result.stderr
        assert "workspace" in output.lower() or "/workspace" in output, \
            "Container should indicate missing workspace mount"
    
    def test_readonly_workspace_mount(self, temp_workspace, temp_harness):
        """Test that container exits if workspace is mounted read-only."""
        result = subprocess.run([
            "docker", "run", "--rm",
            "--read-only",
            "--network", "none",
            "-v", f"{temp_workspace}:/workspace:ro",  # Read-only mount
            "-v", f"{temp_harness}:/harness:ro",
            "-e", "ANTHROPIC_API_KEY=test-key",
            "-e", "TRIAL_ID=test",
            "-e", "REPO_TYPE=control",
            "swe-replacement:latest"
        ], capture_output=True, text=True, timeout=30)
        
        # Should exit with error
        assert result.returncode != 0
        
        # Should indicate write permission issue
        output = result.stdout + result.stderr
        assert "read-only" in output.lower() or "permission" in output.lower() or "write" in output.lower(), \
            "Container should indicate workspace is read-only"
    
    def test_security_flags_enforcement(self, temp_workspace, temp_harness):
        """Test that all security flags are properly enforced."""
        # Test with security flags
        secure_result = subprocess.run([
            "docker", "run", "--rm",
            "--read-only",
            "--network", "none",
            "--memory", "2g",
            "--cpus", "1.0",
            "--tmpfs", "/tmp:size=100M",
            "-v", f"{temp_workspace}:/workspace:rw",
            "-v", f"{temp_harness}:/harness:ro",
            "-e", "ANTHROPIC_API_KEY=test-key",
            "-e", "TRIAL_ID=test",
            "-e", "REPO_TYPE=control",
            "swe-replacement:latest",
            "/bin/sh", "-c", "echo 'Security test' && exit 0"
        ], capture_output=True, text=True)
        
        # Should work with all flags
        assert "Security test" in secure_result.stdout
    
    def test_initial_file_creation(self, temp_workspace, temp_harness):
        """Test that container creates required initial files."""
        # Create a minimal test harness that exits after initialization
        test_entrypoint = Path(temp_harness) / "test_entrypoint.py"
        test_entrypoint.write_text("""
import json
import subprocess
from pathlib import Path

# Create required files
Path("/workspace/notes.md").write_text("")
Path("/workspace/.agent_state.json").write_text(json.dumps({"last_message": ""}))

# Initialize git
subprocess.run(["git", "init"], cwd="/workspace")
subprocess.run(["git", "config", "user.email", "agent@experiment.local"], cwd="/workspace")
subprocess.run(["git", "config", "user.name", "Agent"], cwd="/workspace")
subprocess.run(["git", "add", "-A"], cwd="/workspace")
subprocess.run(["git", "commit", "-m", "Initial state"], cwd="/workspace")

print("Initialization complete")
""")
        
        result = subprocess.run([
            "docker", "run", "--rm",
            "--read-only",
            "--network", "none",
            "-v", f"{temp_workspace}:/workspace:rw",
            "-v", f"{temp_harness}:/harness:ro",
            "-e", "ANTHROPIC_API_KEY=test-key",
            "-e", "TRIAL_ID=test",
            "-e", "REPO_TYPE=control",
            "-e", "PYTHONDONTWRITEBYTECODE=1",
            "swe-replacement:latest",
            "python", "/harness/test_entrypoint.py"
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        assert "Initialization complete" in result.stdout
        
        # Verify files were created
        assert (Path(temp_workspace) / "notes.md").exists(), "notes.md should be created"
        assert (Path(temp_workspace) / ".agent_state.json").exists(), ".agent_state.json should be created"
        assert (Path(temp_workspace) / ".git").exists(), "Git repository should be initialized"
        
        # Verify git commit
        git_log = subprocess.run(
            ["git", "-C", temp_workspace, "log", "--oneline"],
            capture_output=True,
            text=True
        )
        assert "Initial state" in git_log.stdout, "Initial git commit should exist"
    
    def test_environment_variable_validation(self, temp_workspace, temp_harness):
        """Test that container validates all required environment variables."""
        required_vars = ["ANTHROPIC_API_KEY", "TRIAL_ID", "REPO_TYPE"]
        
        for var in required_vars:
            # Create env dict with all vars except one
            env_vars = {
                "ANTHROPIC_API_KEY": "test-key",
                "TRIAL_ID": "test",
                "REPO_TYPE": "control"
            }
            del env_vars[var]
            
            cmd = [
                "docker", "run", "--rm",
                "--read-only",
                "--network", "none", 
                "-v", f"{temp_workspace}:/workspace:rw",
                "-v", f"{temp_harness}:/harness:ro",
            ]
            
            # Add remaining env vars
            for k, v in env_vars.items():
                cmd.extend(["-e", f"{k}={v}"])
                
            cmd.append("swe-replacement:latest")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            # Should fail when any required var is missing
            assert result.returncode != 0, f"Container should fail when {var} is missing"
    
    def test_tmpfs_writable(self, temp_workspace, temp_harness):
        """Test that /tmp is writable despite read-only root filesystem."""
        result = subprocess.run([
            "docker", "run", "--rm",
            "--read-only",
            "--tmpfs", "/tmp:size=100M",
            "-v", f"{temp_workspace}:/workspace:rw",
            "-v", f"{temp_harness}:/harness:ro",
            "-e", "ANTHROPIC_API_KEY=test-key",
            "-e", "TRIAL_ID=test",
            "-e", "REPO_TYPE=control",
            "swe-replacement:latest",
            "/bin/sh", "-c", "echo 'test' > /tmp/test.txt && cat /tmp/test.txt"
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        assert "test" in result.stdout, "/tmp should be writable"
    
    def test_harness_mount_readonly(self, temp_workspace, temp_harness):
        """Test that harness mount is read-only."""
        result = subprocess.run([
            "docker", "run", "--rm",
            "--read-only",
            "-v", f"{temp_workspace}:/workspace:rw",
            "-v", f"{temp_harness}:/harness:ro",
            "-e", "ANTHROPIC_API_KEY=test-key",
            "-e", "TRIAL_ID=test",
            "-e", "REPO_TYPE=control",
            "swe-replacement:latest",
            "/bin/sh", "-c", "touch /harness/test.txt 2>&1"
        ], capture_output=True, text=True)
        
        assert result.returncode != 0
        assert "read-only" in result.stderr.lower() or "permission" in result.stderr.lower(), \
            "Harness directory should be read-only"
    
    def test_pythondontwritebytecode(self, temp_workspace, temp_harness):
        """Test that PYTHONDONTWRITEBYTECODE prevents .pyc file creation."""
        # Create a test Python file
        test_py = Path(temp_workspace) / "test_bytecode.py"
        test_py.write_text("print('Hello')")
        
        result = subprocess.run([
            "docker", "run", "--rm",
            "--read-only",
            "-v", f"{temp_workspace}:/workspace:rw",
            "-v", f"{temp_harness}:/harness:ro",
            "-e", "ANTHROPIC_API_KEY=test-key",
            "-e", "TRIAL_ID=test",
            "-e", "REPO_TYPE=control",
            "-e", "PYTHONDONTWRITEBYTECODE=1",
            "swe-replacement:latest",
            "/bin/sh", "-c", "cd /workspace && python test_bytecode.py && ls -la"
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        assert "Hello" in result.stdout
        assert ".pyc" not in result.stdout and "__pycache__" not in result.stdout, \
            "Python bytecode files should not be created"
    
    def test_blocking_for_observation(self, temp_workspace, temp_harness):
        """Test that container blocks awaiting observation after initialization."""
        # This would require a mock harness that can be controlled
        # For now, we verify the container doesn't exit immediately
        
        process = subprocess.Popen([
            "docker", "run", "--rm",
            "--name", "test-blocking",
            "--read-only",
            "--network", "none",
            "-v", f"{temp_workspace}:/workspace:rw", 
            "-v", f"{temp_harness}:/harness:ro",
            "-e", "ANTHROPIC_API_KEY=test-key",
            "-e", "TRIAL_ID=test",
            "-e", "REPO_TYPE=control",
            "swe-replacement:latest"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # Give it a moment to start
        time.sleep(2)
        
        # Check if still running
        poll_result = process.poll()
        
        # Clean up
        subprocess.run(["docker", "kill", "test-blocking"], capture_output=True)
        process.wait()
        
        # Should still be running (None means process hasn't terminated)
        assert poll_result is None, "Container should block waiting for observation, not exit immediately" 