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
    # Use a more accurate approximation based on Claude's actual tokenizer
    # Claude uses a BPE tokenizer similar to GPT models
    # Average is closer to 1 token per 3.5 characters for English text
    # with code being slightly more dense
    import re
    
    # Count different types of content differently
    # Code tends to have more tokens due to special characters
    code_lines = len([l for l in text.split('\n') if l.strip() and (l.strip().startswith(('def', 'class', 'import', 'from')) or '=' in l or '(' in l)])
    total_lines = len(text.split('\n'))
    code_ratio = code_lines / max(total_lines, 1)
    
    # Adjust character per token ratio based on content type
    if code_ratio > 0.5:
        chars_per_token = 3.2  # Code is denser
    else:
        chars_per_token = 3.8  # Natural language is less dense
        
    # Also count special tokens
    special_tokens = len(re.findall(r'[{}\[\]()<>]', text))
    
    return int(len(text) / chars_per_token) + special_tokens // 10


def get_directory_tree(path: str = "/workspace", max_depth: int = 1) -> str:
    """Get a directory tree up to max_depth, excluding .git and results."""
    def build_tree(current_path: Path, prefix: str = "", depth: int = 0) -> List[str]:
        if depth >= max_depth:
            return []
            
        entries = []
        try:
            items = sorted(current_path.iterdir())
            for i, item in enumerate(items):
                is_last = i == len(items) - 1
                
                # Skip hidden files except .agent_state.json
                # Also skip .git and results directories
                if item.name.startswith('.') and item.name != '.agent_state.json':
                    continue
                if item.name in ['.git', 'results', '__pycache__', '.pytest_cache']:
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
    # Use JSON report for accurate results
    json_report_file = "/tmp/pytest_obs_report.json"
    
    result = subprocess.run(
        ["pytest", "-v", "--tb=no", "--json-report", f"--json-report-file={json_report_file}", "-q"],
        cwd="/workspace",
        capture_output=True,
        text=True
    )
    
    # Parse JSON report if available
    passed = 0
    failed = 0
    failed_tests = []
    
    try:
        if Path(json_report_file).exists():
            with open(json_report_file, 'r') as f:
                report = json.load(f)
                passed = report['summary'].get('passed', 0)
                failed = report['summary'].get('failed', 0)
                
                # Get failed test names from report
                if 'tests' in report:
                    for test in report['tests']:
                        if test.get('outcome') == 'failed':
                            failed_tests.append(test.get('nodeid', 'unknown'))
                            
            Path(json_report_file).unlink(missing_ok=True)
    except Exception:
        # Fallback to parsing output
        lines = result.stdout.splitlines()
        for line in lines:
            if 'passed' in line and 'failed' in line:
                # Parse summary line
                import re
                match = re.search(r'(\d+) passed', line)
                if match:
                    passed = int(match.group(1))
                match = re.search(r'(\d+) failed', line)
                if match:
                    failed = int(match.group(1))
                break
    
    summary = f"Test Summary: {passed} passed, {failed} failed"
    if failed > 0 and failed_tests:
        # Include failed test names
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


def truncate_notes(notes_content: str, max_tokens: int = 2000) -> str:
    """Truncate notes to fit within token budget, keeping most recent content."""
    current_tokens = count_tokens_anthropic(notes_content)
    if current_tokens <= max_tokens:
        return notes_content
        
    # Split by turns and keep most recent
    turns = notes_content.split('\n### Turn ')
    if len(turns) <= 1:
        # No turn markers, just truncate from beginning
        chars_to_keep = int(max_tokens * 3.5)  # Rough approximation
        if len(notes_content) > chars_to_keep:
            return f"[... earlier notes truncated ...]\n{notes_content[-chars_to_keep:]}"
        return notes_content
    
    # Keep the most recent turns that fit
    kept_turns = []
    total_tokens = 0
    
    # Process turns in reverse order (most recent first)
    for i in range(len(turns) - 1, -1, -1):
        turn_content = turns[i]
        if i > 0:  # Add turn header back except for first split
            turn_content = f"\n### Turn {turn_content}"
        turn_tokens = count_tokens_anthropic(turn_content)
        
        if total_tokens + turn_tokens <= max_tokens:
            kept_turns.insert(0, turn_content)
            total_tokens += turn_tokens
        else:
            # Add truncation notice
            kept_turns.insert(0, f"[... earlier turns truncated, showing turns {i+1}-{len(turns)-1} ...]")
            break
            
    return ''.join(kept_turns)


def build_observation(turn_number: int) -> Dict[str, Any]:
    """Build the complete observation for the agent."""
    # First, check if notes.md is getting too large
    notes_path = Path("/workspace/notes.md")
    if notes_path.exists():
        notes_content = notes_path.read_text()
        notes_tokens = count_tokens_anthropic(notes_content)
        
        # If notes are too large, truncate them
        if notes_tokens > 2000:  # Leave room for other observation parts
            truncated = truncate_notes(notes_content, max_tokens=2000)
            # Don't overwrite the file, just use truncated version for observation
            notes_content = truncated
    else:
        notes_content = ""
    
    # Build observation
    observation = {
        "directory_tree": get_directory_tree(max_depth=1),  # Limit depth by default
        "git_diff": get_git_diff(),
        "test_results": get_test_results(),
        "requested_files": get_requested_files(),
        "previous_message": get_previous_message()
    }
    
    # Add truncated notes to observation
    if notes_content:
        observation["notes_preview"] = notes_content
    
    # Convert to JSON and count tokens
    observation_json = json.dumps(observation, indent=2)
    total_tokens = count_tokens_anthropic(observation_json)
    
    if total_tokens <= PROMPT_MAX:
        return observation
        
    # Still too large - return error
    return {"error": "prompt_too_large", "token_count": total_tokens} 