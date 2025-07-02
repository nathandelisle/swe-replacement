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
        # TODO: Implement proper formatting based on observation type
        prompt = "You are a software engineer tasked with fixing failing tests.\n\n"
        
        if "test_results" in observation:
            prompt += f"Current test results:\n{observation['test_results']}\n\n"
            
        if "file_content" in observation:
            prompt += f"File content:\n{observation['file_content']}\n\n"
            
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
- read_file: Read the contents of a file
- write_file: Write content to a file
- apply_patch: Apply a unified diff patch to a file
- run_tests: Run pytest on the project
- list_directory: List contents of a directory

Always think through your approach in the scratchpad before taking action.""" 