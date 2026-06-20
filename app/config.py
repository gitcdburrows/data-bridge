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


# Browser origins always allowed, baked into the build so the packaged .exe
# works with no config or .env. CORS_ORIGINS (env) only ADDS to this list —
# it can never drop these, so the Explorer's origins can't be lost by a
# partial/stale config.
DEFAULT_CORS_ORIGINS = [
    "https://universe.thesimplereport.com",
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
]


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

    # Origins allowed to call the bridge from a browser. DEFAULT_CORS_ORIGINS
    # are ALWAYS allowed (so the packaged .exe needs no config); setting
    # CORS_ORIGINS (comma-separated) ADDS extra origins for unpackaged runs.
    cors_origins: List[str] = Field(
        default_factory=lambda: list(DEFAULT_CORS_ORIGINS),
        alias="CORS_ORIGINS",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _merge_cors_origins(cls, v):
        if isinstance(v, str):
            provided = [o.strip() for o in v.split(",") if o.strip()]
        elif isinstance(v, (list, tuple)):
            provided = [str(o).strip() for o in v if str(o).strip()]
        else:
            provided = []
        merged: List[str] = []
        for origin in [*DEFAULT_CORS_ORIGINS, *provided]:
            if origin not in merged:
                merged.append(origin)
        return merged


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
