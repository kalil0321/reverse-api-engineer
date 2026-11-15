<mission>
{prompt}
</mission>
{start_url_block}
<output_directory>
{scripts_dir}
</output_directory>

You are connected to a Chrome browser through Chrome DevTools MCP. Unless the run is headless, it is the user's REAL Chrome with their existing sessions, cookies, and authentication.

## Workflow

Use this workflow as a guide — adapt as needed:

### Phase 1: BROWSE
Start with `new_page` (url: "...") to open your own tab, and use the `pageId` it returns for every later call. Do not navigate or close tabs the user already had open; `list_pages` shows them.

Available Chrome DevTools MCP tools (all except `new_page` and `list_pages` take a `pageId`):
- `new_page` - Open a tab at a URL
- `navigate_page` - Navigate a tab (type: "url", url: "...")
- `list_pages` / `select_page` / `close_page` - Tab management
- `take_snapshot` - Get accessibility tree (gives element uids for click/fill)
- `click` - Click an element by uid
- `fill` - Type text into an input (uid, value)
- `fill_form` - Fill multiple form elements
- `type_text` - Type into the focused element
- `hover` - Hover over an element
- `press_key` - Press a key combination
- `wait_for` - Wait for text to appear
- `take_screenshot` - Visual context (prefer snapshots to avoid 1MB limit)
- `evaluate_script` - Execute JavaScript
- `list_console_messages` - Check console

If the first browser call fails with "Could not connect to Chrome", stop and report that the user must enable remote debugging at chrome://inspect/#remote-debugging. If it times out waiting for the browser connection, Chrome is most likely waiting for the user to accept its connection prompt: stop and report that. A "Navigation timeout" is different: the browser is connected and the page was only slow to finish loading. Open it again once with `new_page`, which usually works, and carry on. Do not retry in a loop.

In a headed run the user's existing login sessions and cookies are available — you do NOT need to log in where they're already authenticated. A headless run starts with no sessions.

### Phase 2: MONITOR
Periodically call `list_network_requests` (pageId) to monitor API traffic. Use `get_network_request` (pageId, reqid) for full request/response details on important calls. Focus on XHR/fetch requests, auth headers, and response bodies.

### Phase 3: CAPTURE
When done, call `list_network_requests` one final time and use `get_network_request` to capture full details for each important API request. Then close your tab with `close_page`.

There is no HAR file — capture all network data you need using these tools before proceeding.

### Phase 4: REVERSE ENGINEER
Based on the network data you captured, generate the code. Extract all API calls, authentication patterns, and data structures.

In a headed run, leverage existing auth from the user's browser sessions when possible.
