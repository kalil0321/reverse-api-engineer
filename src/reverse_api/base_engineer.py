"""Abstract base class for API reverse engineering."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .messages import MessageStore
from .sync import FileSyncWatcher, get_available_directory
from .tui import ClaudeUI
from .utils import generate_folder_name, get_scripts_dir


class BaseEngineer(ABC):
    """Abstract base class for API reverse engineering implementations."""

    def __init__(
        self,
        run_id: str,
        har_path: Path,
        prompt: str,
        model: str | None = None,
        additional_instructions: str | None = None,
        output_dir: str | None = None,
        verbose: bool = True,
        enable_sync: bool = False,
        sdk: str = "claude",
        is_fresh: bool = False,
    ):
        self.run_id = run_id
        self.har_path = har_path
        self.prompt = prompt
        self.model = model
        self.additional_instructions = additional_instructions
        self.scripts_dir = get_scripts_dir(run_id, output_dir)
        self.ui = ClaudeUI(verbose=verbose)
        self.usage_metadata: dict[str, Any] = {}
        self.message_store = MessageStore(run_id, output_dir)
        self.enable_sync = enable_sync
        self.sdk = sdk
        self.is_fresh = is_fresh
        self.sync_watcher: FileSyncWatcher | None = None
        self.local_scripts_dir: Path | None = None

    def start_sync(self):
        """Start real-time file sync if enabled."""
        if not self.enable_sync:
            return

        # Generate local directory name
        base_name = generate_folder_name(self.prompt, sdk=self.sdk)
        scripts_base_path = Path.cwd() / "scripts"

        # Get available directory (won't overwrite existing non-empty dirs)
        local_dir = get_available_directory(scripts_base_path, base_name)

        self.local_scripts_dir = local_dir

        # Create sync watcher
        def on_sync(message):
            self.ui.sync_flash(message)

        def on_error(message):
            self.ui.sync_error(message)

        self.sync_watcher = FileSyncWatcher(
            source_dir=self.scripts_dir,
            dest_dir=local_dir,
            on_sync=on_sync,
            on_error=on_error,
            debounce_ms=500,
        )
        self.sync_watcher.start()
        self.ui.sync_started(str(local_dir))

    def stop_sync(self):
        """Stop real-time file sync."""
        if self.sync_watcher:
            try:
                self.sync_watcher.stop()
            except Exception as e:
                self.ui.sync_error(f"Failed to stop sync watcher: {e}")
            finally:
                self.sync_watcher = None

    def get_sync_status(self) -> dict | None:
        """Get current sync status."""
        if self.sync_watcher:
            return self.sync_watcher.get_status()
        return None

    def _build_analysis_prompt(self) -> str:
        """Build the prompt for analyzing the HAR file."""
        base_prompt = f"""You are tasked with analyzing a HAR (HTTP Archive) file to reverse engineer API calls,
         and generate production-ready Python code that replicates those calls.

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

**IMPORTANT: You have access to the AskUserQuestion tool to ask clarifying questions during your analysis.**
Use this tool when you need to clarify functional requirements, prioritize features, choose between implementation approaches, or gather any other information that would help you generate better code.

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

4. **Ask clarifying questions using AskUserQuestion** if needed:
   - When multiple authentication methods are found, ask which to prioritize
   - If uncertain about feature priorities, ask the user
   - When implementation approaches are ambiguous, ask for preferences
   - Use the tool for any clarifications that would improve the final code

5. **Generate a Python script** that replicates these API calls with the following requirements:
   - Use the `requests` library as the default choice
   - Include proper authentication handling (sessions, headers, tokens)
   - Create separate functions for each distinct API endpoint
   - Include type hints for all function parameters and return values
   - Write comprehensive docstrings for each function
   - Implement proper error handling with try-except blocks
   - Add logging for debugging purposes
   - Make the code production-ready and maintainable
   - Include a main section with example usage

6. **Create documentation**:
   - Generate a README.md file that explains:
     - What APIs were discovered
     - How authentication works
     - How to use each function
     - Example usage
     - Any limitations or requirements

