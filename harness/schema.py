"""
Schema definitions for agent actions.
"""
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass
import json


@dataclass
class Action:
    """Base class for all agent actions."""
    action_type: str
    
    
@dataclass
class ReadFileAction(Action):
    """Action to read a file."""
    action_type: str = "read_file"
    path: str
    
    
@dataclass
class WriteFileAction(Action):
    """Action to write/modify a file."""
    action_type: str = "write_file"
    path: str
    content: str
    
    
@dataclass
class ApplyPatchAction(Action):
    """Action to apply a unified diff patch."""
    action_type: str = "apply_patch"
    path: str
    patch: str
    
    
@dataclass  
class RunTestsAction(Action):
    """Action to run pytest."""
    action_type: str = "run_tests"
    specific_test: Optional[str] = None  # Run specific test file/function
    
    
@dataclass
class ListDirectoryAction(Action):
    """Action to list directory contents."""
    action_type: str = "list_directory"
    path: str = "."
    

def validate_action(action_json: Dict[str, Any]) -> Union[Action, None]:
    """
    Validate and parse an action from JSON.
    Returns the parsed Action object or None if invalid.
    """
    try:
        action_type = action_json.get("action_type")
        
        if action_type == "read_file":
            return ReadFileAction(path=action_json["path"])
        elif action_type == "write_file":
            return WriteFileAction(
                path=action_json["path"],
                content=action_json["content"]
            )
        elif action_type == "apply_patch":
            return ApplyPatchAction(
                path=action_json["path"],
                patch=action_json["patch"]
            )
        elif action_type == "run_tests":
            return RunTestsAction(
                specific_test=action_json.get("specific_test")
            )
        elif action_type == "list_directory":
            return ListDirectoryAction(
                path=action_json.get("path", ".")
            )
        else:
            return None
            
    except (KeyError, TypeError) as e:
        return None


# JSON schema for validation
ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "action_type": {
            "type": "string",
            "enum": ["read_file", "write_file", "apply_patch", "run_tests", "list_directory"]
        }
    },
    "required": ["action_type"],
    "allOf": [
        {
            "if": {"properties": {"action_type": {"const": "read_file"}}},
            "then": {
                "properties": {"path": {"type": "string"}},
                "required": ["path"]
            }
        },
        {
            "if": {"properties": {"action_type": {"const": "write_file"}}},
            "then": {
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        },
        {
            "if": {"properties": {"action_type": {"const": "apply_patch"}}},
            "then": {
                "properties": {
                    "path": {"type": "string"},
                    "patch": {"type": "string"}
                },
                "required": ["path", "patch"]
            }
        },
        {
            "if": {"properties": {"action_type": {"const": "run_tests"}}},
            "then": {
                "properties": {
                    "specific_test": {"type": "string"}
                }
            }
        },
        {
            "if": {"properties": {"action_type": {"const": "list_directory"}}},
            "then": {
                "properties": {
                    "path": {"type": "string"}
                }
            }
        }
    ]
} 