"""Runtime configuration loaded from environment variables / .env file."""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Bloomberg Terminal (bbcomm) defaults to localhost:8194 on a machine
    # with an open Bloomberg Terminal session.
    bloomberg_host: str = Field(default="localhost", alias="BLOOMBERG_HOST")
    bloomberg_port: int = Field(default=8194, alias="BLOOMBERG_PORT")

    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    app_reload: bool = Field(default=False, alias="APP_RELOAD")

    api_key: str = Field(default="", alias="API_KEY")
    cors_origins: List[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"],
        alias="CORS_ORIGINS",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
