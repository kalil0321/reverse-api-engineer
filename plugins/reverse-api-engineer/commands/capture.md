---
description: Launch browser with HAR recording for manual traffic capture
argument-hint: "[url]"
allowed-tools: ["MCP:rae-playwright-mcp", "Bash", "Read"]
---

# Capture Mode - Browser HAR Recording Only

Launch a browser with HAR (HTTP Archive) recording enabled. Navigate manually, then close the browser to save the HAR file. This command does NOT generate code - use `/reverse-api-engineer:engineer <run_id>` afterward to analyze the captured traffic and generate an API client.

## Purpose

Capture mode is useful when you want to:
- Record multiple browsing sessions before analysis
- Separate capture from code generation
- Share HAR files with others for analysis
- Capture traffic first, decide on implementation later

## Workflow

### Step 1: Generate Run ID

Create a unique run ID for this capture session:

```bash
run_id=$(uuidgen | tr '[:upper:]' '[:lower:]' | tr -d '-' | cut -c1-12)
echo "Starting capture session: ${run_id}"
```

Setup HAR file path:
```bash
har_dir="${HOME}/.reverse-api/runs/har/${run_id}"
mkdir -p "${har_dir}"
har_path="${har_dir}/recording.har"
```

Display to user:
```
Capture session started!
Run ID: {run_id}
HAR file: ~/.reverse-api/runs/har/{run_id}/recording.har
```

### Step 2: Launch Browser

Launch browser with HAR recording enabled using Playwright MCP:

```
Call MCP tool: playwright_navigate
Parameters:
  - url: {url} (if provided) or "about:blank"
  - options:
      - record_har: true
      - har_path: ~/.reverse-api/runs/har/{run_id}/recording.har
      - headless: false
```

Display instructions to user:
```
Browser launched with HAR recording enabled.

Instructions:
1. Navigate to the website you want to capture
2. Perform the actions you want to reverse engineer:
   - Log in (to capture authentication)
   - Browse pages (to capture GET requests)
   - Submit forms (to capture POST/PUT requests)
   - Trigger any API calls you need
3. Close the browser when done

The HAR file will be automatically saved when you close the browser.
```

### Step 3: Wait for Browser Close

Monitor the browser session. When the browser window closes, proceed to verification.

### Step 4: Verify HAR Capture

Check that the HAR file was created and contains data:

```bash
if [ -f ~/.reverse-api/runs/har/{run_id}/recording.har ]; then
    size=$(ls -lh ~/.reverse-api/runs/har/{run_id}/recording.har | awk '{print $5}')
    echo "✓ HAR file saved: $size"
else
    echo "✗ Error: HAR file not found"
    exit 1
fi
```

Count network requests in the HAR file:

```python
import json
from pathlib import Path

har_path = Path.home() / ".reverse-api" / "runs" / "har" / "{run_id}" / "recording.har"

with open(har_path, 'r') as f:
    har_data = json.load(f)
    entry_count = len(har_data['log']['entries'])

print(f"Captured {entry_count} network requests")
```

### Step 5: Save Capture Metadata

Save metadata about this capture session:

```bash
cat > ~/.reverse-api/runs/har/{run_id}/metadata.json <<EOF
{
  "run_id": "{run_id}",
  "mode": "capture",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "har_path": "~/.reverse-api/runs/har/{run_id}/recording.har",
  "url": "{url or 'manual navigation'}",
  "entry_count": {entry_count}
}
EOF
```

### Step 6: Display Summary

Present completion summary to user:

```
Capture complete!

Run ID: {run_id}
HAR file: ~/.reverse-api/runs/har/{run_id}/recording.har
File size: {size}
Network requests captured: {entry_count}

Next steps:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Option 1: Analyze and generate API client
  /reverse-api-engineer:engineer {run_id}

Option 2: View captured HAR file
  cat ~/.reverse-api/runs/har/{run_id}/recording.har | jq

Option 3: Filter HAR to see API calls only
  python plugins/reverse-api-engineer/skills/reverse-engineering-api/scripts/har_filter.py \\
    ~/.reverse-api/runs/har/{run_id}/recording.har --stats

Tip: You can capture multiple times and analyze later!
```

## Advantages Over /manual Mode

- **Faster**: No analysis step during capture
- **Flexible**: Capture once, analyze multiple times with different approaches
- **Shareable**: HAR files can be shared with team members
- **Clean separation**: Capture and analysis are independent steps

## Example Usage

```bash
# Capture with starting URL
/reverse-api-engineer:capture https://api.example.com

# Capture with manual navigation (no starting URL)
/reverse-api-engineer:capture

# After capture, analyze whenever ready
/reverse-api-engineer:engineer abc123def456
```

## Tips

1. **Capture thoroughly**: Include all API calls you want to reverse engineer
2. **Authentication**: If the site requires login, make sure to log in during capture
3. **Pagination**: If listing data, navigate through pages to capture pagination patterns
4. **Multiple captures**: You can run multiple capture sessions and analyze them separately

## Error Handling

**Browser doesn't launch:**
- Ensure Playwright MCP is properly configured
- Check that the browser binary is installed

**HAR file is empty:**
- Make sure you performed actions in the browser
- Some sites may have very few network requests

**HAR file is too large:**
- This is normal for sites with many static assets
- Use har_filter.py to reduce it before analysis
