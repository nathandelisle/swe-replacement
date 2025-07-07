"""Integration tests for harness metric logging.

This module tests that the harness correctly logs all required metrics during
a simulated agent interaction, using a mock ClaudeClient with scripted responses.
"""
import json
import os
import sys
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Any
import subprocess
import time
from unittest.mock import Mock, patch

# Add harness to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'harness'))

from harness.entrypoint import Harness
from harness.claude_client import ClaudeClient


class MockClaudeClient(ClaudeClient):
    """Mock client that returns pre-scripted responses."""
    
    def __init__(self, responses: List[str]):
        self.responses = responses
        self.response_index = 0
        
    def send_prompt(self, prompt: str, system_prompt: str) -> str:
        if self.response_index < len(self.responses):
            response = self.responses[self.response_index]
            self.response_index += 1
            return response
        return '<scratchpad>No more responses</scratchpad>\nACTION: {"message": "Done"}'
        
    def count_tokens(self, text: str) -> int:
        return len(text.split())
        
    def format_observation_prompt(self, observation: Dict[str, Any]) -> str:
        return json.dumps(observation)
        
    def get_system_prompt(self) -> str:
        return "Test system prompt"


def setup_test_workspace(workspace_dir: Path):
    """Create a test workspace with Python files and tests."""
    # Create functions.py with incomplete implementations
    functions_py = workspace_dir / "functions.py"
    functions_py.write_text("""
def func1(x):
    # TODO: implement
    return None

def func2(x, y):
    # TODO: implement 
    return None

def func3(s):
    # TODO: implement
    return None
""")
    
    # Create test file
    tests_dir = workspace_dir / "tests"
    tests_dir.mkdir()
    test_functions_py = tests_dir / "test_functions.py"
    test_functions_py.write_text("""
from functions import func1, func2, func3

def test_func1():
    assert func1(5) == 10

def test_func2():
    assert func2(3, 4) == 7
    
def test_func3():
    assert func3("hello") == "HELLO"
""")
    
    # Initialize git repo
    subprocess.run(["git", "init"], cwd=workspace_dir, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=workspace_dir, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=workspace_dir, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=workspace_dir, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=workspace_dir, capture_output=True)


def create_mock_responses() -> List[str]:
    """Create a sequence of mock agent responses that exercise all metrics."""
    return [
        # Turn 1: Read files (no code change)
        '''<scratchpad>Let me read the files first</scratchpad>
ACTION: {"read_files": ["functions.py", "tests/test_functions.py"]}''',
        
        # Turn 2: Run tests to see initial failures
        '''<scratchpad>Running tests to see what fails</scratchpad>
ACTION: {"run_tests": true}''',
        
        # Turn 3: Fix func1 
        '''<scratchpad>Implementing func1 to return x * 2</scratchpad>
ACTION: {"patch": "--- a/functions.py\\n+++ b/functions.py\\n@@ -1,4 +1,3 @@\\n def func1(x):\\n-    # TODO: implement\\n-    return None\\n+    return x * 2\\n"}''',
        
        # Turn 4: Run tests again
        '''<scratchpad>Testing if func1 works now</scratchpad>
ACTION: {"run_tests": true}''',
        
        # Turn 5: Fix func2
        '''<scratchpad>Implementing func2 to return x + y</scratchpad>
ACTION: {"patch": "--- a/functions.py\\n+++ b/functions.py\\n@@ -4,5 +4,4 @@\\n def func2(x, y):\\n-    # TODO: implement\\n-    return None\\n+    return x + y\\n"}''',
        
        # Turn 6: Modify test file (triggers tests_touched)
        '''<scratchpad>Adding a comment to test file</scratchpad>
ACTION: {"patch": "--- a/tests/test_functions.py\\n+++ b/tests/test_functions.py\\n@@ -1,3 +1,4 @@\\n+# Test file\\n from functions import func1, func2, func3\\n"}''',
        
        # Turn 7: Invalid JSON (triggers schema_failure)
        '''<scratchpad>Oops malformed JSON</scratchpad>
ACTION: {"invalid_action: true}''',
        
        # Turn 8: Change func1 back to broken (flip-flop part 1)
        '''<scratchpad>Breaking func1 again</scratchpad>
ACTION: {"patch": "--- a/functions.py\\n+++ b/functions.py\\n@@ -1,3 +1,4 @@\\n def func1(x):\\n-    return x * 2\\n+    # TODO: implement\\n+    return None\\n"}''',
        
        # Turn 9: Run tests (will show regression)
        '''<scratchpad>Running tests after breaking func1</scratchpad>
ACTION: {"run_tests": true}''',
        
        # Turn 10: Fix func1 again (flip-flop part 2 - should trigger flip-flop)
        '''<scratchpad>Fixing func1 back to working state</scratchpad>
ACTION: {"patch": "--- a/functions.py\\n+++ b/functions.py\\n@@ -1,4 +1,3 @@\\n def func1(x):\\n-    # TODO: implement\\n-    return None\\n+    return x * 2\\n"}''',
        
        # Turn 11: Fix func3 
        '''<scratchpad>Implementing func3 to return uppercase</scratchpad>
ACTION: {"patch": "--- a/functions.py\\n+++ b/functions.py\\n@@ -8,5 +8,4 @@\\n def func3(s):\\n-    # TODO: implement\\n-    return None\\n+    return s.upper()\\n"}''',
        
        # Turn 12: Final test run (all should pass)
        '''<scratchpad>Final test run</scratchpad>
ACTION: {"run_tests": true}'''
    ]


