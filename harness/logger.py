"""
Logger for appending turn-level data to JSONL log file.
"""
import json
import os
import time
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path


class Logger:
    def __init__(self, log_file: str = "/workspace/harness.log"):
        """
        Initialize the logger.
        
        Args:
            log_file: Path to the JSONL log file
        """
        self.log_file = log_file
        self.turn_number = 0
        self.start_time = time.time()
        
    def log_turn(self, turn_data: Dict[str, Any]):
        """
        Log a single turn to the JSONL file.
        
        Args:
            turn_data: Dictionary containing turn information
        """
        # Add metadata
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "elapsed_time": time.time() - self.start_time,
            **turn_data
        }
        
        # Append to JSONL file
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
            
    def log_initial_state(self, config: Dict[str, Any]):
        """Log initial configuration and state."""
        self.log_turn({
            "type": "initial_state",
            "config": config
        })
        
    def log_observation(self, observation: Dict[str, Any]):
        """Log an observation sent to the agent."""
        self.log_turn({
            "type": "observation",
            "turn_number": self.turn_number,
            "data": observation
        })
        
    def log_agent_response(self, response: str, scratchpad: Optional[str], 
                          action: Optional[Dict[str, Any]], think_time: float = 0,
                          response_tokens: int = 0):
        """Log the agent's response with timing metrics."""
        self.turn_number += 1
        self.log_turn({
            "type": "agent_response",
            "turn_number": self.turn_number,
            "raw_response": response,
            "scratchpad": scratchpad,
            "action": action,
            "think_time": think_time,
            "response_tokens": response_tokens,
            "response_length": len(response)
        })
        
    def log_action_result(self, action: Dict[str, Any], result: Dict[str, Any],
                         execution_time: float = 0):
        """Log the result of executing an action."""
        # Add special fields for analysis
        log_data = {
            "type": "action_result",
            "turn_number": self.turn_number,
            "action": action,
            "result": result,
            "execution_time": execution_time
        }
        
        # Add message field if present in action
        if "message" in action:
            log_data["message"] = action["message"]
            
        # Add notes_byte_size if this was a write_notes action
        if "write_notes" in action or result.get("notes_byte_size"):
            # Calculate current notes.md size
            notes_path = Path("/workspace/notes.md")
            if notes_path.exists():
                log_data["notes_byte_size"] = len(notes_path.read_bytes())
            else:
                log_data["notes_byte_size"] = result.get("notes_byte_size", 0)
                
        self.log_turn(log_data)
        
    def log_error(self, error_type: str, error_message: str, 
                  context: Optional[Dict[str, Any]] = None):
        """Log an error."""
        self.log_turn({
            "type": "error",
            "turn_number": self.turn_number,
            "error_type": error_type,
            "error_message": error_message,
            "context": context or {}
        })
        
    def log_metric(self, metric_name: str, details: Dict[str, Any]):
        """Log a generic metric entry.

        Args:
            metric_name: A short string identifier, e.g., "function_completed"
            details: Arbitrary JSON-serialisable dict with metric payload.
        """
        payload = {
            "type": "metric",
            "metric": metric_name,
            **details
        }
        self.log_turn(payload)
        
    def log_test_results(self, test_output: str, all_passed: bool,
                        passed_count: int, failed_count: int,
                        test_wall_time: float = 0, test_cpu_time: float = 0,
                        pass_fail_vector: Optional[Dict[str, str]] = None,
                        regression: bool = False):
        """Log test execution results with timing and full outcome vector."""
        self.log_turn({
            "type": "test_results",
            "turn_number": self.turn_number,
            "output": test_output,
            "all_passed": all_passed,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "test_wall_time": test_wall_time,
            "test_cpu_time": test_cpu_time,
            "pass_fail_vector": pass_fail_vector or {},
            "regression": regression
        })
        
    def log_turn_metrics(self, metrics: Dict[str, Any]):
        """Log turn-level metrics."""
        # Extract and highlight key timing metrics
        enhanced_metrics = {
            "type": "turn_metrics",
            **metrics
        }
        
        # Calculate harness overhead if API time is provided
        if "total_api_time" in metrics and "wall_time" in metrics:
            enhanced_metrics["harness_overhead"] = metrics["wall_time"] - metrics.get("think_time", 0)
            
        self.log_turn(enhanced_metrics)
        
    def log_git_commit(self, commit_info: Dict[str, Any]):
        """Log git commit information."""
        self.log_turn({
            "type": "git_commit",
            **commit_info
        })
        
    def log_termination(self, reason: str, final_state: Dict[str, Any]):
        """Log termination of the trial."""
        self.log_turn({
            "type": "termination",
            "reason": reason,
            "final_state": final_state,
            "total_elapsed_time": time.time() - self.start_time
        }) 