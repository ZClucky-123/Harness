import os

from guarded_harness.config.schema import HarnessConfig


def load_config(environ: dict[str, str] | None = None) -> HarnessConfig:
    values = environ if environ is not None else os.environ
    timeout = float(values.get("GUARDED_HARNESS_TIMEOUT", "30"))
    return HarnessConfig(
        base_url=values.get("GUARDED_HARNESS_BASE_URL", HarnessConfig.base_url),
        model=values.get("GUARDED_HARNESS_MODEL", HarnessConfig.model),
        timeout=timeout,
    )
