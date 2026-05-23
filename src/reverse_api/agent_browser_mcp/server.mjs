/**
 * Stdio MCP server: proxies RAE agent mode to Vercel agent-browser (Rust CLI via npx).
 * Logs diagnostics to stderr only; stdout is reserved for MCP.
 */
import { spawnSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import * as z from "zod";

function parseArgs(argv) {
  let harOut = "";
  let session = "";
  let headed = false;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--har-out") harOut = argv[++i] ?? "";
    else if (a === "--session") session = argv[++i] ?? "";
    else if (a === "--headed") headed = true;
  }
  return { harOut, session, headed };
}

function agentBrowserArgv(globalHeaded, sub) {
  const g = [...(globalHeaded ? ["--headed"] : []), "--json"];
  return ["-y", "agent-browser@latest", ...g, ...sub];
}

function runAb(globalHeaded, subcommandArgs) {
  return spawnSync("npx", agentBrowserArgv(globalHeaded, subcommandArgs), {
    encoding: "utf8",
    maxBuffer: 50 * 1024 * 1024,
    env: { ...process.env },
  });
}

function asToolResult(r) {
  const text = (r.stdout || "").trim() || (r.stderr || "").trim() || "(no output)";
  if (r.status !== 0 && r.status != null) {
    return { content: [{ type: "text", text }], isError: true };
  }
  return { content: [{ type: "text", text }] };
}

const { harOut, session, headed } = parseArgs(process.argv.slice(2));

if (!harOut || !session) {
  console.error("rae-agent-browser-mcp: missing --har-out or --session");
  process.exit(2);
}

process.env.AGENT_BROWSER_SESSION = session;
mkdirSync(dirname(harOut), { recursive: true });

const boot = runAb(headed, ["network", "har", "start"]);
if (boot.status !== 0) {
  console.error(
    "rae-agent-browser-mcp: warning: network har start failed (continuing)",
    boot.stderr || boot.stdout,
  );
}

const mcpServer = new McpServer({
  name: "rae-agent-browser",
  version: "1.0.0",
});

const globalHeaded = headed;

mcpServer.registerTool(
  "browser_navigate",
  {
    description: "Open URL in the controlled browser session (agent-browser open). HTTPS is inferred when no scheme is given.",
    inputSchema: {
      url: z.string().describe("Target URL or hostname"),
    },
  },
  async ({ url }) => asToolResult(runAb(globalHeaded, ["open", url])),
);

mcpServer.registerTool(
  "browser_snapshot",
  {
    description: "Accessibility tree snapshot with @eN refs for clicks/fills. Prefer interactive-only (-i) to save tokens.",
    inputSchema: {
      interactive_only: z
        .boolean()
        .optional()
        .describe("When true (default), only interactive controls are returned."),
    },
  },
  async ({ interactive_only = true }) => {
    const args = interactive_only ? ["snapshot", "-i"] : ["snapshot"];
    return asToolResult(runAb(globalHeaded, args));
  },
);

mcpServer.registerTool(
  "browser_click",
  {
    description: "Click an element by @eN ref or CSS selector.",
    inputSchema: {
      element: z.string().describe("Selector or @ref from snapshot"),
    },
  },
  async ({ element }) => asToolResult(runAb(globalHeaded, ["click", element])),
);

mcpServer.registerTool(
  "browser_fill",
  {
    description: "Clear and fill an input or textarea (@ref or selector).",
    inputSchema: {
      element: z.string(),
      text: z.string(),
    },
  },
  async ({ element, text }) =>
    asToolResult(runAb(globalHeaded, ["fill", element, text])),
);

mcpServer.registerTool(
  "browser_type",
  {
    description: "Type into an element without clearing existing value.",
    inputSchema: {
      element: z.string(),
      text: z.string(),
    },
  },
  async ({ element, text }) =>
    asToolResult(runAb(globalHeaded, ["type", element, text])),
);

mcpServer.registerTool(
  "browser_press_key",
  {
    description: 'Press a key (e.g. Enter, Tab, Control+a).',
    inputSchema: {
      key: z.string(),
    },
  },
  async ({ key }) => asToolResult(runAb(globalHeaded, ["press", key])),
);

