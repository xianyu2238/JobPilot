"""Read typed settings from environment variables and a local .env file."""

from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JOBPILOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        validate_assignment=True,
        populate_by_name=True,
    )

    app_name: str = Field(default="JobPilot", min_length=1)
    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    llm_base_url: str = ""
    llm_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("JOBPILOT_LLM_API_KEY", "AIHUBMIX_API_KEY"),
    )
    llm_model: str = ""
    vision_model: str = ""
    llm_json_mode: bool = True
    llm_enable_thinking: bool = False
    llm_proxy: str = ""
    llm_timeout_seconds: float = Field(default=90, ge=1, le=180)
    parse_budget_seconds: float = Field(default=300, ge=1, le=600)
    max_file_mb: int = Field(default=5, ge=1, le=20)
    max_pdf_pages: int = Field(default=5, ge=1, le=10)
    max_image_pixels: int = Field(default=12_000_000, ge=1000, le=25_000_000)
    max_text_chars: int = Field(default=30_000, ge=100, le=100_000)
    ocr_confidence_threshold: float = Field(default=0.85, ge=0, le=1)
    ocr_threads: int = Field(default=4, ge=1, le=16)
    store_capacity: int = Field(default=20, ge=1, le=100)
    store_ttl_seconds: int = Field(default=3600, ge=1, le=86400)
    api_base_url: str = "http://127.0.0.1:8000"
    latex_engine: Literal["auto", "tectonic", "xelatex"] = "auto"
    latex_binary: str = ""
    latex_timeout_seconds: int = Field(default=120, ge=10, le=600)
    latex_allow_downloads: bool = False
    latex_proxy: str = ""

    @field_validator("llm_base_url", "llm_proxy", "api_base_url", "latex_proxy")
    @classmethod
    def validate_url(cls, value: str) -> str:
        from urllib.parse import urlsplit

        value = value.strip().rstrip("/")
        if value:
            url = urlsplit(value)
            if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError("Use an HTTP(S) URL without credentials, query, or fragment")
        return value
