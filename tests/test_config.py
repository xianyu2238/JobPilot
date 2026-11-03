"""Verify configuration precedence and early rejection of invalid log levels."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_environment_overrides_dotenv(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("JOBPILOT_APP_NAME", raising=False)
    monkeypatch.delenv("JOBPILOT_LOG_LEVEL", raising=False)
    config_file = tmp_path / ".env"
    config_file.write_text(
        "JOBPILOT_APP_NAME=测试项目\nJOBPILOT_LOG_LEVEL=WARNING\n",
        encoding="utf-8",
    )
    from_file = Settings(_env_file=config_file)
    assert from_file.app_name == "测试项目"
    assert from_file.log_level == "WARNING"
    monkeypatch.setenv("JOBPILOT_LOG_LEVEL", "ERROR")
    assert Settings(_env_file=config_file).log_level == "ERROR"


def test_invalid_log_level_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("JOBPILOT_LOG_LEVEL", "INVALID")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_aihubmix_key_alias_and_precedence(monkeypatch) -> None:
    monkeypatch.delenv("JOBPILOT_LLM_API_KEY", raising=False)
    monkeypatch.setenv("AIHUBMIX_API_KEY", "test-alias")
    assert Settings(_env_file=None).llm_api_key.get_secret_value() == "test-alias"
    monkeypatch.setenv("JOBPILOT_LLM_API_KEY", "test-primary")
    settings = Settings(_env_file=None)
    assert settings.llm_api_key.get_secret_value() == "test-primary"
    assert "test-primary" not in repr(settings)