mcpServer.registerTool(
  "browser_wait_for",
  {
    description:
      "Wait for a CSS selector visibility, elapsed milliseconds, or page text (--text). Exactly one mode should be supplied.",
    inputSchema: {
      selector: z.string().optional(),
      milliseconds: z.number().int().positive().optional(),
      text: z.string().optional(),
    },
  },
  async ({ selector, milliseconds, text }) => {
    const modes = [selector != null && selector !== "", milliseconds != null, text != null && text !== ""].filter(Boolean);
    if (modes.length !== 1) {
      return {
        content: [
          {
            type: "text",
            text: "Provide exactly one of: selector, milliseconds, or text",
          },
        ],
        isError: true,
      };
    }
    if (milliseconds != null) {
      return asToolResult(runAb(globalHeaded, ["wait", String(milliseconds)]));
    }
    if (text) {
      return asToolResult(runAb(globalHeaded, ["wait", "--text", text]));
    }
    return asToolResult(runAb(globalHeaded, ["wait", selector]));
  },
);

mcpServer.registerTool(
  "browser_scroll",
  {
    description: "Scroll the page (up, down, left, right). Optional pixels (default sensible). Optional --selector scope.",
    inputSchema: {
      direction: z.enum(["up", "down", "left", "right"]),
      pixels: z.number().int().positive().optional(),
      selector: z.string().optional(),
    },
  },
  async ({ direction, pixels, selector }) => {
    const args = ["scroll", direction];
    if (pixels != null) args.push(String(pixels));
    if (selector) {
      args.push("--selector", selector);
    }
    return asToolResult(runAb(globalHeaded, args));
  },
);

mcpServer.registerTool(
  "browser_evaluate",
  {
    description: "Evaluate JavaScript in the page context (agent-browser eval).",
    inputSchema: {
      script: z.string(),
    },
  },
  async ({ script }) =>
    asToolResult(runAb(globalHeaded, ["eval", script])),
);

mcpServer.registerTool(
  "browser_take_screenshot",
  {
    description: "Save a screenshot (--full optional). Omit path for a temp file chosen by agent-browser.",
    inputSchema: {
      path: z.string().optional(),
      full_page: z.boolean().optional(),
    },
  },
  async ({ path, full_page = false }) => {
    const args = ["screenshot"];
    if (full_page) args.push("--full");
    if (path) args.push(path);
    return asToolResult(runAb(globalHeaded, args));
  },
);

mcpServer.registerTool(
  "browser_network_requests",
  {
    description: "Inspect captured requests (XHR/fetch/etc.) with optional filter; add clear=true to reset the buffer.",
    inputSchema: {
      filter: z.string().optional(),
      clear: z.boolean().optional(),
    },
  },
  async ({ filter, clear }) => {
    const args = ["network", "requests"];
    if (filter) {
      args.push("--filter", filter);
    }
    if (clear) {
      args.push("--clear");
    }
    return asToolResult(runAb(globalHeaded, args));
  },
);

mcpServer.registerTool(
  "browser_close",
  {
    description:
      "Stop HAR recording to the configured RAE recording path, close the browser, and finish capture for reverse engineering.",
    inputSchema: {},
  },
  async () => {
    const stop = runAb(globalHeaded, ["network", "har", "stop", harOut]);
    const clo = runAb(globalHeaded, ["close"]);
    const msg = [asToolResult(stop).content?.[0]?.text, asToolResult(clo).content?.[0]?.text].join("\n---\n");
    const failed = (stop.status !== 0 && stop.status != null) || (clo.status !== 0 && clo.status != null);
    if (failed) {
      return { content: [{ type: "text", text: msg }], isError: true };
    }
    return { content: [{ type: "text", text: msg }] };
  },
);

async function main() {
  const transport = new StdioServerTransport();
  await mcpServer.connect(transport);
}

main().catch((err) => {
  console.error("rae-agent-browser-mcp:", err);
  process.exit(1);
});
