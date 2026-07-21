import json

from guarded_harness.config.loader import load_config


def test_load_config_reads_non_secret_provider_file(tmp_path):
    config_dir = tmp_path / ".guarded-harness"
    config_dir.mkdir()
    (config_dir / "provider.json").write_text(
        json.dumps(
            {
                "mode": "live",
                "base_url": "https://njusehub.info/v1",
                "model": "deepseek-v4-flash",
                "timeout": 45,
                "api_key": "must-not-load-from-file",
            }
        ),
        encoding="utf-8",
    )

    config = load_config(environ={}, workspace_root=tmp_path)

    assert config.mode == "live"
    assert config.base_url == "https://njusehub.info/v1"
    assert config.model == "deepseek-v4-flash"
    assert config.timeout == 45
    assert config.api_key is None


def test_load_config_environment_overrides_provider_file(tmp_path):
    config_dir = tmp_path / ".guarded-harness"
    config_dir.mkdir()
    (config_dir / "provider.json").write_text(
        json.dumps(
            {
                "mode": "mock",
                "base_url": "https://file.example/v1",
                "model": "file-model",
                "timeout": 10,
            }
        ),
        encoding="utf-8",
    )

    config = load_config(
        environ={
            "GUARDED_HARNESS_MODE": "live",
            "GUARDED_HARNESS_BASE_URL": "https://env.example/v1",
            "GUARDED_HARNESS_MODEL": "env-model",
            "GUARDED_HARNESS_TIMEOUT": "60",
            "GUARDED_HARNESS_API_KEY": "env-secret",
        },
        workspace_root=tmp_path,
    )

    assert config.mode == "live"
    assert config.base_url == "https://env.example/v1"
    assert config.model == "env-model"
    assert config.timeout == 60
    assert config.api_key == "env-secret"
