#!/usr/bin/env python3
"""
Timing metrics test suite.

Tests wall-clock time measurement, CPU time accounting,
and performance metrics collection throughout the harness.
"""
import time
import subprocess
import tempfile
import shutil
import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
import sys

# Add parent directory to path to import harness modules
sys.path.insert(0, str(Path(__file__).parent.parent / "harness"))


class TestTimingMetrics:
    """Tests for timing and performance metrics."""
    
    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for testing."""
        temp_dir = tempfile.mkdtemp(prefix="timing_test_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_wall_clock_sleep_measurement(self):
        """Test that wall-clock time accurately measures sleep duration."""
        sleep_duration = 0.5  # 500ms
        
        start_time = time.time()
        time.sleep(sleep_duration)
        elapsed = time.time() - start_time
        
        # Should be close to sleep duration (within 100ms tolerance)
        assert abs(elapsed - sleep_duration) < 0.1, \
            f"Wall clock measurement off: {elapsed} vs {sleep_duration}"
    
    def test_cpu_time_vs_wall_time(self):
        """Test differentiation between CPU time and wall time."""
        # CPU-intensive work
        start_wall = time.time()
        start_cpu = time.process_time()
        
        # Do some CPU work
        result = 0
        for i in range(1000000):
            result += i ** 2
        
        cpu_elapsed = time.process_time() - start_cpu
        wall_elapsed = time.time() - start_wall
        
        # CPU time should be substantial
        assert cpu_elapsed > 0.01, "CPU time should register for intensive work"
        
        # Wall time should be >= CPU time
        assert wall_elapsed >= cpu_elapsed
        
        # Now test with sleep (no CPU usage)
        start_wall = time.time()
        start_cpu = time.process_time()
        
        time.sleep(0.2)
        
        cpu_elapsed_sleep = time.process_time() - start_cpu
        wall_elapsed_sleep = time.time() - start_wall
        
        # CPU time should be minimal during sleep
        assert cpu_elapsed_sleep < 0.01, "CPU time should be minimal during sleep"
        
        # Wall time should show the sleep duration
        assert wall_elapsed_sleep >= 0.19, "Wall time should show sleep duration"
    
    @patch('harness.entrypoint.ClaudeClient')
    def test_think_time_measurement(self, mock_claude_client, temp_workspace):
        """Test measurement of agent think time."""
        from entrypoint import Harness
        
        # Mock the Claude client
        mock_client = Mock()
        mock_claude_client.return_value = mock_client
        
        # Control the response delay
        def delayed_response(*args, **kwargs):
            time.sleep(0.3)  # Simulate 300ms think time
            return '<scratchpad>Thinking</scratchpad>\nACTION: {"message": "Done"}'
        
        mock_client.send_prompt.side_effect = delayed_response
        mock_client.count_tokens.return_value = 10
        
        # Would need to run harness and check logged think time
        # This is more of an integration test
    
    def test_action_execution_timing(self):
        """Test timing of individual action execution."""
        from patcher import apply_patch
        
        # Create a workspace
        workspace = tempfile.mkdtemp()
        try:
            # Create a file to patch
            test_file = Path(workspace) / "test.py"
            test_file.write_text("original")
            
            patch_content = """--- a/test.py
+++ b/test.py
@@ -1 +1 @@
-original
+modified
"""
            
            # Time the patch application
            start_time = time.time()
            success, error = apply_patch(workspace, patch_content)
            exec_time = time.time() - start_time
            
            assert success
            assert exec_time > 0
            assert exec_time < 1.0, "Patch application should be fast"
            
        finally:
            shutil.rmtree(workspace)
    
    def test_test_execution_timing(self, temp_workspace):
        """Test timing of pytest execution."""
        # Create a simple test file
        test_file = Path(temp_workspace) / "test_simple.py"
        test_file.write_text("""
def test_fast():
    assert 1 + 1 == 2

def test_slow():
    import time
    time.sleep(0.1)
    assert True
