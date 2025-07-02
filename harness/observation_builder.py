"""
Build observations for the agent with token counting and summarization.
"""
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional


PROMPT_MAX = 8000  # Maximum tokens for prompt


def count_tokens_anthropic(text: str) -> int:
    """Count tokens using Anthropic's method."""
    # Anthropic uses roughly 4 characters per token as an approximation
    # For more accurate counting, we should use their API
    from claude_client import ClaudeClient
    client = ClaudeClient()
    return client.count_tokens(text)


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
                    size = item.stat().st_size
                    entries.append(f"{prefix}{connector}{item.name} ({size} bytes)")
        except PermissionError:
            pass
            
        return entries
    
    tree_lines = build_tree(Path(path))
    return "\n".join(tree_lines)


def get_git_diff() -> str:
    """Get git diff since previous commit."""
    # Only show the last commit's changes to avoid huge diffs
    result = subprocess.run(
        ["git", "diff", "HEAD~1", "HEAD", "--stat"],
        cwd="/workspace",
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        # Might be first commit
        result = subprocess.run(
            ["git", "show", "--stat"],
            cwd="/workspace",
            capture_output=True,
            text=True
        )
    
    return result.stdout if result.returncode == 0 else "No git diff available"


def get_test_results() -> str:
    """Get current pytest results summary."""
    result = subprocess.run(
        ["pytest", "-v", "--tb=no", "-q"],
        cwd="/workspace",
        capture_output=True,
        text=True
    )
    
    # Just return a summary to save tokens
    lines = result.stdout.splitlines()
    passed = len([l for l in lines if " PASSED" in l])
    failed = len([l for l in lines if " FAILED" in l])
    
    summary = f"Test Summary: {passed} passed, {failed} failed"
    if failed > 0:
        # Include failed test names
        failed_tests = [l.split()[0] for l in lines if " FAILED" in l]
        summary += f"\nFailed tests: {', '.join(failed_tests[:5])}"
        if len(failed_tests) > 5:
            summary += f" ... and {len(failed_tests) - 5} more"
    
    return summary


def get_requested_files() -> Dict[str, str]:
    """Get contents of commonly needed files."""
    # Empty - agent will request files as needed
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


def summarize_notes(notes_content: str, target_tokens: int = 150) -> str:
    """Summarize notes using Claude to fit within token budget."""
    from claude_client import ClaudeClient
    
    client = ClaudeClient()
    
    # Check current token count
    current_tokens = count_tokens_anthropic(notes_content)
    if current_tokens <= 1000:
        return notes_content
        
    # Find first ~1000 tokens to summarize
    words = notes_content.split()
    chunk_size = int(1000 * len(words) / current_tokens)  # Approximate
    chunk_to_summarize = ' '.join(words[:chunk_size])
    remaining = ' '.join(words[chunk_size:])
    
    prompt = f"""Summarize the following developer notes into approximately {target_tokens} tokens. 
Keep exact code references, function names, and specific technical details.
Focus on: what was tried, what worked/failed, and current state.

Notes to summarize:
{chunk_to_summarize}"""
    
    try:
        summary = client.send_prompt(
            prompt, 
            system_prompt="You are a technical summarizer. Be extremely concise while preserving key technical details."
        )
        
        return f"[SUMMARIZED NOTES (turns 1-{chunk_size//100})]:\n{summary}\n\n[RECENT NOTES]:\n{remaining}"
    except Exception as e:
        # If summarization fails, just truncate
        return notes_content[:4000] + "\n\n[... older notes truncated for space ...]"


def build_observation(turn_number: int) -> Dict[str, Any]:
    """Build the complete observation for the agent."""
    # First, check if notes.md is getting too large
    notes_path = Path("/workspace/notes.md")
    if notes_path.exists():
        notes_content = notes_path.read_text()
        notes_tokens = count_tokens_anthropic(notes_content)
        
        # If notes are too large, summarize first
        if notes_tokens > 3000:  # Leave room for other observation parts
            summarized = summarize_notes(notes_content)
            notes_path.write_text(summarized)
            
            # Commit the summarization
            subprocess.run(["git", "add", "notes.md"], cwd="/workspace", capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", f"Summarized notes at turn {turn_number}"], 
                cwd="/workspace", 
                capture_output=True
            )
    
    # Build observation
    observation = {
        "directory_tree": get_directory_tree(),
        "git_diff": get_git_diff(),
        "test_results": get_test_results(),
        "requested_files": get_requested_files(),
        "previous_message": get_previous_message()
    }
    
    # Convert to JSON and count tokens
    observation_json = json.dumps(observation, indent=2)
    total_tokens = count_tokens_anthropic(observation_json)
    
    if total_tokens <= PROMPT_MAX:
        return observation
    
    # Try to reduce by limiting directory tree depth
    observation["directory_tree"] = get_directory_tree(max_depth=1)
    observation_json = json.dumps(observation, indent=2)
    total_tokens = count_tokens_anthropic(observation_json)
    
    if total_tokens <= PROMPT_MAX:
        return observation
        
    # Still too large - return error
    return {"error": "prompt_too_large", "token_count": total_tokens} 