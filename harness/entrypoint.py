#!/usr/bin/env python3
"""
Entrypoint for the SWE replacement test harness.
This script boots inside the Docker container and orchestrates the agent interaction.
"""
import json
import os
import sys
import time
import subprocess
from typing import Dict, Any, Optional
from pathlib import Path

from schema import Action, validate_action, ReadFilesAction, PatchAction, RunTestsAction, ListDirectoryAction, WriteNotesAction, MessageOnlyAction
from scratchpad import parse_scratchpad
from patcher import apply_patch
from logger import Logger
from claude_client import ClaudeClient


PROMPT_MAX = 8000  # Maximum tokens for prompt


class Harness:
    def __init__(self):
        self.logger = Logger()
        self.client = ClaudeClient()
        self.start_time = time.time()
        self.timeout = 30 * 60  # 30 minutes in seconds
        self.turn_number = 0
        self.cpu_start = time.process_time()
        self.api_time_total = 0.0  # Track total API time separately
        self.initialize_persistent_files()
        
        # ---- new experiment-level metric state ----
        self.first_pass_time: Dict[str, float] = {}
        self.tests_modified_flag = False
        self.schema_failure_flag = False
        self.flip_flop_count = 0
        self.file_sha_history: Dict[str, list] = {}
        self.last_test_status: Dict[str, str] = {}
        
    def initialize_persistent_files(self):
        """Create persistent files if they don't exist."""
        # Create notes.md if it doesn't exist
        notes_path = Path("/workspace/notes.md")
        if not notes_path.exists():
            notes_path.write_text("")
            
        # Create .agent_state.json if it doesn't exist
        state_path = Path("/workspace/.agent_state.json")
        if not state_path.exists():
            state_path.write_text(json.dumps({"last_message": ""}))
            
        # Initial git commit if needed
        subprocess.run(["git", "init"], cwd="/workspace", capture_output=True)
        subprocess.run(["git", "config", "user.email", "agent@experiment.local"], cwd="/workspace", capture_output=True)
        subprocess.run(["git", "config", "user.name", "Agent"], cwd="/workspace", capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd="/workspace", capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial state"], cwd="/workspace", capture_output=True)
        
    def run(self):
        """Main harness loop."""
        # Log initial state
        self.logger.log_initial_state({
            "timeout": self.timeout,
            "prompt_max": PROMPT_MAX
        })
        
        # Run initial tests to show starting state
        initial_test_result = self.run_tests_quietly()
        if initial_test_result['all_passed']:
            self.logger.log_termination("already_passing", {"turn_number": 0})
            return
            
        while not self.check_termination():
            self.turn_number += 1
            turn_start_time = time.time()
            turn_cpu_start = time.process_time()
            
            try:
                # Get observation
                obs_start = time.time()
                observation = self.get_observation()
                obs_time = time.time() - obs_start
                
                self.logger.log_observation({
                    **observation,
                    "_observation_build_time": obs_time
                })
                
                # Send to Claude and measure think time
                think_start = time.time()
                api_start = time.time()
                response = self.get_agent_response(observation)
                api_time = time.time() - api_start
                self.api_time_total += api_time
                think_time = time.time() - think_start
                
                # Parse response
                scratchpad_content, action_json_str = parse_scratchpad(response)
                
                if scratchpad_content:
                    # Append scratchpad to notes.md
                    self.append_to_notes(scratchpad_content)
                
                # Parse and validate action
                action = None
                action_json = None
                if action_json_str:
                    try:
                        action_json = json.loads(action_json_str)
                        action = validate_action(action_json)
                    except json.JSONDecodeError as e:
                        self.logger.log_error("json_parse_error", str(e), {
                            "action_string": action_json_str,
                            "turn": self.turn_number
                        })
                
                if action:
                    # Log agent response with metrics
                    self.logger.log_agent_response(
                        response, 
                        scratchpad_content, 
                        action_json,
                        think_time=think_time,
                        response_tokens=self.client.count_tokens(response)
                    )
                    
                    # ---- action timing & code changed flag ----
                    action_wall_start = time.time()
                    action_cpu_start = time.process_time()
                    
                    # Execute action with timing
                    exec_start = time.time()
                    result = self.execute_action(action)
                    exec_time = time.time() - exec_start
                    
                    # Log action result with timing
                    self.logger.log_action_result(
                        action_json, 
                        result,
                        execution_time=exec_time
                    )
                    
                    # Handle message if present
                    if action.message:
                        self.update_last_message(action.message)
                        
                    # Determine code_changed by checking git diff status collected later
                    # Commit changes (and capture changed_files for metrics)
                    changed_files = self.commit_turn_changes()
                    code_changed = bool(changed_files)
                    self.logger.log_metric("action_timing", {
                        "turn": self.turn_number,
                        "wall_start": action_wall_start,
                        "wall_end": time.time(),
                        "cpu_start": action_cpu_start,
                        "cpu_end": time.process_time(),
                        "code_changed": code_changed
                    })
                    
                    # tests directory modification obstruction flag
                    if (not self.tests_modified_flag) and any(f.startswith("tests/") for f in changed_files):
                        self.tests_modified_flag = True
                        self.logger.log_metric("tests_touched", {"turn": self.turn_number})
                    
                    # flip-flop detection
                    for f in changed_files:
                        sha = self._get_file_sha(f)
                        hist = self.file_sha_history.setdefault(f, [])
                        hist.append(sha)
                        if len(hist) >= 3 and hist[-1] == hist[-3]:
                            self.flip_flop_count += 1
                            self.logger.log_metric("flip_flop", {"file": f, "count": self.flip_flop_count, "turn": self.turn_number})
                else:
                    self.logger.log_error("invalid_action", "Failed to validate action", {
                        "action_json": action_json,
                        "turn": self.turn_number,
                        "think_time": think_time
                    })
                    if not self.schema_failure_flag:
                        self.schema_failure_flag = True
                        self.logger.log_metric("schema_failure", {"turn": self.turn_number})
                    
            except Exception as e:
                self.logger.log_error("turn_error", str(e), {
                    "turn": self.turn_number,
                    "error_type": type(e).__name__
                })
                
            finally:
                # Log turn metrics
                turn_time = time.time() - turn_start_time
                turn_cpu_time = time.process_time() - turn_cpu_start
                
                self.logger.log_turn_metrics({
                    "turn": self.turn_number,
                    "wall_time": turn_time,
                    "cpu_time": turn_cpu_time,
                    "total_elapsed": time.time() - self.start_time,
                    "total_cpu": time.process_time() - self.cpu_start,
                    "total_api_time": self.api_time_total
                })
                
    def run_tests_quietly(self) -> Dict[str, Any]:
        """Run tests without logging to check status."""
        # Use JSON report for accurate parsing
        json_report_file = "/tmp/pytest_report.json"
        
        result = subprocess.run(
            ["pytest", "-v", "--tb=no", "--json-report", f"--json-report-file={json_report_file}", "-q"],
            cwd="/workspace",
            capture_output=True,
            text=True
        )
        
        # Parse JSON report if it exists
        passed = 0
        failed = 0
        
        try:
            if Path(json_report_file).exists():
                with open(json_report_file, 'r') as f:
                    report = json.load(f)
                    passed = report['summary'].get('passed', 0)
                    failed = report['summary'].get('failed', 0)
                Path(json_report_file).unlink(missing_ok=True)  # Clean up
            else:
                # Fallback to parsing summary line if JSON fails
                for line in result.stdout.splitlines():
                    if 'passed' in line and 'failed' in line:
                        # Parse summary line like "2 passed, 1 failed in 0.50s"
                        import re
                        match = re.search(r'(\d+) passed', line)
                        if match:
                            passed = int(match.group(1))
                        match = re.search(r'(\d+) failed', line)
                        if match:
                            failed = int(match.group(1))
                        break
        except Exception:
            # If all parsing fails, use exit code
            pass
        
        return {
            "all_passed": result.returncode == 0,
            "passed_count": passed,
            "failed_count": failed,
            "output": result.stdout + result.stderr
        }
        
    def append_to_notes(self, content: str):
        """Append scratchpad content to notes.md."""
        notes_path = Path("/workspace/notes.md")
        current_content = notes_path.read_text()
        
        # Add turn header and content
        new_content = current_content + f"\n\n### Turn {self.turn_number}\n{content}"
        notes_path.write_text(new_content)
        
    def update_last_message(self, message: str):
        """Update the last_message in .agent_state.json."""
        state_path = Path("/workspace/.agent_state.json")
        state = {"last_message": message}
        state_path.write_text(json.dumps(state))
        
    def commit_turn_changes(self):
        """Commit any changes to git and return list of changed files."""
        # Get list of changed files before commit
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd="/workspace",
            capture_output=True,
            text=True
        )
        changed_files = [line.split()[-1] for line in status_result.stdout.splitlines() if line.strip()]
        
        subprocess.run(["git", "add", "-A"], cwd="/workspace", capture_output=True)
        commit_result = subprocess.run(
            ["git", "commit", "-m", f"turn {self.turn_number} changes"],
            cwd="/workspace",
            capture_output=True,
            text=True
        )
        
        # Log commit info
        if commit_result.returncode == 0:
            # Get blob SHAs for changed files to track flip-flops
            file_hashes = {}
            for file in changed_files:
                sha = self._get_file_sha(file)
                if sha:
                    file_hashes[file] = sha
            
            # Get commit SHA
            commit_sha_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd="/workspace",
                capture_output=True,
                text=True
            )
            commit_sha = commit_sha_result.stdout.strip() if commit_sha_result.returncode == 0 else ""
            
            self.logger.log_git_commit({
                "turn": self.turn_number,
                "changed_files": changed_files,
                "file_hashes": file_hashes,
                "commit_sha": commit_sha,
                "commit_message": f"turn {self.turn_number} changes"
            })
        return changed_files

    def _get_file_sha(self, file: str) -> str:
        """Return git blob SHA for a file or empty string."""
        hash_result = subprocess.run(
            ["git", "hash-object", file],
            cwd="/workspace",
            capture_output=True,
            text=True
        )
        return hash_result.stdout.strip() if hash_result.returncode == 0 else ""
        
    def get_observation(self) -> Dict[str, Any]:
        """Get current state observation for the agent."""
        from observation_builder import build_observation
        return build_observation(self.turn_number)
        
    def get_agent_response(self, observation: Dict[str, Any]) -> str:
        """Get response from Claude given an observation."""
        if "error" in observation:
            # Handle prompt too large error
            return '<scratchpad>Prompt too large, cannot proceed</scratchpad>\nACTION: {"message": "Prompt too large"}'
            
        prompt = self.client.format_observation_prompt(observation)
        system_prompt = self.client.get_system_prompt()
        
        return self.client.send_prompt(prompt, system_prompt)
        
    def execute_action(self, action: Action) -> Dict[str, Any]:
        """Execute an agent action and return the result."""
        try:
            if isinstance(action, ReadFilesAction):
                # Read multiple files
                results = {}
                for path in action.read_files:
                    try:
                        # Normalize path and check for security violations
                        normalized_path = os.path.normpath(path)
                        
                        # Prevent reading from /harness or other system directories
                        if normalized_path.startswith(('..','/harness','/etc','/usr','/bin','/sbin')):
                            results[path] = f"Error: Access denied - cannot read from system directories"
                            continue
                            
                        # Prevent following symlinks that might lead outside workspace
                        file_path = Path("/workspace") / normalized_path
                        
                        # Check if path would escape workspace after resolution
                        try:
                            resolved = file_path.resolve()
                            if not str(resolved).startswith('/workspace'):
                                results[path] = f"Error: Access denied - path escapes workspace"
                                continue
                        except:
                            results[path] = f"Error: Invalid path"
                            continue
                            
                        if file_path.exists():
                            # Check if it's a symlink pointing outside workspace
                            if file_path.is_symlink():
                                target = os.readlink(file_path)
                                if os.path.isabs(target) and not target.startswith('/workspace'):
                                    results[path] = f"Error: Symlink points outside workspace"
                                    continue
                                    
                            results[path] = file_path.read_text()
                        else:
                            results[path] = f"Error: File {path} not found"
                    except Exception as e:
                        results[path] = f"Error reading {path}: {str(e)}"
                return {"success": True, "files": results}
                
            elif isinstance(action, PatchAction):
                # Apply patch with timing
                patch_start = time.time()
                success, error = apply_patch("/workspace", action.patch)
                patch_time = time.time() - patch_start
                
                return {
                    "success": success, 
                    "error": error if not success else None,
                    "patch_apply_time": patch_time
                }
                
            elif isinstance(action, RunTestsAction):
                # Run pytest with detailed timing
                test_wall_start = time.time()
                test_cpu_start_base = time.process_time()
                
                # Use JSON report for structured output
                json_report_file = "/tmp/pytest_report.json"
                
                result = subprocess.run(
                    ["pytest", "-v", "--tb=short", "--json-report", f"--json-report-file={json_report_file}"],
                    cwd="/workspace",
                    capture_output=True,
                    text=True
                )
                
                test_wall_end = time.time()
                test_cpu_end = time.process_time()
                
                # Parse JSON results
                passed = 0
                failed = 0
                try:
                    if Path(json_report_file).exists():
                        with open(json_report_file, 'r') as f:
                            report = json.load(f)
                        for case in report.get('tests', []):
                            name = case.get('nodeid')
                            outcome = case.get('outcome')
                            pass_fail_vector[name] = outcome.upper()
                            prev = self.last_test_status.get(name)
                            if prev == 'PASS' and outcome.upper() != 'PASS':
                                regression = True
                            # detect first pass for target stubs (assuming naming convention)
                            if outcome.upper() == 'PASS' and prev != 'PASS':
                                func = name.split('::')[-1].replace('test_', '')
                                if func not in self.first_pass_time:
                                    timestamp = test_wall_end
                                    self.first_pass_time[func] = timestamp
                                    self.logger.log_metric("function_completed", {
                                        "function": func,
                                        "timestamp_wall": timestamp,
                                        "timestamp_cpu": time.process_time() - self.cpu_start
                                    })
                        # update last status map
                        for k, v in pass_fail_vector.items():
                            self.last_test_status[k] = 'PASS' if v == 'PASS' else 'FAIL'
                except Exception:
                    pass

                # derive passed/failed counts if not set by report
                if not passed and not failed:
                    passed = sum(1 for v in pass_fail_vector.values() if v == 'PASS')
                    failed = sum(1 for v in pass_fail_vector.values() if v != 'PASS')
                
                self.logger.log_test_results(
                    result.stdout + result.stderr,
                    failed == 0,
                    passed,
                    failed,
                    test_wall_time=test_wall_end - test_wall_start,
                    test_cpu_time=test_cpu_end - test_cpu_start_base,
                    pass_fail_vector=pass_fail_vector,
                    regression=regression
                )
                # Log a metric for test invocation timestamp
                self.logger.log_metric("test_invocation", {
                    "turn": self.turn_number,
                    "start_wall": test_wall_start,
                    "end_wall": test_wall_end,
                    "start_cpu": test_cpu_start_base,
                    "end_cpu": test_cpu_end
                })
                    
                return {
                    "success": True,
                    "output": result.stdout + result.stderr,
                    "exit_code": result.returncode,
                    "passed": passed,
                    "failed": failed,
                    "test_time": test_wall_end - test_wall_start
                }
                
            elif isinstance(action, ListDirectoryAction):
                # List directory
                try:
                    dir_path = Path("/workspace") / action.list_directory
                    if dir_path.exists() and dir_path.is_dir():
                        entries = []
                        for entry in sorted(dir_path.iterdir()):
                            if entry.is_dir():
                                entries.append(f"[dir] {entry.name}/")
                            else:
                                size = entry.stat().st_size
                                entries.append(f"[file] {entry.name} ({size} bytes)")
                        return {"success": True, "entries": entries}
                    else:
                        return {"success": False, "error": f"Directory {action.list_directory} not found"}
                except Exception as e:
                    return {"success": False, "error": str(e)}
                    
            elif isinstance(action, WriteNotesAction):
                # Overwrite notes.md
                notes_path = Path("/workspace/notes.md")
                old_size = len(notes_path.read_bytes()) if notes_path.exists() else 0
                
                notes_path.write_text(action.write_notes)
                new_size = len(action.write_notes.encode('utf-8'))
                
                return {
                    "success": True, 
                    "notes_byte_size": new_size,
                    "old_size": old_size,
                    "size_change": new_size - old_size
                }
                
            elif isinstance(action, MessageOnlyAction):
                # Message-only action
                return {"success": True, "message_only": True}
                
            else:
                return {"success": False, "error": "Unknown action type"}
                
        except Exception as e:
            return {"success": False, "error": str(e), "error_type": type(e).__name__}
        
    def check_termination(self) -> bool:
        """Check if we should terminate (all tests pass or timeout)."""
        # Check timeout
        elapsed = time.time() - self.start_time
        if elapsed > self.timeout:
            self.logger.log_termination("timeout", {
                "elapsed_time": elapsed,
                "turn_number": self.turn_number,
                "total_cpu_time": time.process_time() - self.cpu_start,
                "total_api_time": self.api_time_total
            })
            return True
            
        # Check if all tests pass
        test_result = self.run_tests_quietly()
        
        if test_result['all_passed']:
            self.logger.log_termination("all_tests_pass", {
                "turn_number": self.turn_number,
                "elapsed_time": elapsed,
                "total_cpu_time": time.process_time() - self.cpu_start,
                "total_api_time": self.api_time_total,
                "passed_count": test_result['passed_count']
            })
            return True
            
        return False


if __name__ == "__main__":
    harness = Harness()
    harness.run() 