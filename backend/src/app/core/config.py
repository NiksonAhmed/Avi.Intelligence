"""Application settings loaded from environment variables (and `.env` in development)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    app_time_zone: str = "Australia/Sydney"

    # Development-only stand-in for sign-in (ignored in production): admin, project_manager, cra,
    # data_manager, safety or viewer. Lets you check what each role can see.
    dev_user_role: str = "admin"

    # SQLite for an isolated local demo; PostgreSQL in Docker Compose / production.
    database_url: str = "sqlite:///./avi_intelligence.db"

    # Comma-separated list of origins allowed to call the API from a browser.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- SharePoint (Microsoft Graph, app-only client credentials) ---
    sharepoint_mode: Literal["auto", "live", "mock"] = "auto"
    sharepoint_tenant_id: str | None = None
    sharepoint_client_id: str | None = None
    sharepoint_client_secret: SecretStr | None = None
    sharepoint_site_url: str | None = None
    sharepoint_sop_library: str = "Documents"
    sharepoint_sop_folder: str | None = None
    sharepoint_sop_field_map: str | None = None
    sharepoint_cache_minutes: int = Field(default=5, ge=0, le=1440)

    @field_validator(
        "sharepoint_tenant_id",
        "sharepoint_client_id",
        "sharepoint_site_url",
        "sharepoint_sop_folder",
        "sharepoint_sop_field_map",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v.strip() if isinstance(v, str) else v

    @field_validator("sharepoint_client_secret", mode="before")
    @classmethod
    def _blank_secret_to_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sharepoint_has_credentials(self) -> bool:
        return bool(
            self.sharepoint_tenant_id
            and self.sharepoint_client_id
            and self.sharepoint_client_secret
            and self.sharepoint_site_url
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