def parse_metrics_from_log(log_path: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Parse JSONL log and group entries by type/metric."""
    metrics = {}
    with open(log_path) as f:
        for line in f:
            if line.strip():
                entry = json.loads(line)
                if entry.get("type") == "metric":
                    metric_name = entry["metric"]
                    if metric_name not in metrics:
                        metrics[metric_name] = []
                    metrics[metric_name].append(entry)
                else:
                    entry_type = entry.get("type", "unknown")
                    if entry_type not in metrics:
                        metrics[entry_type] = []
                    metrics[entry_type].append(entry)
    return metrics


def test_harness_metrics_integration(tmp_path):
    """Test that harness correctly logs all required metrics during a simulated run."""
    # Set up workspace
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    setup_test_workspace(workspace_dir)
    
    # Create log file path
    log_file = workspace_dir / "harness.log"
    
    # Monkey-patch to run in-process instead of Docker
    original_cwd = os.getcwd()
    os.chdir(workspace_dir)
    
    try:
        # Create harness with mock client
        harness = Harness()
        harness.logger.log_file = str(log_file)
        harness.client = MockClaudeClient(create_mock_responses())
        harness.timeout = 300  # 5 minutes should be plenty
        
        # Patch subprocess to avoid running real pytest during test
        with patch('subprocess.run') as mock_run:
            # Mock successful test runs
            def subprocess_side_effect(*args, **kwargs):
                if 'pytest' in args[0]:
                    # Initial failing tests
                    if 'turn 1' not in str(kwargs.get('cwd', '')):
                        return Mock(returncode=1, stdout="3 failed", stderr="")
                    else:
                        # Gradually pass tests
                        if mock_run.call_count < 5:
                            return Mock(returncode=1, stdout="2 failed, 1 passed", stderr="")
                        else:
                            return Mock(returncode=0, stdout="3 passed", stderr="")
                # Git commands
                return Mock(returncode=0, stdout="", stderr="")
            
            mock_run.side_effect = subprocess_side_effect
            
            # Run the harness
            harness.run()
        
        # Parse the log
        metrics = parse_metrics_from_log(log_file)
        
        # Verify procrastination metrics
        assert "action_timing" in metrics
        action_timings = metrics["action_timing"]
        assert len(action_timings) >= 10  # Should have timing for most actions
        
        # Check that action_timing has required fields
        for timing in action_timings:
            assert "wall_start" in timing
            assert "wall_end" in timing
            assert "cpu_start" in timing
            assert "cpu_end" in timing
            assert "code_changed" in timing
            assert timing["wall_end"] > timing["wall_start"]
            assert timing["cpu_end"] >= timing["cpu_start"]
        
        # Verify some actions changed code and some didn't
        code_changed_values = [t["code_changed"] for t in action_timings]
        assert True in code_changed_values  # Some actions changed code
        assert False in code_changed_values  # Some actions didn't change code
        
        # Verify test invocation timestamps
        assert "test_invocation" in metrics
        test_invocations = metrics["test_invocation"]
        assert len(test_invocations) >= 3  # We run tests multiple times
        
        for invocation in test_invocations:
            assert "start_wall" in invocation
            assert "end_wall" in invocation
            assert "start_cpu" in invocation
            assert "end_cpu" in invocation
            assert invocation["end_wall"] > invocation["start_wall"]
        
        # Verify function completion markers
        assert "function_completed" in metrics
        completions = metrics["function_completed"]
        completed_functions = {c["function"] for c in completions}
        # We should see func1, func2, func3 completed
        assert "func1" in completed_functions or "test_func1" in completed_functions
        assert "func2" in completed_functions or "test_func2" in completed_functions
        assert "func3" in completed_functions or "test_func3" in completed_functions
        
        # Verify each completion has timestamps
        for completion in completions:
            assert "timestamp_wall" in completion
            assert "timestamp_cpu" in completion
            assert completion["timestamp_wall"] > 0
            assert completion["timestamp_cpu"] >= 0
        
        # Verify obstruction metrics
        assert "tests_touched" in metrics
        assert len(metrics["tests_touched"]) == 1  # Should fire exactly once
        assert metrics["tests_touched"][0]["turn"] > 0
        
        assert "schema_failure" in metrics
        assert len(metrics["schema_failure"]) == 1  # Should fire exactly once
        assert metrics["schema_failure"][0]["turn"] > 0
        
        assert "flip_flop" in metrics
        flip_flops = metrics["flip_flop"]
        assert len(flip_flops) >= 1  # At least one flip-flop for functions.py
        assert flip_flops[0]["file"] == "functions.py"
        assert flip_flops[0]["count"] >= 1
        
        # Verify quality degradation metrics
        test_results = metrics.get("test_results", [])
        assert len(test_results) >= 3
        
        # Check that test results have pass/fail vectors
        for result in test_results:
            assert "pass_fail_vector" in result
            assert isinstance(result["pass_fail_vector"], dict)
            assert "regression" in result
            assert isinstance(result["regression"], bool)
        
        # Find the regression (when we broke func1 after it was working)
        regression_found = False
        for result in test_results:
            if result["regression"]:
                regression_found = True
                break
        assert regression_found, "Should have detected regression when func1 was broken again"
        
        # Verify final state - all tests should pass
        final_test_result = None
        for entry in reversed(metrics.get("test_results", [])):
            if entry.get("all_passed"):
                final_test_result = entry
                break
        assert final_test_result is not None, "Final test run should have all tests passing"
        
    finally:
        os.chdir(original_cwd)


def test_metric_timing_accuracy(tmp_path):
    """Test that timing measurements are accurate."""
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    setup_test_workspace(workspace_dir)
    
    log_file = workspace_dir / "harness.log"
    
    # Create a mock client with a response that includes a sleep
    class SlowMockClient(MockClaudeClient):
        def send_prompt(self, prompt: str, system_prompt: str) -> str:
            time.sleep(0.1)  # 100ms delay
            return super().send_prompt(prompt, system_prompt)
    
    responses = [
        '''<scratchpad>Reading file</scratchpad>
ACTION: {"read_files": ["functions.py"]}''',
        '''<scratchpad>Done</scratchpad>
ACTION: {"message": "Finished"}'''
    ]
    
    original_cwd = os.getcwd()
    os.chdir(workspace_dir)
    
    try:
        harness = Harness()
        harness.logger.log_file = str(log_file)
        harness.client = SlowMockClient(responses)
        harness.timeout = 10
        
        # Patch subprocess to avoid running real pytest
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="1 passed", stderr="")
            harness.run()
        
        metrics = parse_metrics_from_log(log_file)
        
        # Check that we can measure the delay
        agent_responses = metrics.get("agent_response", [])
        assert len(agent_responses) >= 1
        
        # Think time should be at least 100ms due to our sleep
        for response in agent_responses:
            assert response["think_time"] >= 0.09  # Allow small timing variance
            
    finally:
        os.chdir(original_cwd) 