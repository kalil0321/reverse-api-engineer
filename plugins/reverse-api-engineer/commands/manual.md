---
description: Launch browser with HAR recording, capture traffic manually, then generate Python API client
argument-hint: "[task] [url]"
allowed-tools: ["MCP:rae-playwright-mcp", "Read", "Write", "Bash"]
---

# Manual Mode - Browser Capture and API Generation

Launch a browser with HAR recording enabled. The user will navigate manually to trigger the desired API calls. When the browser closes, analyze the captured HAR file and generate a production-ready Python API client.

## Prerequisites

Ensure the `reverse-engineering-api` skill is loaded for guidance on HAR analysis and code generation.

## Command Arguments

- `task` (optional): Description of what to reverse engineer (e.g., "fetch Apple jobs", "scrape product data")
- `url` (optional): Starting URL for the browser

If arguments are not provided, prompt the user interactively.

## Task Tracking

Before starting the workflow, create a todo list to track progress:

```python
TodoWrite([
  {"content": "Launch browser with HAR recording", "status": "pending", "activeForm": "Launching browser"},
  {"content": "Wait for user to complete manual navigation", "status": "pending", "activeForm": "Recording traffic"},
  {"content": "Verify HAR capture", "status": "pending", "activeForm": "Verifying HAR file"},
  {"content": "Filter HAR using har_filter.py", "status": "pending", "activeForm": "Filtering HAR"},
  {"content": "Analyze HAR using har_analyze.py", "status": "pending", "activeForm": "Analyzing endpoints"},
  {"content": "Generate API client", "status": "pending", "activeForm": "Generating code"},
  {"content": "Validate code using har_validate.py", "status": "pending", "activeForm": "Validating code"},
  {"content": "Test implementation", "status": "pending", "activeForm": "Testing API client"},
  {"content": "Generate documentation", "status": "pending", "activeForm": "Writing README"}
])
```

**CRITICAL:** Mark each task as `in_progress` when starting, `completed` when done. NEVER skip tasks - complete all 9 steps.

## Workflow

### Step 1: Gather Task Information

If `task` argument is not provided:
```
Ask: "What would you like to reverse engineer? (e.g., 'fetch job listings from Company X')"
```

If `url` argument is not provided:
```
Ask: "What URL should I open? (optional, press Enter to skip)"
```

### Step 2: Generate Run ID and Setup Paths

Generate a unique run ID using UUID format:
```
run_id = uuid4() (e.g., "abc-123-def-456")
```

Setup paths:
```
har_dir = ~/.reverse-api/runs/har/{run_id}/
har_path = {har_dir}/recording.har
```

Ensure directory exists:
```bash
mkdir -p ~/.reverse-api/runs/har/{run_id}/
```

### Step 3: Launch Browser with HAR Recording

Use the Playwright MCP `rae-playwright-mcp` to launch a browser with HAR recording:

```
Call MCP tool: playwright_navigate
Parameters:
  - url: {url} or "about:blank" if no URL provided
  - options:
      - record_har: true
      - har_path: ~/.reverse-api/runs/har/{run_id}/recording.har
```

Inform the user:
```
Browser launched with HAR recording enabled.
Navigate to the website and interact with it to trigger API calls.
Close the browser when you're done to proceed with analysis.

HAR will be saved to: ~/.reverse-api/runs/har/{run_id}/recording.har
```

### Step 4: Wait for Browser to Close

Monitor the browser session. When it closes, the HAR file will be saved automatically.

Verify HAR file exists:
```bash
ls -lh ~/.reverse-api/runs/har/{run_id}/recording.har
```

If file doesn't exist or is empty:
```
Error: "HAR file not found or empty. Please ensure you interacted with the website before closing the browser."
Exit with error
```

### Step 5: Analyze HAR File

**Mark todo in_progress: "Filter HAR using har_filter.py"**

Filter the HAR file to remove static assets, analytics, and CDN resources:

```bash
python plugins/reverse-api-engineer/skills/reverse-engineering-api/scripts/har_filter.py ~/.reverse-api/runs/har/{run_id}/recording.har --output {output_dir}/filtered.har --stats
```

Read and display the filtering statistics:
```
Filtering complete!
Total entries: {total}
API endpoints found: {filtered_entries}
Removed:
- Static assets: {removed_static}
- Analytics/tracking: {removed_analytics}
- CDN resources: {removed_cdn}

API patterns detected: {api_patterns_found}
```

**Mark todo completed**

**Mark todo in_progress: "Analyze HAR using har_analyze.py"**

Extract structured endpoint information from filtered HAR:

```bash
python plugins/reverse-api-engineer/skills/reverse-engineering-api/scripts/har_analyze.py {output_dir}/filtered.har --output {output_dir}/analysis.json
```

Read analysis.json and summarize for the user:

```bash
cat {output_dir}/analysis.json
```

Display summary:
```
Analysis complete!

Base URL: {base_url}
Authentication: {authentication.type} ({authentication.description})
Unique endpoints: {unique_endpoints}
Pagination: {pagination.type if pagination.detected else "Not detected"}

Endpoints found:
{for each endpoint in endpoints:}
- {endpoint.methods} {endpoint.pattern}
  Calls observed: {endpoint.calls_observed}
  Auth required: {endpoint.requires_auth}
  Query params: {endpoint.query_params.required + endpoint.query_params.optional}
```

**Mark todo completed**

### Step 6: Generate API Client

Generate a descriptive name for the script based on the task:
```
task_name = sanitize(task)  # e.g., "apple_jobs_api"
output_dir = ./scripts/{task_name}/
```

