"""
Schema definitions for agent actions.
"""
from typing import Dict, Any, Optional, Union, List
from dataclasses import dataclass
import json


@dataclass
class Action:
    """Base class for all agent actions."""
    message: Optional[str]
    

@dataclass
class ReadFilesAction(Action):
    """Action to read multiple files."""
    read_files: List[str]
    

@dataclass
class PatchAction(Action):
    """Action to apply a unified diff patch."""
    patch: str
    

@dataclass  
class RunTestsAction(Action):
    """Action to run pytest."""
    run_tests: bool = True
    

@dataclass
class ListDirectoryAction(Action):
    """Action to list directory contents."""
    list_directory: str
    

@dataclass
class WriteNotesAction(Action):
    """Action to overwrite the notes.md file."""
    write_notes: str
    

@dataclass
class MessageOnlyAction(Action):
    """Action that only contains a message."""
    pass


def validate_action(action_json: Dict[str, Any]) -> Union[Action, None]:
    """
    Validate and parse an action from JSON.
    Returns the parsed Action object or None if invalid.
    
    The action must have exactly one primary key (plus optional "message").
    """
    try:
        # Extract message if present
        message = action_json.get("message")
        
        # Count primary action keys
        primary_keys = ["read_files", "patch", "run_tests", "list_directory", "write_notes"]
        present_keys = [k for k in primary_keys if k in action_json]
        
        # Must have exactly one primary key (or zero if only message)
        if len(present_keys) > 1:
            return None
        elif len(present_keys) == 0:
            if message is not None:
                return MessageOnlyAction(message=message)
            else:
                return None
                
        # Parse based on the primary key
        if "read_files" in action_json:
            return ReadFilesAction(
                read_files=action_json["read_files"],
                message=message
            )
        elif "patch" in action_json:
            return PatchAction(
                patch=action_json["patch"],
                message=message
            )
        elif "run_tests" in action_json:
            return RunTestsAction(
                run_tests=action_json["run_tests"],
                message=message
            )
        elif "list_directory" in action_json:
            return ListDirectoryAction(
                list_directory=action_json["list_directory"],
                message=message
            )
        elif "write_notes" in action_json:
            return WriteNotesAction(
                write_notes=action_json["write_notes"],
                message=message
            )
            
    except (KeyError, TypeError) as e:
        return None


# JSON schema for validation
ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "read_files": {
            "type": "array",
            "items": {"type": "string"}
        },
        "patch": {
            "type": "string"
        },
        "run_tests": {
            "type": "boolean",
            "enum": [True]
        },
        "list_directory": {
            "type": "string"
        },
        "write_notes": {
            "type": "string"
        },
        "message": {
            "type": "string"
        }
    },
    "additionalProperties": False,
    "oneOf": [
        {"required": ["read_files"]},
        {"required": ["patch"]},
        {"required": ["run_tests"]},
        {"required": ["list_directory"]},
        {"required": ["write_notes"]},
        {"required": ["message"]}  # message-only action
    ]
} 