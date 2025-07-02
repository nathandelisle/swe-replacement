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
        self.turn_number += 1
        
        # Add metadata
        log_entry = {
            "turn_number": self.turn_number,
            "timestamp": datetime.utcnow().isoformat(),
            "elapsed_time": time.time() - self.start_time,
            **turn_data
        }
        
        # Append to JSONL file
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
            
    def log_observation(self, observation: Dict[str, Any]):
        """Log an observation sent to the agent."""
        self.log_turn({
            "type": "observation",
            "data": observation
        })
        
    def log_agent_response(self, response: str, scratchpad: Optional[str], 
                          action: Optional[Dict[str, Any]]):
        """Log the agent's response."""
        self.log_turn({
            "type": "agent_response",
            "raw_response": response,
            "scratchpad": scratchpad,
            "action": action
        })
        
    def log_action_result(self, action: Dict[str, Any], result: Dict[str, Any]):
        """Log the result of executing an action."""
        # Add special fields for analysis
        log_data = {
            "type": "action_result",
            "action": action,
            "result": result
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
            "error_type": error_type,
            "error_message": error_message,
            "context": context or {}
        })
        
    def log_test_results(self, test_output: str, all_passed: bool,
                        passed_count: int, failed_count: int):
        """Log test execution results."""
        self.log_turn({
            "type": "test_results",
            "output": test_output,
            "all_passed": all_passed,
            "passed_count": passed_count,
            "failed_count": failed_count
        })
        
    def log_termination(self, reason: str, final_state: Dict[str, Any]):
        """Log termination of the trial."""
        self.log_turn({
            "type": "termination",
            "reason": reason,
            "final_state": final_state,
            "total_elapsed_time": time.time() - self.start_time
        }) 