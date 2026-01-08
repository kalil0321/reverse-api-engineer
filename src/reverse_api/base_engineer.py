"""Abstract base class for API reverse engineering."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .messages import MessageStore
from .sync import FileSyncWatcher, get_available_directory
from .tui import ClaudeUI
from .utils import generate_folder_name, get_docs_dir, get_scripts_dir


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
        output_language: str = "python",
        output_mode: str = "client",
    ):
        self.run_id = run_id
        self.har_path = har_path
        self.prompt = prompt
        self.model = model
        self.additional_instructions = additional_instructions
        self.output_mode = output_mode

        # Select output directory based on mode
        if output_mode == "docs":
            self.scripts_dir = get_docs_dir(run_id, output_dir)
        else:
            self.scripts_dir = get_scripts_dir(run_id, output_dir)

        self.ui = ClaudeUI(verbose=verbose)
        self.usage_metadata: dict[str, Any] = {}
        self.message_store = MessageStore(run_id, output_dir)
        self.enable_sync = enable_sync
        self.sdk = sdk
        self.is_fresh = is_fresh
        self.output_language = output_language
        self.sync_watcher: FileSyncWatcher | None = None
        self.local_scripts_dir: Path | None = None

    def start_sync(self):
        """Start real-time file sync if enabled."""
        if not self.enable_sync:
            return

        # Generate local directory name
        base_name = generate_folder_name(self.prompt, sdk=self.sdk)

        # Choose base path based on output mode
        if self.output_mode == "docs":
            base_path = Path.cwd() / "docs"
        else:
            base_path = Path.cwd() / "scripts"

        # Get available directory (won't overwrite existing non-empty dirs)
        local_dir = get_available_directory(base_path, base_name)

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

    def _get_output_extension(self) -> str:
        """Return file extension based on output language."""
        return {
            "python": ".py",
            "javascript": ".js",
            "typescript": ".ts",
        }.get(self.output_language, ".py")

    def _get_client_filename(self) -> str:
        """Return the output filename based on mode."""
        if self.output_mode == "docs":
            return "openapi.json"
        return f"api_client{self._get_output_extension()}"

    def _get_run_command(self) -> str:
        """Return the command to run the generated client."""
        return {
            "python": "python api_client.py",
            "javascript": "node api_client.js",
            "typescript": "npx tsx api_client.ts",
        }.get(self.output_language, "python api_client.py")

    def _get_language_instructions(self) -> str:
        """Return language-specific code generation instructions."""
        client_filename = self._get_client_filename()
        run_command = self._get_run_command()

        if self.output_language == "javascript":
            return f"""4. **Generate a JavaScript module** that replicates these API calls with the following requirements:
   - Use modern JavaScript (ES2022+) with ESM modules (import/export)
   - Use native `fetch` API for HTTP requests (Node.js 18+ built-in)
   - If advanced features are needed (retries, interceptors), use `axios` instead
   - Include proper authentication handling (sessions, headers, tokens)
   - Create separate async functions for each distinct API endpoint
   - Use JSDoc comments for type documentation on all functions
   - Implement proper error handling with try-catch blocks
   - Create custom Error classes for API errors
   - Add console logging for debugging purposes
   - Make the code production-ready and maintainable
   - Include a main section with example usage (wrapped in async IIFE or top-level await)
   - If using external dependencies (like axios), generate a package.json with:
     - "type": "module" for ESM support
     - Required dependencies
     - scripts: {{ "start": "node api_client.js" }}

5. **Create documentation**:
   - Generate a README.md file that explains:
     - What APIs were discovered
     - How authentication works
     - How to use each function
     - Example usage
     - Requirements: Node.js 18+
     - Any limitations or requirements

6. **Test your implementation**:
   - If package.json was generated, first run: npm install
   - Run with: {run_command}
   - You have up to 5 attempts to fix any issues
   - If the initial implementation fails, analyze the error and try again

After your analysis, generate the files:

