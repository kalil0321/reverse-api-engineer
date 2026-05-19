from __future__ import annotations

from rae_agent.protocol import ChatRequest, TargetLanguage

LANGUAGE_HINTS = {
    TargetLanguage.PYTHON: """
- Idiomatic Python 3.11+
- Use `httpx` for HTTP, prefer async if the flows look paginated or interactive
- Type hints with `from __future__ import annotations`
- Pydantic models when response shapes are stable
""",
    TargetLanguage.TYPESCRIPT: """
- TypeScript 5+, ESM
- Use the global `fetch` API (no axios)
- Strict types, no `any`
- Export plain async functions; group them in a class only if state is required
""",
    TargetLanguage.GO: """
- Modern Go 1.22+
- net/http standard client; no third-party HTTP libraries
- Errors wrapped with `%w`
- Structs with json tags
""",
}


SYSTEM_PROMPT = """You are ReverseAPI, an expert at reverse-engineering HTTP APIs from captured traffic.

You will be given:
- A user request describing the API client they want
- A JSON file at a known path containing captured HTTP flows (request + response, headers and bodies)
- A target language

Your job:
1. Read the flows file with the Read tool.
2. Identify the API endpoints involved in the user's request.
3. Detect authentication patterns (Bearer, cookies, custom headers).
4. Detect content negotiation, pagination, retries, rate limit headers.
5. Synthesise a clean, production-shaped client library in the target language.
6. Write each generated file using the Write tool, into the current working directory.
7. Briefly summarise what you produced and any assumptions you made.

Do NOT execute any code or make outbound HTTP calls. Do NOT install packages.
Keep generated code dependency-light and readable."""


def build_user_prompt(request: ChatRequest, flows_path: str) -> str:
    hints = LANGUAGE_HINTS.get(request.target, "").strip()
    lines = [
        f"User request: {request.user_message}",
        "",
        f"Captured flows file: {flows_path}",
        f"Number of flows: {len(request.flows)}",
        f"Target language: {request.target.value}",
        "",
        "Language guidelines:",
        hints,
    ]
    if request.history:
        lines.extend([
            "",
            "Recent conversation:",
            *[f"- {item['role']}: {item['content']}" for item in request.history[-6:]],
        ])
    return "\n".join(lines)
