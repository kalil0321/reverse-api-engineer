<mission>
{prompt}
</mission>
{start_url_block}
<output_directory>
{scripts_dir}
</output_directory>

## Workflow

Use this workflow as a guide — adapt as needed:

### Phase 1: BROWSE
Use browser MCP tools to accomplish the mission goal. Some available tools:
- `browser_navigate` - Navigate to a URL
- `browser_click` - Click an element
- `browser_close` - Close the browser
- `browser_evaluate` - Evaluate JavaScript code (also how to scroll)
- `browser_press_key` - Press a key
- `browser_run_code_unsafe` - Run Playwright code
- `browser_type` - Type text into input
- `browser_wait_for` - Wait for text/time
- `browser_snapshot` - Get accessibility tree (good alternative to screenshots)
- `browser_take_screenshot` - Take screenshot (prefer element-specific to avoid 1MB limit)
- `browser_network_requests` - List captured network requests

### Phase 2: MONITOR
Periodically call `browser_network_requests()` to monitor API traffic. Look for auth patterns (cookies, tokens, headers), endpoints, and response structures.

### Phase 3: CAPTURE
Reverse API Engineer records every request and response the browser makes to `{har_path}`. The file is written when the browser closes, so call `browser_close()` once you have browsed what the mission needs. The recording is kept for the user whether or not you read it.

### Phase 4: REVERSE ENGINEER
Work from the traffic you saw with `browser_network_requests()`. When you need full headers or response bodies, read `{har_path}` after closing the browser. Extract the API calls, authentication patterns, and data structures, and generate the code. The recording is not part of your summary unless reading it failed.

Call `browser_network_requests()` frequently to monitor traffic.