""")
        
        # Run pytest and measure time
        start_wall = time.time()
        start_cpu = time.process_time()
        
        result = subprocess.run(
            ["pytest", "-v", str(test_file)],
            capture_output=True,
            text=True
        )
        
        wall_time = time.time() - start_wall
        cpu_time = time.process_time() - start_cpu
        
        assert result.returncode == 0
        assert wall_time > 0.1  # At least the sleep duration
        assert cpu_time < wall_time  # CPU time less than wall time due to sleep
    
    def test_turn_metrics_aggregation(self):
        """Test aggregation of metrics across a turn."""
        # Simulate metrics for a turn
        turn_start = time.time()
        turn_cpu_start = time.process_time()
        
        # Simulate observation building (100ms)
        time.sleep(0.1)
        obs_time = 0.1
        
        # Simulate think time (300ms)
        time.sleep(0.3)
        think_time = 0.3
        
        # Simulate action execution (50ms)
        time.sleep(0.05)
        exec_time = 0.05
        
        # Calculate totals
        turn_wall_time = time.time() - turn_start
        turn_cpu_time = time.process_time() - turn_cpu_start
        
        # Verify timing adds up (with tolerance)
        expected_total = obs_time + think_time + exec_time
        assert abs(turn_wall_time - expected_total) < 0.05
        
        # CPU time should be minimal (mostly sleep)
        assert turn_cpu_time < 0.1
    
    def test_timeout_enforcement(self):
        """Test that timeout is properly enforced."""
        # This would test the 30-minute timeout in the harness
        timeout_seconds = 2  # Use short timeout for testing
        
        start_time = time.time()
        
        # Simulate work loop
        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                break
            time.sleep(0.1)
        
        final_elapsed = time.time() - start_time
        assert final_elapsed >= timeout_seconds
        assert final_elapsed < timeout_seconds + 0.2  # Should exit promptly
    
    def test_high_precision_timing(self):
        """Test timing precision for sub-second operations."""
        # Test multiple small operations
        timings = []
        
        for _ in range(10):
            start = time.time()
            # Small operation
            _ = sum(range(10000))
            elapsed = time.time() - start
            timings.append(elapsed)
        
        # All timings should be positive
        assert all(t > 0 for t in timings)
        
        # Should have microsecond precision
        assert any(t < 0.001 for t in timings), "Should capture sub-millisecond operations"
    
    def test_git_operation_timing(self, temp_workspace):
        """Test timing of git operations."""
        # Initialize git
        subprocess.run(["git", "init"], cwd=temp_workspace)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=temp_workspace)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=temp_workspace)
        
        # Create and time initial commit
        test_file = Path(temp_workspace) / "test.txt"
        test_file.write_text("content")
        
        start_time = time.time()
        subprocess.run(["git", "add", "-A"], cwd=temp_workspace)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=temp_workspace)
        git_time = time.time() - start_time
        
        assert git_time > 0
        assert git_time < 1.0, "Git operations should be reasonably fast"
    
    def test_metrics_json_serialization(self):
        """Test that timing metrics can be properly serialized to JSON."""
        metrics = {
            "turn": 1,
            "wall_time": 1.234567,
            "cpu_time": 0.567890,
            "think_time": 0.789012,
            "observation_build_time": 0.012345,
            "action_execution_time": 0.045678,
            "test_wall_time": 2.345678,
            "test_cpu_time": 1.234567,
            "timestamp": time.time()
        }
        
        # Should serialize without issues
        json_str = json.dumps(metrics)
        assert json_str
        
        # Should deserialize correctly
        loaded = json.loads(json_str)
        assert loaded["wall_time"] == 1.234567
        assert loaded["cpu_time"] == 0.567890
    
    def test_cumulative_metrics(self):
        """Test tracking of cumulative metrics across turns."""
        total_wall_time = 0
        total_cpu_time = 0
        
        for turn in range(3):
            turn_start_wall = time.time()
            turn_start_cpu = time.process_time()
            
            # Simulate turn work
            time.sleep(0.1)
            for i in range(100000):
                _ = i ** 2
            
            turn_wall = time.time() - turn_start_wall
            turn_cpu = time.process_time() - turn_start_cpu
            
            total_wall_time += turn_wall
            total_cpu_time += turn_cpu
        
        # Totals should be sum of turns
        assert total_wall_time > 0.3  # At least 3 * 0.1 sleep
        assert total_cpu_time > 0.01  # Some CPU work done
        assert total_cpu_time < total_wall_time
    
    def test_parallel_operation_timing(self):
        """Test timing when operations could be parallel."""
        import concurrent.futures
        
        def cpu_task(n):
            start = time.time()
            result = sum(i ** 2 for i in range(n))
            return time.time() - start
        
        # Sequential timing
        seq_start = time.time()
        seq_times = [cpu_task(100000) for _ in range(3)]
        seq_total = time.time() - seq_start
        
        # Parallel timing (if supported)
        par_start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            par_times = list(executor.map(cpu_task, [100000] * 3))
        par_total = time.time() - par_start
        
        # Both should complete
        assert len(seq_times) == 3
        assert len(par_times) == 3
        
        # Sequential should take roughly sum of individual times
        assert seq_total >= sum(seq_times) * 0.9 