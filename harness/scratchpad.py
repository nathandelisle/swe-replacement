"""
Parser for extracting scratchpad content from agent responses.
"""
import re
from typing import Tuple, Optional


def parse_scratchpad(response: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse the agent response to extract scratchpad content and action.
    
    Expected format:
    <scratchpad>
    ... agent thoughts ...
    </scratchpad>
    ACTION: {json action}
    
    Returns:
        Tuple of (scratchpad_content, action_json_string)
    """
    # Extract scratchpad content
    scratchpad_pattern = r'<scratchpad>(.*?)</scratchpad>'
    scratchpad_match = re.search(scratchpad_pattern, response, re.DOTALL)
    
    scratchpad_content = None
    if scratchpad_match:
        scratchpad_content = scratchpad_match.group(1).strip()
    
    # Extract ACTION line
    action_pattern = r'ACTION:\s*({.*})'
    action_match = re.search(action_pattern, response, re.DOTALL)
    
    action_json = None
    if action_match:
        action_json = action_match.group(1).strip()
        
    return scratchpad_content, action_json


def validate_response_format(response: str) -> bool:
    """
    Validate that the response follows the expected format.
    
    Returns:
        True if valid, False otherwise
    """
    has_scratchpad = '<scratchpad>' in response and '</scratchpad>' in response
    has_action = 'ACTION:' in response
    
    return has_scratchpad and has_action 