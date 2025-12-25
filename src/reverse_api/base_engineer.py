"""Abstract base class for API reverse engineering."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, Any

from .utils import get_scripts_dir, get_timestamp
from .tui import ClaudeUI
from .messages import MessageStore


class BaseEngineer(ABC):
    """Abstract base class for API reverse engineering implementations."""

    def __init__(
        self,
        run_id: str,
        har_path: Path,
        prompt: str,
        model: Optional[str] = None,
        additional_instructions: Optional[str] = None,
        output_dir: Optional[str] = None,
        verbose: bool = True,
    ):
        self.run_id = run_id
        self.har_path = har_path
        self.prompt = prompt
        self.model = model
        self.additional_instructions = additional_instructions
        self.scripts_dir = get_scripts_dir(run_id, output_dir)
        self.ui = ClaudeUI(verbose=verbose)
        self.usage_metadata: Dict[str, Any] = {}
        self.message_store = MessageStore(run_id, output_dir)

    def _build_analysis_prompt(self) -> str:
        """Build the prompt for analyzing the HAR file."""
        base_prompt = f"""Analyze the HAR file at {self.har_path} and reverse engineer the APIs captured.

Original user prompt: {self.prompt}

Your task:
1. Read and analyze the HAR file to understand the API calls made
2. Identify authentication patterns (cookies, tokens, headers)
3. Extract request/response patterns for each endpoint
4. Generate a clean, well-documented Python script that replicates these API calls

The Python script should:
- Use the `requests` library
- Include proper authentication handling
- Have functions for each distinct API endpoint
- Include type hints and docstrings
- Handle errors gracefully
- Be production-ready

Save the generated Python script to: {self.scripts_dir / 'api_client.py'}
Also create a brief README.md in the same folder explaining the APIs discovered.
Always test your implementation to ensure it works. If it doesn't try again if you think you can fix it. You can go up to 5 attempts.
Sometimes websites have bot detection and that kind of things so keep in mind.
If you see you can't achieve with requests, feel free to use playwright with the real user browser with CDP to bypass bot detection.
No matter which implementation you choose, always try to make it production ready and test it.
"""
        if self.additional_instructions:
            base_prompt += f"\n\nAdditional instructions:\n{self.additional_instructions}"
        
        return base_prompt

    @abstractmethod
    async def analyze_and_generate(self) -> Optional[Dict[str, Any]]:
        """Run the reverse engineering analysis. Must be implemented by subclasses."""
        pass
