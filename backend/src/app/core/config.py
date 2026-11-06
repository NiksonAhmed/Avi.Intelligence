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
    # Which person in the demo directory the development user is (see app/auth/directory.py), so
    # "My Tasks" and assignee-only status changes can be tried locally.
    dev_user_id: str = "dev-user"

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
    # Semicolon-separated subfolders (relative to the SOP folder) that do not contain SOPs.
    sharepoint_sop_exclude_folders: str | None = None
    # Comma-separated file extensions treated as SOP documents.
    sharepoint_sop_file_types: str = "docx,doc,pdf"
    # Only approved (Effective) documents: drafts, in review and superseded are never shown or opened.
    sharepoint_sop_approved_only: bool = True
    # Only SOPs and forms recognised by their number (e.g. CO-SOP-001, CO-005-A); hides change
    # controls, executed records and unnumbered files.
    sharepoint_sop_numbered_only: bool = True
    sharepoint_cache_minutes: int = Field(default=5, ge=0, le=1440)

    # --- SimpleTrials (CTMS) ---
    # auto = API when credentials are set, otherwise demo studies. api | mock force a mode.
    simpletrials_mode: Literal["auto", "api", "mock"] = "auto"
    simpletrials_base_url: str = "https://app.simpletrials.com/api/v1/"
    # Single-study read-only credentials (e.g. the Sandbox study) ...
    simpletrials_study_id: str | None = None
    simpletrials_study_key: SecretStr | None = None
    # ... or Workspace/All Studies read-only credentials (take precedence when set).
    simpletrials_customer_id: str | None = None
    simpletrials_customer_key: SecretStr | None = None
    # Key milestones (portfolio headline). SimpleTrials' coded milestones are always key; these
    # extra names are matched case-insensitively, ignoring numbering like "07.03 " (semicolon-separated).
    simpletrials_key_milestones: str = (
        "Protocol Finalized;First Ethics Approval;Database Hard Lock;Clinical Study Report Finalized"
    )

    # --- AI assistant (Anthropic Claude API) ---
    anthropic_api_key: SecretStr | None = None
    assistant_model: str = "claude-opus-5-5"
    assistant_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"

    # Trust the operating system's certificate store (needed behind TLS-inspecting proxies).
    use_system_trust_store: bool = True

    @field_validator(
        "sharepoint_tenant_id",
        "sharepoint_client_id",
        "sharepoint_site_url",
        "sharepoint_sop_folder",
        "sharepoint_sop_field_map",
        "sharepoint_sop_exclude_folders",
        "simpletrials_study_id",
        "simpletrials_customer_id",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v.strip() if isinstance(v, str) else v

    @field_validator(
        "sharepoint_client_secret",
        "anthropic_api_key",
        "simpletrials_study_key",
        "simpletrials_customer_key",
        mode="before",
    )
    @classmethod
    def _blank_secret_to_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def simpletrials_scope(self) -> Literal["workspace", "study"] | None:
        """Which SimpleTrials credentials are configured (workspace wins over single study)."""
        if self.simpletrials_customer_id and self.simpletrials_customer_key:
            return "workspace"
        if self.simpletrials_study_id and self.simpletrials_study_key:
            return "study"
        return None

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
