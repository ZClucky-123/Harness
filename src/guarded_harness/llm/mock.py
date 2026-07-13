from copy import deepcopy
from typing import Any

from guarded_harness.llm.base import LLMProvider


class MockLLM(LLMProvider):
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.contexts: list[dict[str, Any]] = []

    def complete(self, context: dict[str, Any]) -> str:
        self.contexts.append(deepcopy(context))
        if not self._responses:
            raise RuntimeError("MockLLM has no scripted response remaining")
        return self._responses.pop(0)
