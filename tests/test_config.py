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
