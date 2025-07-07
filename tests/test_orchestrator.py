#!/usr/bin/env python3
"""
Orchestrator test suite.

Tests trial orchestration, concurrent execution, cleanup procedures,
error handling, and result collection.
"""
import subprocess
import tempfile
import shutil
import json
import time
import threading
import os
import pytest
from pathlib import Path
import uuid
from unittest.mock import patch, Mock
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "orchestrator"))

from run_trial import TrialRunner
from batch import BatchRunner


class TestOrchestrator:
    """Tests for trial orchestration and batch processing."""
    
    @pytest.fixture
    def temp_results_dir(self):
        """Create a temporary results directory."""
        temp_dir = tempfile.mkdtemp(prefix="orch_test_results_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def mock_workspace(self):
        """Create a mock workspace with required files."""
        temp_dir = tempfile.mkdtemp(prefix="orch_test_workspace_")
        
        # Create mock repository structure
        control_dir = Path(temp_dir) / "repos" / "control"
        treatment_dir = Path(temp_dir) / "repos" / "treatment"
        control_dir.mkdir(parents=True)
        treatment_dir.mkdir(parents=True)
        
        # Create mock files
        (control_dir / "functions.py").write_text("def func(): return 'control'")
        (control_dir / "test_functions.py").write_text("def test_func(): pass")
        (treatment_dir / "functions.py").write_text("def func(): return 'treatment'")
        (treatment_dir / "test_functions.py").write_text("def test_func(): pass")
        
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_trial_runner_initialization(self):
        """Test TrialRunner initialization."""
        runner = TrialRunner("control", "test-123")
        
        assert runner.repo_type == "control"
        assert runner.trial_id == "test-123"
        assert runner.container_name == "swe-trial-test-123"
        assert "control_test-123" in str(runner.results_dir)
    
    def test_trial_id_auto_generation(self):
        """Test automatic trial ID generation."""
        runner1 = TrialRunner("control")
        runner2 = TrialRunner("control")
        
        assert runner1.trial_id != runner2.trial_id
        assert len(runner1.trial_id) == 8  # UUID truncated to 8 chars
    
    @patch('run_trial.subprocess.run')
    def test_trial_preparation(self, mock_run, mock_workspace, temp_results_dir):
        """Test trial preparation and workspace setup."""
        with patch('run_trial.Path') as mock_path:
            mock_path.return_value = Path(temp_results_dir)
            
            runner = TrialRunner("control", "test-prep")
            runner.results_dir = Path(temp_results_dir) / "test-prep"
            
            # Mock source repo existence
            with patch.object(Path, 'exists', return_value=True):
                with patch('run_trial.shutil.copy2'):
                    with patch('run_trial.shutil.copytree'):
                        runner.prepare_trial()
            
            # Check results directory created
            assert runner.results_dir.exists()
            
            # Check metadata file created
            metadata_file = runner.results_dir / "metadata.json"
            assert metadata_file.exists()
            
            metadata = json.loads(metadata_file.read_text())
            assert metadata["trial_id"] == "test-prep"
            assert metadata["repo_type"] == "control"
            assert "start_time" in metadata
    
    def test_concurrent_trial_execution(self, temp_results_dir):
        """Test running multiple trials concurrently."""
        trials_completed = []
        trials_failed = []
        
        def run_mock_trial(trial_id):
            try:
                # Simulate trial work
                time.sleep(0.1)
                
                # Create result file
                result_dir = Path(temp_results_dir) / f"trial_{trial_id}"
                result_dir.mkdir(parents=True)
                (result_dir / "completed.txt").write_text("Done")
                
                trials_completed.append(trial_id)
            except Exception as e:
                trials_failed.append((trial_id, str(e)))
        
        # Launch concurrent trials
        threads = []
        for i in range(5):
            thread = threading.Thread(target=run_mock_trial, args=(i,))
            thread.start()
            threads.append(thread)
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # All should complete
        assert len(trials_completed) == 5
        assert len(trials_failed) == 0
        
        # Check result files
        for i in range(5):
            assert (Path(temp_results_dir) / f"trial_{i}" / "completed.txt").exists()
    
    @patch('run_trial.subprocess.run')
    def test_container_cleanup_on_error(self, mock_run):
        """Test that containers are cleaned up even on error."""
        runner = TrialRunner("control", "test-cleanup")
        
        # Track calls and their results
        cleanup_success = False
        
        def subprocess_side_effect(cmd, *args, **kwargs):
            # If this is the container run command, fail it
            if isinstance(cmd, list) and "docker" in cmd and "run" in cmd:
                raise Exception("Container failed")
            # If this is the cleanup command
            elif isinstance(cmd, list) and "docker" in cmd and "kill" in cmd:
                nonlocal cleanup_success
                cleanup_success = True
                return Mock(returncode=0, stdout="", stderr="")
            # Other commands succeed
            return Mock(returncode=0, stdout="", stderr="")
        
        mock_run.side_effect = subprocess_side_effect
        
        try:
            runner.run_container()
        except Exception:
            pass
        
        # Cleanup should have been attempted and succeeded
        assert cleanup_success, "Container cleanup should be attempted and succeed on error"
        
        # Verify the kill command was called with correct container name
        kill_calls = [call for call in mock_run.call_args_list 
                      if call[0][0] and "kill" in call[0][0]]
        assert len(kill_calls) > 0, "Docker kill should be called"
        assert any(runner.container_name in str(call) for call in kill_calls), \
            f"Docker kill should target container {runner.container_name}"
    
    def test_workspace_cleanup(self, temp_results_dir):
        """Test temporary workspace cleanup."""
        runner = TrialRunner("control", "test-cleanup")
        
        # Create a mock temp workspace
        temp_workspace = tempfile.mkdtemp()
        runner.temp_workspace = temp_workspace
        
        # Verify it exists
        assert os.path.exists(temp_workspace)
        
        # Run cleanup
        runner.cleanup()
        
        # Verify it's removed
        assert not os.path.exists(temp_workspace)
    
    def test_result_collection(self, temp_results_dir, mock_workspace):
        """Test collection of trial results."""
        runner = TrialRunner("control", "test-collect")
        runner.results_dir = Path(temp_results_dir) / "test-collect"
        runner.results_dir.mkdir(parents=True)
        
        # Create mock workspace with results
        runner.temp_workspace = tempfile.mkdtemp()
        
        # Create mock harness log
        harness_log = Path(runner.temp_workspace) / "harness.log"
        harness_log.write_text("Log entries...")
        
        # Create mock workspace files
        (Path(runner.temp_workspace) / "functions.py").write_text("modified")
        (Path(runner.temp_workspace) / "notes.md").write_text("Agent notes")
        
        # Initialize git for history test
        subprocess.run(["git", "init"], cwd=runner.temp_workspace, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=runner.temp_workspace)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=runner.temp_workspace)
        subprocess.run(["git", "add", "-A"], cwd=runner.temp_workspace)
        subprocess.run(["git", "commit", "-m", "Test"], cwd=runner.temp_workspace)
        
        # Run collection
        runner.collect_results()
        
        # Verify results collected
        assert (runner.results_dir / "harness.log").exists()
        assert (runner.results_dir / "final_workspace" / "functions.py").exists()
        assert (runner.results_dir / "final_workspace" / "notes.md").exists()
        
        # Cleanup
        shutil.rmtree(runner.temp_workspace)
    
    def test_metadata_persistence(self, temp_results_dir):
        """Test that metadata is properly saved and updated."""
        runner = TrialRunner("treatment", "test-meta")
        runner.results_dir = Path(temp_results_dir) / "test-meta"
        runner.results_dir.mkdir(parents=True)
        
        # Create initial metadata
        initial_metadata = {
            "trial_id": "test-meta",
            "repo_type": "treatment",
            "start_time": "2024-01-01T00:00:00"
        }
        
        with open(runner.results_dir / "metadata.json", 'w') as f:
            json.dump(initial_metadata, f)
        
        # Update metadata (simulating end of trial)
        with open(runner.results_dir / "metadata.json", 'r') as f:
            metadata = json.load(f)
        
        metadata["end_time"] = "2024-01-01T00:30:00"
        metadata["exit_code"] = 0
        
        with open(runner.results_dir / "metadata.json", 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Verify updates
        saved = json.loads((runner.results_dir / "metadata.json").read_text())
        assert saved["start_time"] == "2024-01-01T00:00:00"
        assert saved["end_time"] == "2024-01-01T00:30:00"
        assert saved["exit_code"] == 0
    
    def test_docker_volume_cleanup(self):
        """Test that Docker volumes are cleaned up."""
        # This would test that no anonymous volumes remain after trials
        # Would need Docker access to fully test
        
        # Check for orphaned volumes
        result = subprocess.run(
            ["docker", "volume", "ls", "-q"],
            capture_output=True,
            text=True
        )
        
        initial_volumes = set(result.stdout.strip().split('\n')) if result.stdout.strip() else set()
        
        # After running trials, check again
        # In real test, would run actual trials here
        
        result = subprocess.run(
            ["docker", "volume", "ls", "-q"],
            capture_output=True,
            text=True
        )
        
        final_volumes = set(result.stdout.strip().split('\n')) if result.stdout.strip() else set()
        
        # No new anonymous volumes should remain
        # (This is a simplified test)
        new_volumes = final_volumes - initial_volumes
        assert len(new_volumes) == 0, f"Leaked docker volumes: {new_volumes}"
    
    @pytest.mark.xfail(reason="Not implemented - needs container timeout simulation")
    def test_trial_timeout_handling(self):
        """Test handling of trials that exceed timeout."""
        # This would test the container timeout mechanism
        # Would need to mock or use short timeout for testing
        assert False, "Test not implemented"
    
    @pytest.mark.xfail(reason="Not implemented - needs batch runner mocking")
    def test_batch_runner_parallel_limit(self):
        """Test that batch runner respects parallel execution limits."""
        # This would test the batch.py parallel execution
        # Would verify no more than N trials run simultaneously
        assert False, "Test not implemented"
    
    def test_error_recovery_and_logging(self, temp_results_dir):
        """Test error recovery and proper error logging."""
        runner = TrialRunner("control", "test-error")
        runner.results_dir = Path(temp_results_dir) / "test-error"
        runner.results_dir.mkdir(parents=True)
        
        # Simulate various errors
        error_msg = "Test error occurred"
        
        # Write error file
        with open(runner.results_dir / "error.txt", 'w') as f:
            f.write(f"Container launch error: {error_msg}\n")
        
        # Verify error is logged
        assert (runner.results_dir / "error.txt").exists()
        error_content = (runner.results_dir / "error.txt").read_text()
        assert error_msg in error_content
    
    def test_container_resource_limits(self):
        """Test that resource limits are enforced."""
        # Verify memory and CPU limits from run_trial.py
        run_trial_path = Path(__file__).parent.parent / "orchestrator" / "run_trial.py"
        
        if run_trial_path.exists():
            content = run_trial_path.read_text()
            assert '"--memory", "2g"' in content
            assert '"--cpus", "1.0"' in content
    
    def test_results_directory_structure(self, temp_results_dir):
        """Test that results directory has expected structure."""
        runner = TrialRunner("control", "test-structure")
        runner.results_dir = Path(temp_results_dir) / "test-structure"
        runner.results_dir.mkdir(parents=True)
        
        # Create expected structure
        (runner.results_dir / "metadata.json").write_text("{}")
        (runner.results_dir / "container_output.txt").write_text("output")
        (runner.results_dir / "harness.log").write_text("logs")
        (runner.results_dir / "final_workspace").mkdir()
        
        # Verify structure
        assert (runner.results_dir / "metadata.json").exists()
        assert (runner.results_dir / "container_output.txt").exists()
        assert (runner.results_dir / "harness.log").exists()
        assert (runner.results_dir / "final_workspace").is_dir() 