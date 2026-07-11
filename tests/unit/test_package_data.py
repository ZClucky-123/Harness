from pathlib import Path


PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_web_assets_are_declared_as_package_data() -> None:
    pyproject = PYPROJECT.read_text(encoding="utf-8")

    assert "[tool.setuptools.package-data]" in pyproject
    assert '"guarded_harness.web" = ["static/*", "templates/*"]' in pyproject
