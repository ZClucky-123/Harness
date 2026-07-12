import httpx

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
