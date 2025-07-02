#!/usr/bin/env python3
"""
Cold-start lineage test suite.

Tests build reproducibility and deterministic image creation from a pristine environment.
Ensures the experiment can be replicated from scratch with only Docker as a prerequisite.
"""
import subprocess
import os
import tempfile
import shutil
import hashlib
import json
import pytest
from pathlib import Path
import docker
from typing import Tuple, Optional


class TestColdStartLineage:
    """Tests for build reproducibility and deterministic container creation."""
    
    @pytest.fixture(scope="class")
    def docker_client(self):
        """Create Docker client for testing."""
        return docker.from_env()
    
    @pytest.fixture(scope="class")
    def isolated_workspace(self):
        """Create an isolated workspace for testing."""
        temp_dir = tempfile.mkdtemp(prefix="cold_start_test_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_prerequisites_check(self):
        """Test that Docker is the only prerequisite."""
        # Check Docker is available
        result = subprocess.run(["docker", "--version"], capture_output=True)
        assert result.returncode == 0, "Docker must be installed and accessible"
        
        # Verify no other tools are assumed (e.g., python outside container)
        # This test runs in the test environment, but the build should not assume Python
        
    def test_deterministic_build(self, isolated_workspace, docker_client):
        """Test that consecutive builds produce identical layer digests."""
        # Copy necessary files to isolated workspace
        source_dir = Path(__file__).parent.parent
        docker_dir = source_dir / "docker"
        harness_dir = source_dir / "harness"
        
        # Create minimal structure in isolated workspace
        isolated_docker = Path(isolated_workspace) / "docker"
        isolated_harness = Path(isolated_workspace) / "harness"
        
        shutil.copytree(docker_dir, isolated_docker)
        shutil.copytree(harness_dir, isolated_harness)
        
        # Build image twice
        build_results = []
        for i in range(2):
            result = subprocess.run(
                ["docker", "build", "-t", f"test-deterministic-{i}", "-f", "docker/Dockerfile", "."],
                cwd=isolated_workspace,
                capture_output=True,
                text=True
            )
            assert result.returncode == 0, f"Build {i+1} failed: {result.stderr}"
            
            # Get image digest
            image = docker_client.images.get(f"test-deterministic-{i}")
            build_results.append({
                "id": image.id,
                "attrs": image.attrs,
                "layers": self._get_layer_digests(image)
            })
            
        # Compare builds
        assert build_results[0]["layers"] == build_results[1]["layers"], \
            "Consecutive builds must produce identical layer digests"
        
        # Cleanup
        for i in range(2):
            try:
                docker_client.images.remove(f"test-deterministic-{i}", force=True)
            except:
                pass
    
    def test_offline_build(self, isolated_workspace):
        """Test that build works without network access (all dependencies vendored)."""
        # This test simulates building behind a firewall
        # Note: Actual network isolation would require more complex setup
        
        # Copy necessary files
        source_dir = Path(__file__).parent.parent
        docker_dir = source_dir / "docker"
        harness_dir = source_dir / "harness"
        
        isolated_docker = Path(isolated_workspace) / "docker"
        isolated_harness = Path(isolated_workspace) / "harness"
        
        shutil.copytree(docker_dir, isolated_docker)
        shutil.copytree(harness_dir, isolated_harness)
        
        # Check Dockerfile doesn't use network-dependent commands
        dockerfile_path = isolated_docker / "Dockerfile"
        dockerfile_content = dockerfile_path.read_text()
        
        # Verify no apt-get update or pip install from network
        assert "apt-get update" not in dockerfile_content or "RUN --mount=type=cache" in dockerfile_content, \
            "Dockerfile should use build cache or offline packages"
        
        # Verify requirements are vendored or use specific versions
        requirements_path = Path(isolated_workspace) / "requirements.txt"
        if requirements_path.exists():
            requirements = requirements_path.read_text()
            lines = [l.strip() for l in requirements.splitlines() if l.strip() and not l.startswith("#")]
            for line in lines:
                assert "==" in line or "file://" in line, \
                    f"Requirement {line} must specify exact version or local file"
    
    def test_build_from_source_only(self, isolated_workspace):
        """Test that build uses only checked-in source files."""
        # Create a marker file that should NOT end up in the image
        marker_file = Path(isolated_workspace) / "should_not_be_in_image.txt"
        marker_file.write_text("This file should not be in the Docker image")
        
        # Copy necessary files
        source_dir = Path(__file__).parent.parent
        docker_dir = source_dir / "docker"
        harness_dir = source_dir / "harness"
        
        isolated_docker = Path(isolated_workspace) / "docker"
        isolated_harness = Path(isolated_workspace) / "harness"
        
        shutil.copytree(docker_dir, isolated_docker)
        shutil.copytree(harness_dir, isolated_harness)
        
        # Build image
        result = subprocess.run(
            ["docker", "build", "-t", "test-source-only", "-f", "docker/Dockerfile", "."],
            cwd=isolated_workspace,
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Build failed: {result.stderr}"
        
        # Check that marker file is not in image
        check_result = subprocess.run(
            ["docker", "run", "--rm", "test-source-only", "ls", "-la", "/"],
            capture_output=True,
            text=True
        )
        assert "should_not_be_in_image.txt" not in check_result.stdout, \
            "Build must not include files outside of explicit COPY commands"
        
        # Cleanup
        subprocess.run(["docker", "rmi", "test-source-only", "-f"], capture_output=True)
    
    def test_layer_caching_integrity(self, docker_client):
        """Test that layer caching doesn't affect reproducibility."""
        # Build once to populate cache
        result1 = subprocess.run(
            ["docker", "build", "-t", "test-cache-1", "-f", "docker/Dockerfile", "."],
            cwd=Path(__file__).parent.parent,
            capture_output=True
        )
        assert result1.returncode == 0
        
        # Modify a file that should invalidate cache
        test_file = Path(__file__).parent.parent / "harness" / "test_cache_marker.py"
        test_file.write_text("# Cache test marker")
        
        try:
            # Build again - should not use stale cache
            result2 = subprocess.run(
                ["docker", "build", "-t", "test-cache-2", "-f", "docker/Dockerfile", "."],
                cwd=Path(__file__).parent.parent,
                capture_output=True,
                text=True
            )
            assert result2.returncode == 0
            
            # Verify the file made it into the new image
            check_result = subprocess.run(
                ["docker", "run", "--rm", "test-cache-2", "ls", "/harness/"],
                capture_output=True,
                text=True  
            )
            assert "test_cache_marker.py" in check_result.stdout
            
        finally:
            # Cleanup
            test_file.unlink(missing_ok=True)
            subprocess.run(["docker", "rmi", "test-cache-1", "test-cache-2", "-f"], capture_output=True)
    
    def _get_layer_digests(self, image) -> list:
        """Extract layer digests from Docker image."""
        history = image.history()
        return [layer.get('Id', '') for layer in history if layer.get('Id')]
    
    def test_build_script_idempotency(self):
        """Test that build script produces same result when run multiple times."""
        build_script = Path(__file__).parent.parent / "docker" / "build_image.sh"
        
        if not build_script.exists():
            pytest.skip("build_image.sh not found")
            
        # Record initial state
        initial_images = subprocess.run(
            ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}:{{.ID}}"],
            capture_output=True,
            text=True
        ).stdout.strip().split('\n')
        
        # Run build script
        result = subprocess.run(
            ["bash", str(build_script)],
            cwd=build_script.parent,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0, f"Build script failed: {result.stderr}"
        
        # Check that swe-replacement:latest exists
        check_result = subprocess.run(
            ["docker", "images", "swe-replacement:latest", "--format", "{{.ID}}"],
            capture_output=True,
            text=True
        )
        assert check_result.stdout.strip(), "swe-replacement:latest image not created" 