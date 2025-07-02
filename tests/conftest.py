"""
Pytest configuration for SWE replacement experiment tests.

Provides shared fixtures and test configuration.
"""
import os
import sys
import pytest
import tempfile
import shutil
from pathlib import Path

# Add parent directories to Python path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "harness"))
sys.path.insert(0, str(project_root / "orchestrator"))


@pytest.fixture(scope="session")
def docker_available():
    """Check if Docker is available for tests."""
    import subprocess
    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except:
        return False


@pytest.fixture(scope="session")
def test_image_built(docker_available):
    """Ensure test Docker image is built."""
    if not docker_available:
        pytest.skip("Docker not available")
    
    import subprocess
    # Check if swe-replacement:latest exists
    result = subprocess.run(
        ["docker", "images", "-q", "swe-replacement:latest"],
        capture_output=True,
        text=True
    )
    
    if not result.stdout.strip():
        pytest.skip("swe-replacement:latest image not built. Run docker/build_image.sh first")
    
    return True


@pytest.fixture
def isolated_temp_dir():
    """Create an isolated temporary directory for tests."""
    temp_dir = tempfile.mkdtemp(prefix="swe_test_")
    original_cwd = os.getcwd()
    
    yield temp_dir
    
    # Cleanup
    os.chdir(original_cwd)
    try:
        shutil.rmtree(temp_dir)
    except:
        pass  # Best effort cleanup


@pytest.fixture
def mock_harness_environment(isolated_temp_dir):
    """Set up a mock harness environment."""
    # Create required directories
    workspace = Path(isolated_temp_dir) / "workspace"
    harness = Path(isolated_temp_dir) / "harness"
    results = Path(isolated_temp_dir) / "results"
    
    workspace.mkdir()
    harness.mkdir()
    results.mkdir()
    
    # Copy harness files if they exist
    source_harness = Path(__file__).parent.parent / "harness"
    if source_harness.exists():
        for item in source_harness.iterdir():
            if item.suffix == ".py":
                shutil.copy2(item, harness)
    
    return {
        "workspace": workspace,
        "harness": harness,
        "results": results,
        "root": isolated_temp_dir
    }


@pytest.fixture
def git_repo(isolated_temp_dir):
    """Create a git repository for testing."""
    import subprocess
    
    repo_path = Path(isolated_temp_dir) / "repo"
    repo_path.mkdir()
    
    # Initialize git
    subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        capture_output=True
    )
    
    # Create initial commit
    (repo_path / "README.md").write_text("# Test Repository")
    subprocess.run(["git", "add", "-A"], cwd=repo_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        capture_output=True
    )
    
    return repo_path


# Configure pytest options
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (may be slow)"
    )
    config.addinivalue_line(
        "markers", "requires_docker: marks tests that require Docker"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow running"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on test names."""
    for item in items:
        # Add markers based on test names or locations
        if "docker" in item.nodeid.lower():
            item.add_marker(pytest.mark.requires_docker)
        
        if "end_to_end" in item.nodeid:
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.slow)
        
        if any(keyword in item.nodeid for keyword in ["concurrent", "batch", "orchestrator"]):
            item.add_marker(pytest.mark.integration)


# Test environment validation
@pytest.fixture(scope="session", autouse=True)
def validate_test_environment():
    """Validate that the test environment is properly set up."""
    import subprocess
    
    # Check Python version
    assert sys.version_info >= (3, 8), "Python 3.8+ required for tests"
    
    # Check required commands
    required_commands = ["git", "pytest"]
    missing_commands = []
    
    for cmd in required_commands:
        try:
            subprocess.run([cmd, "--version"], capture_output=True, check=True)
        except:
            missing_commands.append(cmd)
    
    if missing_commands:
        pytest.skip(f"Missing required commands: {', '.join(missing_commands)}") 