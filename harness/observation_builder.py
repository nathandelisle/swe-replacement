"""
Build observations for the agent with token counting and summarization.
"""
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
import tiktoken


PROMPT_MAX = 8000  # Maximum tokens for prompt


def count_tokens(text: str, model: str = "cl100k_base") -> int:
    """Count tokens in text using tiktoken."""
    encoding = tiktoken.get_encoding(model)
    return len(encoding.encode(text))


def get_directory_tree(path: str = "/workspace", max_depth: int = 2) -> str:
    """Get a directory tree up to max_depth."""
    def build_tree(current_path: Path, prefix: str = "", depth: int = 0) -> List[str]:
        if depth >= max_depth:
            return []
            
        entries = []
        try:
            items = sorted(current_path.iterdir())
            for i, item in enumerate(items):
                is_last = i == len(items) - 1
                
                # Skip hidden files except .agent_state.json
                if item.name.startswith('.') and item.name != '.agent_state.json':
                    continue
                    
                connector = "└── " if is_last else "├── "
                if item.is_dir():
                    entries.append(f"{prefix}{connector}{item.name}/")
                    extension = "    " if is_last else "│   "
                    entries.extend(build_tree(item, prefix + extension, depth + 1))
                else:
                    entries.append(f"{prefix}{connector}{item.name}")
        except PermissionError:
            pass
            
        return entries
    
    tree_lines = build_tree(Path(path))
    return "\n".join(tree_lines)


def get_git_diff() -> str:
    """Get git diff since previous commit."""
    result = subprocess.run(
        ["git", "diff", "HEAD~1", "HEAD"],
        cwd="/workspace",
        capture_output=True,
        text=True
    )
    return result.stdout if result.returncode == 0 else ""


def get_test_results() -> str:
    """Get current pytest results."""
    result = subprocess.run(
        ["pytest", "-v", "--tb=short", "--no-header"],
        cwd="/workspace",
        capture_output=True,
        text=True
    )
    return result.stdout + result.stderr


def get_requested_files() -> Dict[str, str]:
    """Get contents of commonly needed files."""
    # For now, just return empty dict - agent will use read_files action
    return {}


def get_previous_message() -> str:
    """Get the previous message from agent state."""
    state_path = Path("/workspace/.agent_state.json")
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
            return state.get("last_message", "")
        except:
            pass
    return ""


def summarize_notes(notes_content: str, num_tokens: int = 1000) -> str:
    """Summarize the oldest portion of notes using Claude."""
    from claude_client import ClaudeClient
    
    # Find the portion to summarize (first num_tokens)
    encoding = tiktoken.get_encoding("cl100k_base")
    tokens = encoding.encode(notes_content)
    
    if len(tokens) <= num_tokens:
        return notes_content
        
    # Get the first num_tokens
    portion_to_summarize = encoding.decode(tokens[:num_tokens])
    remaining_content = encoding.decode(tokens[num_tokens:])
    
    # Summarize using Claude
    client = ClaudeClient()
    prompt = f"Summarize the following developer notes into <150 tokens while keeping exact code references: {portion_to_summarize}"
    
    try:
        summary = client.send_prompt(prompt, system_prompt="You are a helpful assistant that summarizes technical notes concisely.")
        
        # Combine summary with remaining content
        return f"[SUMMARIZED: {summary}]\n\n{remaining_content}"
    except:
        # If summarization fails, return original
        return notes_content


def build_observation(turn_number: int) -> Dict[str, Any]:
    """Build the complete observation for the agent."""
    # Gather all components
    observation = {
        "directory_tree": get_directory_tree(),
        "git_diff": get_git_diff(),
        "test_results": get_test_results(),
        "requested_files": get_requested_files(),
        "previous_message": get_previous_message()
    }
    
    # Convert to JSON string to count tokens
    observation_json = json.dumps(observation, indent=2)
    
    # Count tokens
    total_tokens = count_tokens(observation_json)
    
    if total_tokens <= PROMPT_MAX:
        return observation
        
    # Need to summarize notes.md
    notes_path = Path("/workspace/notes.md")
    if notes_path.exists():
        notes_content = notes_path.read_text()
        
        # Summarize oldest 1000 tokens
        summarized_notes = summarize_notes(notes_content, 1000)
        
        # Write back and commit
        notes_path.write_text(summarized_notes)
        subprocess.run(["git", "add", "notes.md"], cwd="/workspace", capture_output=True)
        subprocess.run(["git", "commit", "-m", f"Summarized notes at turn {turn_number}"], cwd="/workspace", capture_output=True)
        
        # Rebuild observation
        observation = {
            "directory_tree": get_directory_tree(),
            "git_diff": get_git_diff(), 
            "test_results": get_test_results(),
            "requested_files": get_requested_files(),
            "previous_message": get_previous_message()
        }
        
        # Check tokens again
        observation_json = json.dumps(observation, indent=2)
        total_tokens = count_tokens(observation_json)
        
        if total_tokens <= PROMPT_MAX:
            return observation
    
    # Still too large
    return {"error": "prompt_too_large"} 