7. **Test your implementation**:
   - After generating the code, test it to ensure it works
   - You have up to 5 attempts to fix any issues
   - If the initial implementation fails, analyze the error and try again
   - Keep in mind that some websites have bot detection mechanisms

8. **Handle bot detection**:
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
- Identify any ambiguities or questions you should ask the user using AskUserQuestion
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

Your final output should confirm that the files have been created and provide a brief summary of what was accomplished.
Do not include the full code in your response - just confirm the files were saved and summarize the key findings.
"""
        if self.additional_instructions:
            base_prompt += f"\n\nAdditional instructions:\n{self.additional_instructions}"

        # Add AskUserQuestion tool guidance
        base_prompt += """

## Interactive Clarification with AskUserQuestion

You have access to the `AskUserQuestion` tool to ask clarifying questions during analysis:

<ask_user_question_guidelines>
Use AskUserQuestion when uncertain about:
- Functional requirements or expected behavior
- Which features to prioritize
- Implementation approach choices
- API authentication details the user might know
- Specific use cases or workflows to support

The tool accepts a list of questions with the following structure:

```json
{
  "questions": [
    {
      "question": "Which authentication should I prioritize?",
      "header": "Authentication",
      "options": [
        {"label": "Cookie-based session", "description": "Uses session cookies for auth"},
        {"label": "Bearer token", "description": "Uses JWT or API tokens"},
        {"label": "Both", "description": "Auto-detect and support both methods"}
      ],
      "multiSelect": false
    }
  ]
}
```

Question Structure:
- `question` (required): The question text
- `header` (optional): Short category label for context
- `options` (required): List of choices with labels and descriptions
- `multiSelect` (optional): true for checkbox selection, false for single select (default: false)

Examples:

1. Single-select question (authentication method):
```json
{
  "questions": [{
    "question": "Which authentication method should I implement?",
    "header": "Auth Method",
    "options": [
      {"label": "Cookie-based", "description": "Session cookies"},
      {"label": "Bearer token", "description": "JWT tokens"},
      {"label": "Both", "description": "Support both methods"}
    ],
    "multiSelect": false
  }]
}
```

2. Multi-select question (features):
```json
{
  "questions": [{
    "question": "Which features should I include?",
    "header": "Features",
    "options": [
      {"label": "Retry logic", "description": "Auto-retry failed requests"},
      {"label": "Rate limiting", "description": "Throttle requests"},
      {"label": "Caching", "description": "Cache responses"}
    ],
    "multiSelect": true
  }]
}
```

3. Multiple questions in one call:
```json
{
  "questions": [
    {
      "question": "Which authentication method?",
      "header": "Auth",
      "options": [
        {"label": "Cookies", "description": "Session-based"},
        {"label": "Tokens", "description": "Token-based"}
      ],
      "multiSelect": false
    },
    {
      "question": "Which features to enable?",
      "header": "Features",
      "options": [
        {"label": "Retry", "description": "Auto-retry"},
        {"label": "Logging", "description": "Debug logs"}
      ],
      "multiSelect": true
    }
  ]
}
```

Guidelines:
- Ask 1-3 well-targeted questions that materially impact implementation
- Always provide `options` with clear labels and descriptions
- Use `multiSelect: true` when multiple options can be selected
- Use meaningful `header` values to provide context
- The user's answers will be returned in the tool result
</ask_user_question_guidelines>
"""

        tag_context = f"""
## Tag-Based Workflows

This session uses tag-based context loading:

- **@id <run_id>**: Re-engineer mode active
  - Target run: {self.run_id}
  - HAR location: {self.har_path.parent}
  - Existing scripts: {self.scripts_dir}
  - Message history: {self.message_store.messages_path.parent} (available for reference if needed)
  - Fresh mode: {str(self.is_fresh).lower()}

By default, treat this as an iterative refinement. The user's prompt describes
changes or improvements to make to the existing script. If fresh mode is enabled,
ignore previous implementation and start from scratch.

Note: Full message history is available at the messages path above if you need
to understand previous context, but it is not automatically loaded into this
conversation.
"""
        return base_prompt + tag_context

    @abstractmethod
    async def analyze_and_generate(self) -> dict[str, Any] | None:
        """Run the reverse engineering analysis. Must be implemented by subclasses."""
        pass
