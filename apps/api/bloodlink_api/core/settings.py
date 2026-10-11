"""Runtime settings (owner: D1, spec §5 infrastructure/configuration).

Single Settings object for the whole API. Values come from the environment
(optionally via a project ``.env``). Nothing else in the codebase reads
``os.environ`` directly, so configuration has exactly one owner.
"""

from __future__ import annotations

import os

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from bloodlink_config.paths import PROJECT_ROOT
from bloodlink_contracts import API_PREFIX


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BLOODLINK_",
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "dev"
    app_name: str = "BloodLink API"
    api_prefix: str = API_PREFIX

    secret_key: str = "dev-only-insecure-secret-key-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 120
    refresh_token_ttl_minutes: int = 60 * 24 * 7
    jwt_issuer: str = "bloodlink-api"

    database_url: str = "sqlite:///./bloodlink.db"
    sql_echo: bool = False
    geo_backend: str = "haversine"  # haversine | postgis

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    # Matching engine defaults (D4 consumes; D1 owns the contract values)
    match_tier1_radius_km: float = 15.0
    match_tier1_limit: int = 25
    match_tier2_radius_km: float = 40.0
    match_tier2_limit: int = 50
    match_tier3_limit: int = 120
    donor_cooldown_days: int = 90

    push_transport: str = "log"  # log | console | webpush

    seed_on_startup: bool = True
    rate_limit_notifications_per_hour: int = 12

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("sql_echo", "seed_on_startup", mode="before")
    @classmethod
    def _boolish(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return value

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def resolved_database_url(self) -> str:
        """Make relative SQLite paths stable regardless of the CWD."""
        url = self.database_url
        if url.startswith("sqlite:///./"):
            relative = url.replace("sqlite:///./", "", 1)
            absolute = (PROJECT_ROOT / relative).resolve()
            return f"sqlite:///{absolute}"
        return url


def get_settings() -> Settings:
    """Cached settings accessor (also usable as a FastAPI dependency)."""
    cached = getattr(get_settings, "_cache", None)
    if cached is None:
        env_file = PROJECT_ROOT / ".env"
        if env_file.exists():
            from bloodlink_config.env import load_env_file

            load_env_file(env_file)
        cached = Settings()
        get_settings._cache = cached  # type: ignore[attr-defined]
    return cached


def reset_settings_cache() -> None:
    """Test helper: forget the cached Settings instance."""
    if hasattr(get_settings, "_cache"):
        delattr(get_settings, "_cache")
    for key in [k for k in os.environ if k.startswith("BLOODLINK_")]:
        if key.endswith("_TEST_OVERRIDE"):
            os.environ.pop(key, None)
