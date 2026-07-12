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
        try:
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
        except httpx.TimeoutException as exc:
            raise RuntimeError("provider request timed out") from exc
        except httpx.RequestError as exc:
            raise RuntimeError("provider network connection failed") from exc
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(_http_error_message(exc.response.status_code)) from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("provider returned invalid JSON") from exc

        content = _extract_message_content(payload)
        stripped = _strip_json_fence(content)
        if not stripped:
            raise RuntimeError("provider returned empty content")
        return stripped


def _http_error_message(status_code: int) -> str:
    if status_code == 400:
        return "provider request was rejected; check model, base URL, and parameters"
    if status_code == 401:
        return "provider authentication failed; check the API key"
    if status_code == 403:
        return "provider permission denied; check account access for this model"
    if status_code == 429:
        return "provider rate limited or quota exhausted; retry later or check quota"
    if 500 <= status_code <= 599:
        return f"provider service error ({status_code}); retry later"
    return f"provider HTTP error ({status_code})"


def _extract_message_content(payload: object) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]  # type: ignore[index]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("provider response missing choices[0].message.content") from exc
    if not isinstance(content, str):
        raise RuntimeError("provider response content is not a string")
    return content


def _strip_json_fence(content: str) -> str:
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) >= 3 and lines[0].strip().lower() in {"```", "```json"} and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return stripped
