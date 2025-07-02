"""
Minimal Claude API client for agent interaction.
"""
import os
import time
from typing import Dict, Any, Optional
import anthropic


class ClaudeClient:
    def __init__(self):
        """Initialize the Claude client."""
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
            
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-3-opus-20240229"  # Or another model
        self.max_tokens = 4096
        
    def send_prompt(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Send a prompt to Claude and get the response.
        
        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            
        Returns:
            The model's response text
        """
        try:
            messages = [{"role": "user", "content": prompt}]
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=messages,
                system=system_prompt if system_prompt else None
            )
            
            return response.content[0].text
            
        except Exception as e:
            raise Exception(f"Failed to get response from Claude: {str(e)}")
            
    def format_observation_prompt(self, observation: Dict[str, Any]) -> str:
        """
        Format an observation into a prompt for the agent.
        
        Args:
            observation: The observation data
            
        Returns:
            Formatted prompt string
        """
        # Format the observation dict as a clear prompt
        prompt = "Current observation:\n\n"
        prompt += f"Directory tree:\n{observation.get('directory_tree', 'N/A')}\n\n"
        prompt += f"Git diff:\n{observation.get('git_diff', 'No changes')}\n\n"
        prompt += f"Test results:\n{observation.get('test_results', 'No test results')}\n\n"
        
        if observation.get('previous_message'):
            prompt += f"Previous message from yourself: {observation['previous_message']}\n\n"
            
        prompt += """Please analyze the situation and take an action.

You must respond in the following format:
<scratchpad>
Your analysis and thoughts here...
</scratchpad>
ACTION: {"action_type": "...", ...}
"""
        
        return prompt
        
    def get_system_prompt(self) -> str:
        """Get the system prompt for the agent."""
        return """You are an AI software engineer working on a Python project. Your goal is to make all tests pass.

You have access to the following actions:
- read_files: Read the contents of multiple files
- patch: Apply a unified diff patch to modify files
- run_tests: Run pytest on the project
- list_directory: List contents of a directory
- write_notes: Overwrite the entire notes.md file

You also have a persistent "notes.md" file in the project root.
• Everything you write in the <scratchpad> is appended there automatically.
• You may read that file with read_files.
• You may overwrite it entirely by returning {"write_notes": "<full new text>"}.
You may send a short string forward to your next self using the "message" field.

Always think through your approach in the scratchpad before taking action.""" 