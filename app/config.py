"""Runtime configuration loaded from environment variables / .env file.

The bridge is designed to run as a self-contained desktop app, so every
setting has a sensible default and the service starts with no configuration
at all. When packaged as an executable (PyInstaller) the ``.env`` file is
looked up next to the executable, so users can drop a ``.env`` beside the
app to override defaults without touching a Python environment.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_file_path() -> str:
    """Locate the .env file.

    When frozen by PyInstaller we look next to the executable so the app is
    configurable in place; otherwise we use a project-relative ``.env``.
    """
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), ".env")
    return ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_file_path(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Bloomberg Terminal (bbcomm) defaults to localhost:8194 on a machine
    # with an open Bloomberg Terminal session.
    bloomberg_host: str = Field(default="localhost", alias="BLOOMBERG_HOST")
    bloomberg_port: int = Field(default=8194, alias="BLOOMBERG_PORT")

    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")

    # Origins allowed to call the bridge from a browser. The Universe Studio
    # explorer is hosted at https://universe.thesimplereport.com; the
    # localhost entries keep local explorer development working out of the box.
    cors_origins: List[str] = Field(
        default_factory=lambda: [
            "https://universe.thesimplereport.com",
            "http://localhost:5173",
            "http://localhost:3000",
        ],
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
