from dataclasses import dataclass


@dataclass(frozen=True)
class HarnessConfig:
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key: str | None = None
    timeout: float = 30.0