Create output directory:
```bash
mkdir -p ./scripts/{task_name}/
```

Generate `api_client.py` with the following structure:

```python
"""
Auto-generated API client for {domain}
Generated from HAR capture on {date}

Run ID: {run_id}
HAR file: ~/.reverse-api/runs/har/{run_id}/recording.har
"""

import requests
from typing import Optional, Dict, Any, List
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class {ClassName}Client:
    """API client for {domain}."""

    def __init__(
        self,
        base_url: str = "{base_url}",
        session: Optional[requests.Session] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self._setup_session()

    def _setup_session(self):
        """Configure session with default headers."""
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible)",
            "Accept": "application/json",
            # Add detected required headers
        })

    def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs,
    ) -> requests.Response:
        """Make an HTTP request with error handling."""
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise

    # Generated endpoint methods
    # For each detected endpoint, create a method like:

    def get_example(self, param: str) -> Dict[str, Any]:
        """
        {Method description based on endpoint}.

        Args:
            param: {Parameter description}

        Returns:
            JSON response data

        Raises:
            requests.exceptions.RequestException: If request fails
        """
        response = self._request("GET", f"/api/example/{param}")
        return response.json()


# Example usage
if __name__ == "__main__":
    client = {ClassName}Client()
    # Add example calls based on captured endpoints
```

Generate `README.md`:
```markdown
# {Task Name} API Client

Auto-generated Python API client from browser traffic capture.

## Generated From

- **Run ID**: {run_id}
- **HAR File**: ~/.reverse-api/runs/har/{run_id}/recording.har
- **Date**: {date}
- **Base URL**: {base_url}

## Installation

```bash
pip install requests
```

## Usage

```python
from api_client import {ClassName}Client

client = {ClassName}Client()

# Example: {endpoint_1}
result = client.{method_1}({params})
print(result)
```

## Available Methods

{List all generated methods with descriptions}

## Authentication

{Describe detected authentication mechanism and how to configure}

## Notes

- Generated from captured browser traffic
- Endpoints based on observed API calls
- May require authentication tokens/API keys
- Test thoroughly before production use
```

### Step 6.5: Validate Generated Code

**Mark todo in_progress: "Validate code using har_validate.py"**

Validate the generated API client against the HAR analysis:

```bash
python plugins/reverse-api-engineer/skills/reverse-engineering-api/scripts/har_validate.py {output_dir}/api_client.py {output_dir}/analysis.json
```

Check the validation score and issues:

**If validation score < 90:**
1. Read the validation issues carefully
2. Fix each issue in api_client.py:
   - Missing endpoints: Add methods for each missing endpoint
   - Missing auth: Implement authentication from analysis.json
   - Missing error handling: Add try-except blocks and custom exceptions
   - Missing type hints: Add type hints to all methods
3. Save the updated api_client.py
4. Run validation again
5. Repeat until score >= 90

**Example validation loop:**
```
Attempt 1:
- Score: 75
- Issues: 2 missing endpoints, no auth implementation
- Fix: Add missing endpoints, implement bearer token auth
- Regenerate api_client.py

Attempt 2:
- Score: 92
- Issues: 1 info (minor type hint improvement)
- Result: PASS (score >= 90)
```

Display validation result:
```
Validation complete!
Score: {score}/100
Coverage: {coverage.percentage}% ({coverage.endpoints_covered}/{coverage.endpoints_total} endpoints)
Issues: {summary.errors} errors, {summary.warnings} warnings, {summary.info} info

{if score >= 90:}
✓ Code validation passed!
{else:}
✗ Code validation failed - fixing issues and regenerating...
```

**Mark todo completed** (only when score >= 90)

### Step 7: Save Run History

Update `~/.reverse-api/history.json` with run metadata:

```json
{
  "run_id": "{run_id}",
  "mode": "manual",
  "task": "{task}",
  "url": "{url}",
  "timestamp": "{ISO timestamp}",
  "har_path": "~/.reverse-api/runs/har/{run_id}/recording.har",
  "output_dir": "./scripts/{task_name}/",
  "status": "completed"
}
```

### Step 8: Summary

Present final summary to user:
```
API client generated successfully!

Run ID: {run_id}
HAR file: ~/.reverse-api/runs/har/{run_id}/recording.har

Generated files:
- ./scripts/{task_name}/api_client.py
- ./scripts/{task_name}/README.md

Detected endpoints: {count}
Authentication: {auth_type}

Next steps:
1. Review the generated code
2. Test with: python ./scripts/{task_name}/api_client.py
3. Integrate into your project
```

## Error Handling

- **Browser launch fails**: Check Playwright MCP is running and accessible
- **HAR file empty**: User didn't interact with website, or no network traffic captured
- **No API endpoints found**: All entries were filtered out (adjust filters or capture more traffic)
- **Generation fails**: Use `/reverse-api-engineer:engineer {run_id}` to retry with different approach

## Tips for Users

- **Login flows**: Log in during capture to record authentication
- **Pagination**: Navigate through pages to capture query parameter patterns
- **Different actions**: Create, read, update, delete to capture all CRUD endpoints
- **Multiple captures**: You can run manual mode multiple times for different flows
- **Re-engineer**: Use `/reverse-api-engineer:engineer {run_id}` to regenerate from same capture

## Examples

```
/reverse-api-engineer:manual "fetch Apple jobs" https://jobs.apple.com
/reverse-api-engineer:manual "scrape product data"
/reverse-api-engineer:manual
```
