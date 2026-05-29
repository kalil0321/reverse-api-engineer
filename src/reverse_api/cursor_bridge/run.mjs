/**
 * JSON-over-stdio bridge for the Cursor TypeScript SDK.
 * stdin: one JSON object (see cursor_engineer._CURSOR_BRIDGE_SCHEMA in Python).
 * stdout: newline-delimited JSON events, ending with { "type": "done", ... } or { "type": "error", ... }.
 */
import { readFileSync } from "node:fs";
import { Agent } from "@cursor/sdk";

function emit(obj) {
  process.stdout.write(`${JSON.stringify(obj)}\n`);
}

function summarizeEvent(ev) {
  try {
    const t = ev.type;
    if (t === "thinking") {
      return { type: t, text: ev.text };
    }
    if (t === "task" && ev.text) {
      return { type: "thinking", text: String(ev.text) };
    }
    if (t === "assistant") {
      const parts = [];
      for (const block of ev.message?.content || []) {
        if (block.type === "text" && block.text) {
          parts.push(block.text);
        }
      }
      return { type: t, text: parts.join("") };
    }
    if (t === "tool_call") {
      return {
        type: t,
        name: ev.name,
        status: ev.status,
        callId: ev.call_id ?? ev.callId,
        args: ev.args,
        result: ev.status !== "running" ? ev.result : undefined,
      };
    }
    return { type: t };
  } catch {
    return { type: "unknown" };
  }
}

const raw = readFileSync(0, "utf-8");
let input;
try {
  input = JSON.parse(raw);
} catch (e) {
  emit({ type: "error", message: `invalid stdin json: ${e.message}` });
  process.exit(1);
}

const apiKey = input.apiKey || process.env.CURSOR_API_KEY;
if (!apiKey) {
  emit({ type: "error", message: "missing apiKey and CURSOR_API_KEY" });
  process.exit(1);
}

const cwd = input.cwd;
if (!cwd || typeof cwd !== "string") {
  emit({ type: "error", message: "missing cwd" });
  process.exit(1);
}

const modelId = input.modelId || "composer-2.5";
const mcpServers = input.mcpServers && typeof input.mcpServers === "object" ? input.mcpServers : undefined;
const resumeAgentId = input.resumeAgentId || null;
const prompt = input.prompt;
if (!prompt || typeof prompt !== "string") {
  emit({ type: "error", message: "missing prompt" });
  process.exit(1);
}

const settingSources =
  Array.isArray(input.settingSources) && input.settingSources.length > 0
    ? input.settingSources
    : input.cursorWebSearch === false
      ? ["project", "user"]
      : ["project", "user", "plugins", "team"];

const usageAgg = {
  input_tokens: 0,
  output_tokens: 0,
  cache_read_tokens: 0,
  cache_write_tokens: 0,
};

/** @type {import("@cursor/sdk").SDKAgent | null} */
let agent = null;
try {
  const agentOpts = {
    apiKey,
    model: { id: modelId },
    local: { cwd, settingSources },
    ...(mcpServers ? { mcpServers } : {}),
  };

  if (resumeAgentId) {
    agent = await Agent.resume(resumeAgentId, agentOpts);
  } else {
    agent = await Agent.create(agentOpts);
  }

  emit({ type: "agent", agentId: agent.agentId });

  const sendOptions = {
    onDelta: ({ update }) => {
      if (update?.type === "turn-ended" && update.usage) {
        const u = update.usage;
        usageAgg.input_tokens += Number(u.inputTokens ?? 0);
        usageAgg.output_tokens += Number(u.outputTokens ?? 0);
        usageAgg.cache_read_tokens += Number(u.cacheReadTokens ?? 0);
        usageAgg.cache_write_tokens += Number(u.cacheWriteTokens ?? 0);
      }
    },
  };
  if (resumeAgentId && mcpServers) {
    sendOptions.mcpServers = mcpServers;
  }

  const run = await agent.send(prompt, sendOptions);

  /** Coalesce rapid thinking deltas into one NDJSON line per segment (reduces UI spam). */
  let thinkingBuf = "";
  const flushThinking = () => {
    const t = thinkingBuf.trim();
    if (!t) return;
    emit({ type: "stream", event: { type: "thinking", text: thinkingBuf } });
    thinkingBuf = "";
  };

  for await (const ev of run.stream()) {
    if (ev.type === "thinking") {
      thinkingBuf += ev.text ?? "";
      continue;
    }
    flushThinking();
    if (ev.type === "task" && ev.text) {
      emit({
        type: "stream",
        event: { type: "thinking", text: String(ev.text) },
      });
      continue;
    }
    emit({ type: "stream", event: summarizeEvent(ev) });
  }
  flushThinking();

  const runResult = await run.wait();
  emit({
    type: "done",
    agentId: agent.agentId,
    runResult,
    usage: usageAgg,
  });
} catch (e) {
  emit({
    type: "error",
    message: String(e?.message || e),
    stack: typeof e?.stack === "string" ? e.stack : undefined,
  });
  process.exit(1);
} finally {
  if (agent) {
    try {
      const ad = agent[Symbol.asyncDispose];
      if (typeof ad === "function") {
        await ad.call(agent);
      } else {
        agent.close();
      }
    } catch {
      try {
        agent.close();
      } catch {
        // ignore
      }
    }
  }
}
