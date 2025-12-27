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
        base_prompt = f"""You are tasked with analyzing a HAR (HTTP Archive) file to reverse engineer API calls and generate production-ready Python code that replicates those calls.

Here is the HAR file path you need to analyze:
<har_path>
{self.har_path}
</har_path>

Here is the original user prompt with context about what they're trying to accomplish:
<user_prompt>
{self.prompt}
</user_prompt>

Here is the output directory where you should save your generated files:
<output_dir>
{self.scripts_dir}
</output_dir>

Your task is to:

1. **Read and analyze the HAR file** to understand all API calls that were captured. Look for:
   - HTTP methods (GET, POST, PUT, DELETE, etc.)
   - Request URLs and endpoints
   - Request headers (especially authentication-related ones)
   - Request bodies and parameters
   - Response structures
   - Response status codes

2. **Identify authentication patterns** such as:
   - Cookies and session tokens
   - Authorization headers (Bearer tokens, API keys, etc.)
   - CSRF tokens or other security mechanisms
   - Custom authentication headers

3. **Extract request/response patterns** for each distinct endpoint:
   - Required vs optional parameters
   - Data formats (JSON, form data, etc.)
   - Query parameters vs body parameters
   - Response data structures

4. **Generate a Python script** that replicates these API calls with the following requirements:
   - Use the `requests` library as the default choice
   - Include proper authentication handling (sessions, headers, tokens)
   - Create separate functions for each distinct API endpoint
   - Include type hints for all function parameters and return values
   - Write comprehensive docstrings for each function
   - Implement proper error handling with try-except blocks
   - Add logging for debugging purposes
   - Make the code production-ready and maintainable
   - Include a main section with example usage

5. **Create documentation**:
   - Generate a README.md file that explains:
     - What APIs were discovered
     - How authentication works
     - How to use each function
     - Example usage
     - Any limitations or requirements

6. **Test your implementation**:
   - After generating the code, test it to ensure it works
   - You have up to 5 attempts to fix any issues
   - If the initial implementation fails, analyze the error and try again
   - Keep in mind that some websites have bot detection mechanisms

7. **Handle bot detection**:
   - If you encounter bot detection, CAPTCHA, or anti-scraping measures with `requests`
   - Consider switching to Playwright with CDP (Chrome DevTools Protocol)
   - Use the real user browser context to bypass detection
   - Maintain the same code quality standards regardless of approach

Before generating your code, use a scratchpad to plan your approach:

<scratchpad>
In your scratchpad:
- Summarize the key API endpoints found in the HAR file
- Note the authentication mechanism being used
- Identify any patterns or commonalities between requests
- Plan the structure of your Python script
- Consider potential issues (rate limiting, bot detection, etc.)
- Decide whether `requests` will be sufficient or if Playwright is needed
</scratchpad>

After your analysis, generate the files:

1. Save the Python script to: {self.scripts_dir}/api_client.py
2. Save the documentation to: {self.scripts_dir}/README.md

If your first attempt doesn't work, analyze what went wrong and try again. Document each attempt and what you learned.

<attempt_log>
For each attempt (up to 5), document:
- Attempt number
- What approach you tried
- What error or issue occurred (if any)
- What you changed for the next attempt
</attempt_log>

After testing, provide your final response with:
- A summary of the APIs discovered
- The authentication method used
- Whether the implementation works
- Any limitations or caveats
- The paths to the generated files

Your final output should confirm that the files have been created and provide a brief summary of what was accomplished. Do not include the full code in your response - just confirm the files were saved and summarize the key findings.
"""
        if self.additional_instructions:
            base_prompt += f"\n\nAdditional instructions:\n{self.additional_instructions}"
        
        return base_prompt

    @abstractmethod
    async def analyze_and_generate(self) -> Optional[Dict[str, Any]]:
        """Run the reverse engineering analysis. Must be implemented by subclasses."""
        pass
