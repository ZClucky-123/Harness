from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, context: dict[str, Any]) -> str:
        """Return one action response for the provided loop context."""
