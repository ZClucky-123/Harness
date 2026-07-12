import httpx
import pytest

from guarded_harness.llm.openai_compatible import OpenAICompatibleProvider


def _response(content: str) -> httpx.Response:
    request = httpx.Request("POST", "https://example.test/v1/chat/completions")
    return httpx.Response(200, request=request, json={"choices": [{"message": {"content": content}}]})


def test_openai_provider_sends_action_protocol_system_prompt(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return _response('{"type":"finish","message":"ok"}')

    monkeypatch.setattr("guarded_harness.llm.openai_compatible.httpx.post", fake_post)

    result = OpenAICompatibleProvider("https://example.test/v1", "model-a", "secret").complete({"task": "answer"})

    assert result == '{"type":"finish","message":"ok"}'
    messages = calls[0][1]["json"]["messages"]
    assert messages[0]["role"] == "system"
    assert "Return exactly one JSON object" in messages[0]["content"]
    assert '{"type":"finish","message":"..."}' in messages[0]["content"]
    assert messages[1]["role"] == "user"


def test_openai_provider_strips_fenced_json_response(monkeypatch):
    def fake_post(*args, **kwargs):
        return _response('```json\n{"type":"finish","message":"2"}\n```')

    monkeypatch.setattr("guarded_harness.llm.openai_compatible.httpx.post", fake_post)

    result = OpenAICompatibleProvider("https://example.test/v1", "model-a", "secret").complete({"task": "1+1"})

    assert result == '{"type":"finish","message":"2"}'


@pytest.mark.parametrize("content", ["", "   ", "```json\n   \n```"])
def test_openai_provider_rejects_empty_content_before_action_parsing(monkeypatch, content: str):
    def fake_post(*args, **kwargs):
        return _response(content)

    monkeypatch.setattr("guarded_harness.llm.openai_compatible.httpx.post", fake_post)

    with pytest.raises(RuntimeError, match="empty content"):
        OpenAICompatibleProvider("https://example.test/v1", "model-a", "secret").complete({"task": "1+1"})


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (400, "request was rejected"),
        (401, "authentication failed"),
        (403, "permission denied"),
        (429, "rate limited or quota exhausted"),
        (500, "service error"),
    ],
)
def test_openai_provider_classifies_http_errors(monkeypatch, status_code: int, expected: str):
    request = httpx.Request("POST", "https://example.test/v1/chat/completions")

    def fake_post(*args, **kwargs):
        return httpx.Response(status_code, request=request, text="provider body")

    monkeypatch.setattr("guarded_harness.llm.openai_compatible.httpx.post", fake_post)

    with pytest.raises(RuntimeError, match=expected) as exc_info:
        OpenAICompatibleProvider("https://example.test/v1", "model-a", "secret").complete({"task": "1+1"})

    assert "secret" not in str(exc_info.value)
    assert "provider body" not in str(exc_info.value)


def test_openai_provider_classifies_timeout(monkeypatch):
    def fake_post(*args, **kwargs):
        raise httpx.TimeoutException("too slow")

    monkeypatch.setattr("guarded_harness.llm.openai_compatible.httpx.post", fake_post)

    with pytest.raises(RuntimeError, match="timed out"):
        OpenAICompatibleProvider("https://example.test/v1", "model-a", "secret").complete({"task": "1+1"})


def test_openai_provider_rejects_invalid_json(monkeypatch):
    request = httpx.Request("POST", "https://example.test/v1/chat/completions")

    def fake_post(*args, **kwargs):
        return httpx.Response(200, request=request, content=b"not json")

    monkeypatch.setattr("guarded_harness.llm.openai_compatible.httpx.post", fake_post)

    with pytest.raises(RuntimeError, match="invalid JSON"):
        OpenAICompatibleProvider("https://example.test/v1", "model-a", "secret").complete({"task": "1+1"})
