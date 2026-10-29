from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    database_url: PostgresDsn
    participant_session_minutes: int = Field(default=60, ge=1, le=240)
    participant_registration_limit: int = Field(default=60, ge=1)
    participant_submission_limit: int = Field(default=120, ge=1)
    privacy_notice_version: str | None = Field(default=None, max_length=100)
    privacy_notice_text: str | None = Field(default=None, max_length=10000)

    @field_validator("privacy_notice_version", "privacy_notice_text", mode="before")
    @classmethod
    def strip_notice(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
