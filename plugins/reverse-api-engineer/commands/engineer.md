---
description: Re-analyze existing HAR capture to generate new API client
argument-hint: "<run_id|har_path>"
allowed-tools: ["Read", "Write", "Bash"]
---

# Engineer Mode - Re-engineer from Existing HAR

Re-run AI generation on an existing HAR capture. This is useful when you want to regenerate the client with a different approach, extract additional endpoints, or improve the implementation without re-capturing traffic.

## Prerequisites

Ensure the `reverse-engineering-api` skill is loaded for guidance on HAR analysis and code generation.

## Command Arguments

- `run_id_or_path` (required): Either a run ID (e.g., "abc-123-def") or direct path to HAR file

## Task Tracking

Before starting the workflow, create a todo list to track progress:

```python
TodoWrite([
  {"content": "Verify HAR file exists", "status": "pending", "activeForm": "Verifying HAR file"},
  {"content": "Filter HAR using har_filter.py", "status": "pending", "activeForm": "Filtering HAR"},
  {"content": "Analyze HAR using har_analyze.py", "status": "pending", "activeForm": "Analyzing endpoints"},
  {"content": "Generate API client code", "status": "pending", "activeForm": "Generating code"},
  {"content": "Validate code using har_validate.py", "status": "pending", "activeForm": "Validating code"},
  {"content": "Test API client implementation", "status": "pending", "activeForm": "Testing implementation"},
  {"content": "Generate documentation", "status": "pending", "activeForm": "Writing README"}
])
```

**CRITICAL:** Mark each task as `in_progress` when starting, `completed` when done. NEVER skip tasks - complete all 7 steps.

## Workflow

### Step 1: Parse Input Argument

Determine if the argument is a run_id or a file path:

```python
import os

arg = "{argument}"

if os.path.exists(arg) and arg.endswith('.har'):
    # Direct HAR file path
    har_path = arg
    run_id = None
elif '/' in arg or '\\' in arg:
    # Looks like a path but doesn't exist
    Error: "HAR file not found at: {arg}"
elif arg:
    # Looks like a run_id
    run_id = arg
    har_path = f"~/.reverse-api/runs/har/{run_id}/recording.har"
else:
    # No argument provided
    Error: "Please provide either a run_id or path to HAR file"
```

### Step 2: Verify HAR File Exists

Check if the HAR file exists and is readable:

```bash
if [ -f {har_path} ]; then
    echo "HAR file found: {har_path}"
    ls -lh {har_path}
else
    echo "Error: HAR file not found at {har_path}"
    exit 1
fi
```

If using run_id but HAR file doesn't exist:
```
Error: "No HAR file found for run_id: {run_id}

Expected location: ~/.reverse-api/runs/har/{run_id}/recording.har

Available runs:
{list runs in ~/.reverse-api/runs/}"
```

### Step 3: List Available Runs (if needed)

If the HAR file is not found and a run_id was provided, list available runs to help the user:

```bash
ls -1 ~/.reverse-api/runs/ | head -10
```

Display:
```
Available run IDs:
- abc-123-def (2025-01-01)
- xyz-789-ghi (2025-01-02)
...

Use: /reverse-api-engineer:engineer <run_id>
Or provide direct path: /reverse-api-engineer:engineer /path/to/capture.har
```

### Step 4: Read Existing Run Metadata (if available)

If using run_id, try to read metadata from history:

```bash
if [ -f ~/.reverse-api/history.json ]; then
    # Read history.json and find entry for this run_id
    # Extract: task, url, timestamp, original mode
fi
```

Display context:
```
Re-engineering HAR capture:
- Run ID: {run_id}
- Original task: {task}
- Captured on: {timestamp}
- Original mode: {mode}
```

### Step 5: Prompt for New Task Description

Ask the user what to focus on for this regeneration:

```
The HAR file contains captured API traffic from a previous session.

What would you like to generate? (e.g., "focus on authentication endpoints", "create a simpler client", "add pagination support")

Press Enter to use original task: "{original_task}"
```

If user provides new description, use it. Otherwise, use original task.

### Step 6: Analyze HAR File

**Mark todo in_progress: "Filter HAR using har_filter.py"**

Filter the HAR file to remove static assets, analytics, and CDN resources:

```bash
python plugins/reverse-api-engineer/skills/reverse-engineering-api/scripts/har_filter.py {har_path} --output {output_dir}/filtered.har --stats
```

Read and display the filtering statistics:
```
Filtering HAR file: {har_path}
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

### Step 7: Generate New Run ID

Generate a new run ID for this regeneration:

```python
import uuid
new_run_id = str(uuid.uuid4())
```

This keeps the original capture separate from the new generation.

### Step 8: Generate API Client

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

Original Run ID: {original_run_id}
Original HAR file: {har_path}
Regenerated Run ID: {new_run_id}
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

- **Original Run ID**: {original_run_id}
- **HAR File**: {har_path}
- **Regenerated**: {date}
- **Regeneration Run ID**: {new_run_id}
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

- Regenerated from previous HAR capture
- Original capture: {original_date}
- Endpoints based on observed API calls
- May require authentication tokens/API keys
- Test thoroughly before production use
```

### Step 8.5: Validate Generated Code

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

### Step 9: Save Run History

Update `~/.reverse-api/history.json` with run metadata:

```json
{
  "run_id": "{new_run_id}",
  "mode": "engineer",
  "task": "{task}",
  "source_run_id": "{original_run_id}",
  "har_path": "{har_path}",
  "timestamp": "{ISO timestamp}",
  "output_dir": "./scripts/{task_name}/",
  "status": "completed"
}
```

### Step 10: Summary

Present final summary to user:

```
API client re-generated successfully!

Original HAR: {har_path}
Original Run ID: {original_run_id}
New Run ID: {new_run_id}

Generated files:
- ./scripts/{task_name}/api_client.py
- ./scripts/{task_name}/README.md

Detected endpoints: {count}
Authentication: {auth_type}

Next steps:
1. Review the generated code
2. Test with: python ./scripts/{task_name}/api_client.py
3. Compare with previous version (if any)
4. Integrate into your project

To regenerate with different focus:
/reverse-api-engineer:engineer {original_run_id}
```

## Error Handling

- **HAR file not found**: Provide list of available runs and suggest correct usage
- **Invalid HAR format**: Check file is valid JSON and follows HAR specification
- **No API endpoints found**: All entries were filtered out (suggest adjusting filters or recapturing)
- **Generation fails**: Retry with different approach or analyze HAR manually

## Tips for Users

- **Different approaches**: Try regenerating with different focus areas
- **Refinement**: Use engineer mode to improve previous generations
- **Testing**: Compare multiple generated versions to find the best implementation
- **Documentation**: Each regeneration creates a new run_id for tracking
- **Original HAR**: The original HAR file is never modified

## Examples

```
# Using run_id
/reverse-api-engineer:engineer abc-123-def

# Using direct path
/reverse-api-engineer:engineer ~/.reverse-api/runs/har/xyz-789/recording.har

# Using relative path
/reverse-api-engineer:engineer ./captures/myapp.har

# Re-engineer with focus
/reverse-api-engineer:engineer abc-123-def
> "focus on authentication endpoints only"
```

## Use Cases

1. **Improve previous generation**: Regenerate with better endpoint detection
2. **Extract subset**: Focus on specific endpoints from large capture
3. **Different implementation**: Generate alternative client architecture
4. **Update documentation**: Regenerate with better docstrings and examples
5. **Fix issues**: Address problems in previous generation without re-capturing
