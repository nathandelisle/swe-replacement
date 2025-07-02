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
        self.initialize_persistent_files()
        
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
        subprocess.run(["git", "add", "notes.md", ".agent_state.json"], cwd="/workspace", capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial state"], cwd="/workspace", capture_output=True)
        
    def run(self):
        """Main harness loop."""
        while not self.check_termination():
            self.turn_number += 1
            
            # Get observation
            observation = self.get_observation()
            self.logger.log_observation(observation)
            
            # Send to Claude
            try:
                response = self.get_agent_response(observation)
                
                # Parse response
                scratchpad_content, action_json_str = parse_scratchpad(response)
                
                if scratchpad_content:
                    # Append scratchpad to notes.md
                    self.append_to_notes(scratchpad_content)
                
                # Parse action
                if action_json_str:
                    action_json = json.loads(action_json_str)
                    action = validate_action(action_json)
                    
                    if action:
                        # Log agent response
                        self.logger.log_agent_response(response, scratchpad_content, action_json)
                        
                        # Execute action
                        result = self.execute_action(action)
                        
                        # Log action result
                        self.logger.log_action_result(action_json, result)
                        
                        # Handle message if present
                        if action.message:
                            self.update_last_message(action.message)
                            
                        # Commit changes
                        self.commit_turn_changes()
                    else:
                        self.logger.log_error("invalid_action", "Failed to validate action", {"action_json": action_json})
                else:
                    self.logger.log_error("no_action", "No action found in response", {"response": response})
                    
            except Exception as e:
                self.logger.log_error("turn_error", str(e), {"turn": self.turn_number})
                
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
        """Commit any changes to notes.md and .agent_state.json."""
        subprocess.run(["git", "add", "notes.md", ".agent_state.json"], cwd="/workspace", capture_output=True)
        subprocess.run(["git", "commit", "-m", f"turn {self.turn_number} notes/message"], cwd="/workspace", capture_output=True)
        
    def get_observation(self) -> Dict[str, Any]:
        """Get current state observation for the agent."""
        # Build observation
        from observation_builder import build_observation
        return build_observation(self.turn_number)
        
    def get_agent_response(self, observation: Dict[str, Any]) -> str:
        """Get response from Claude given an observation."""
        # Check if observation has error
        if "error" in observation:
            # Handle prompt too large error
            return '{"message": "Prompt too large, cannot proceed"}'
            
        # Format observation as prompt
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
                        file_path = Path("/workspace") / path
                        if file_path.exists():
                            results[path] = file_path.read_text()
                        else:
                            results[path] = f"Error: File {path} not found"
                    except Exception as e:
                        results[path] = f"Error reading {path}: {str(e)}"
                return {"success": True, "files": results}
                
            elif isinstance(action, PatchAction):
                # Apply patch
                success, error = apply_patch("/workspace", action.patch)
                return {"success": success, "error": error if not success else None}
                
            elif isinstance(action, RunTestsAction):
                # Run pytest
                result = subprocess.run(
                    ["pytest", "-v", "--json-report", "--json-report-file=/tmp/report.json"],
                    cwd="/workspace",
                    capture_output=True,
                    text=True
                )
                
                # Read the JSON report
                try:
                    with open("/tmp/report.json", 'r') as f:
                        report = json.load(f)
                    
                    passed = report.get("summary", {}).get("passed", 0)
                    failed = report.get("summary", {}).get("failed", 0)
                    
                    self.logger.log_test_results(
                        result.stdout + result.stderr,
                        failed == 0,
                        passed,
                        failed
                    )
                except:
                    pass
                    
                return {
                    "success": True,
                    "output": result.stdout + result.stderr,
                    "exit_code": result.returncode
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
                                entries.append(f"[file] {entry.name}")
                        return {"success": True, "entries": entries}
                    else:
                        return {"success": False, "error": f"Directory {action.list_directory} not found"}
                except Exception as e:
                    return {"success": False, "error": str(e)}
                    
            elif isinstance(action, WriteNotesAction):
                # Overwrite notes.md
                notes_path = Path("/workspace/notes.md")
                notes_path.write_text(action.write_notes)
                
                # Log notes size
                notes_size = len(action.write_notes.encode('utf-8'))
                
                return {"success": True, "notes_byte_size": notes_size}
                
            elif isinstance(action, MessageOnlyAction):
                # Message-only action, nothing to execute
                return {"success": True, "message_only": True}
                
            else:
                return {"success": False, "error": "Unknown action type"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
        
    def check_termination(self) -> bool:
        """Check if we should terminate (all tests pass or timeout)."""
        # Check timeout
        if time.time() - self.start_time > self.timeout:
            self.logger.log_termination("timeout", {"elapsed_time": self.timeout})
            return True
            
        # Check if all tests pass (need to run pytest to check)
        result = subprocess.run(
            ["pytest", "-v", "--tb=no"],
            cwd="/workspace",
            capture_output=True
        )
        
        if result.returncode == 0:
            self.logger.log_termination("all_tests_pass", {"turn_number": self.turn_number})
            return True
            
        return False


if __name__ == "__main__":
    harness = Harness()
    harness.run() 