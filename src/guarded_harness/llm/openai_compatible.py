from typing import Any

import httpx

from guarded_harness.llm.base import LLMProvider


ACTION_PROTOCOL_PROMPT = """You are the decision engine inside a coding-agent harness.
Return exactly one JSON object and no prose, no markdown, no code fences.
The JSON object must contain a "type" field.
Supported actions:
- {"type":"finish","message":"..."} for ordinary answers or final results.
- {"type":"read_file","path":"relative/path"}
- {"type":"write_file","path":"relative/path","content":"..."}
- {"type":"run_shell","command":"..."}
- {"type":"run_tests"}
- {"type":"remember","kind":"decision","content":"...","tags":["..."]}
For normal question answering, use {"type":"finish","message":"..."}.
"""


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, base_url: str, model: str, api_key: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def complete(self, context: dict[str, Any]) -> str:
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": ACTION_PROTOCOL_PROMPT},
                    {"role": "user", "content": str(context)},
                ],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return _strip_json_fence(response.json()["choices"][0]["message"]["content"])


def _strip_json_fence(content: str) -> str:
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) >= 3 and lines[0].strip().lower() in {"```", "```json"} and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return stripped