1. Save the JavaScript module to: {self.scripts_dir}/{client_filename}
2. Save the documentation to: {self.scripts_dir}/README.md
3. If external dependencies are used, save: {self.scripts_dir}/package.json"""

        elif self.output_language == "typescript":
            return f"""4. **Generate a TypeScript module** that replicates these API calls with the following requirements:
   - Use TypeScript with strict typing enabled
   - Use ESM modules (import/export syntax)
   - Use native `fetch` API for HTTP requests (Node.js 18+ built-in)
   - If advanced features are needed (retries, interceptors), use `axios` instead
   - Define TypeScript interfaces for all request/response types
   - Include proper authentication handling (sessions, headers, tokens)
   - Create separate async functions for each distinct API endpoint
   - Use async/await patterns throughout
   - Export a class-based API client with proper encapsulation
   - Implement proper error handling with custom error types
   - Add console logging for debugging purposes
   - Make the code production-ready and maintainable
   - Include a main section with example usage
   - Generate a package.json with:
     - "type": "module" for ESM support
     - devDependencies: tsx, typescript, @types/node
     - dependencies: axios (only if used)
     - scripts: {{ "start": "npx tsx api_client.ts" }}

5. **Create documentation**:
   - Generate a README.md file that explains:
     - What APIs were discovered
     - How authentication works
     - How to use each function
     - Example usage
     - Requirements: Node.js 18+
     - Any limitations or requirements

6. **Test your implementation**:
   - Run: npm install && {run_command}
   - npx auto-downloads tsx if not installed
   - You have up to 5 attempts to fix any issues
   - If the initial implementation fails, analyze the error and try again

After your analysis, generate the files:

1. Save the TypeScript module to: {self.scripts_dir}/{client_filename}
2. Save the documentation to: {self.scripts_dir}/README.md
3. Save the package.json to: {self.scripts_dir}/package.json"""

        else:  # python (default)
            return f"""4. **Generate a Python script** that replicates these API calls with the following requirements:
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
   - Run with: {run_command}
   - You have up to 5 attempts to fix any issues
   - If the initial implementation fails, analyze the error and try again
   - Keep in mind that some websites have bot detection mechanisms

7. **Handle bot detection**:
   - If you encounter bot detection, CAPTCHA, or anti-scraping measures with `requests`
   - Consider switching to Playwright with CDP (Chrome DevTools Protocol)
   - Use the real user browser context to bypass detection
   - Maintain the same code quality standards regardless of approach

After your analysis, generate the files:

1. Save the Python script to: {self.scripts_dir}/{client_filename}
2. Save the documentation to: {self.scripts_dir}/README.md"""

    def _get_docs_instructions(self) -> str:
        """Return OpenAPI documentation generation instructions."""
        return f"""4. **Generate an OpenAPI 3.0 specification** that documents these API endpoints:
   - Use OpenAPI 3.0.0 format (https://swagger.io/specification/)
   - Include all discovered endpoints with:
     - Correct HTTP methods (GET, POST, PUT, DELETE, etc.)
     - Path parameters and query parameters
     - Request body schemas (JSON Schema format)
     - Response schemas for common status codes (200, 400, 401, 404, 500)
     - Authentication/security schemes (API keys, Bearer tokens, OAuth, etc.)
   - Organize endpoints into logical tags/groups (e.g., "Users", "Products", "Orders")
   - Infer meaningful descriptions for:
     - Each endpoint's purpose (what it does)
     - Parameters (what they control)
     - Response fields (what they represent)
   - Include examples where patterns are clear from the HAR data
   - Use JSON Schema $ref for shared components/schemas
   - Document authentication requirements in security schemes
   - Add a servers array with the base URL from the HAR file

5. **Enhance documentation with AI inference**:
   - Analyze request/response patterns to infer parameter types and constraints
   - Group related endpoints into logical operations
   - Generate human-readable descriptions (not just field names)
   - Identify required vs optional parameters based on HAR observations
   - Add example values from actual captured requests
   - Document error responses observed in the HAR
   - Note rate limiting headers if present
   - Describe authentication flow if multi-step

6. **Create supplementary documentation**:
   - Generate a README.md file that explains:
     - API overview and purpose
     - Authentication method and how to obtain credentials
     - Base URL and versioning
     - Common use cases with example requests
     - Rate limiting information (if observed)
     - Any special headers or requirements
     - Link to view the OpenAPI spec (e.g., in Swagger UI)

After your analysis, generate the files:

1. Save the OpenAPI spec to: {self.scripts_dir}/openapi.json
2. Save the README to: {self.scripts_dir}/README.md
3. Optionally create: {self.scripts_dir}/examples.md with curl examples

Your OpenAPI spec should be production-ready and suitable for:
- API documentation portals (Swagger UI, Redoc, Stoplight)
- Code generation (OpenAPI Generator, swagger-codegen)
- API testing (Postman, Insomnia)
- Contract testing and validation"""

    def _build_analysis_prompt(self) -> str:
        """Build the prompt for analyzing the HAR file."""
        if self.output_mode == "docs":
            mode_description = "generate an OpenAPI 3.0 specification documenting"
            task_description = "OpenAPI documentation"
        else:
            language_name = {
                "python": "Python",
                "javascript": "JavaScript",
                "typescript": "TypeScript",
            }.get(self.output_language, "Python")
            mode_description = f"reverse engineer API calls and generate production-ready {language_name} code that replicates"
            task_description = f"{language_name} API client"

        base_prompt = f"""You are tasked with analyzing a HAR (HTTP Archive) file to {mode_description} those calls.

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
Use this tool when you need to clarify functional requirements, prioritize features, choose between implementation approaches, or gather any other information that would help you generate better {task_description}.

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
   - Use the tool for any clarifications that would improve the final output

{self._get_docs_instructions() if self.output_mode == "docs" else self._get_language_instructions()}

Before generating your output, use a scratchpad to plan your approach:

<scratchpad>
In your scratchpad:
- Summarize the key API endpoints found in the HAR file
- Note the authentication mechanism being used
- Identify any patterns or commonalities between requests
- Plan the structure of your {task_description}
- Consider potential issues (rate limiting, versioning, etc.)
{"- Decide whether `requests` will be sufficient or if Playwright is needed" if self.output_mode != "docs" else ""}
- Identify any ambiguities or questions you should ask the user using AskUserQuestion
</scratchpad>

{"" if self.output_mode == "docs" else """If your first attempt doesn't work, analyze what went wrong and try again. Document each attempt and what you learned.

<attempt_log>
For each attempt (up to 5), document:
- Attempt number
- What approach you tried
- What error or issue occurred (if any)
- What you changed for the next attempt
</attempt_log>

"""}After {"documenting" if self.output_mode == "docs" else "testing"}, provide your final response with:
- A summary of the APIs discovered
- The authentication method used
- {"The completeness and accuracy of the OpenAPI spec" if self.output_mode == "docs" else "Whether the implementation works"}
- Any limitations or caveats
- The paths to the generated files

Your final output should confirm that the files have been created and provide a brief summary of what was accomplished.
Do not include the full {"spec" if self.output_mode == "docs" else "code"} in your response - just confirm the files were saved and summarize the key findings.
"""
        if self.additional_instructions:
            base_prompt += f"\n\nAdditional instructions:\n{self.additional_instructions}"

        tag_context = f"""
## Tag-Based Workflows

This session uses tag-based context loading:

- **@id <run_id>** {"@docs" if self.output_mode == "docs" else ""}: {"Documentation" if self.output_mode == "docs" else "Re-engineer"} mode active
  - Target run: {self.run_id}
  - HAR location: {self.har_path.parent}
  - Existing {"docs" if self.output_mode == "docs" else "scripts"}: {self.scripts_dir}
  - Message history: {self.message_store.messages_path.parent} (available for reference if needed)
  - Fresh mode: {str(self.is_fresh).lower()}

By default, treat this as an iterative refinement. The user's prompt describes
changes or improvements to make to the existing {"documentation" if self.output_mode == "docs" else "script"}. If fresh mode is enabled,
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
