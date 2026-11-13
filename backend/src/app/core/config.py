"""Application settings loaded from environment variables (and `.env` in development)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ViedocConnectionSettings(BaseModel):
    """One Viedoc API client. Viedoc links each client to one study (and each region has its own API),
    so there is one of these per study. Set in `.env` as VIEDOC_CONNECTIONS__<NAME>__<FIELD>."""

    api_url: str
    """The API web address shown with the client in Viedoc (https://...viedoc.net/...)."""
    client_id: str
    client_secret: SecretStr
    token_url: str | None = None
    """OAuth token address; when blank it is looked up from the API's OpenID configuration."""
    scope: str | None = None
    environment: Literal["sandbox", "live"] = "sandbox"
    """Live connections are never read unless VIEDOC_ALLOW_LIVE=true (after data-protection sign-off)."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
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
    # Scheduled read-only sync for reports, in minutes (0 = off; never runs when APP_ENV=test).
    simpletrials_sync_minutes: int = Field(default=60, ge=0, le=1440)
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

    # --- Viedoc (EDC) for Data Management: read-only, one API client per study ---
    # "mock" always uses the demo study and ignores configured connections (tests and browser tests).
    viedoc_mode: Literal["auto", "mock"] = "auto"
    viedoc_connections: dict[str, ViedocConnectionSettings] = Field(default_factory=dict)
    viedoc_allow_live: bool = False
    data_management_enabled: bool = False
    # Hourly sync by default (0 = off; never runs in tests).
    data_management_sync_minutes: int = Field(default=60, ge=0, le=1440)
    # Ageing targets in working days (red when over, amber on the last day).
    dm_site_answer_days: int = Field(default=5, ge=1, le=60)
    dm_approval_days: int = Field(default=3, ge=1, le=60)

    # --- Conferences (BD): read-only from a SharePoint list; demo data until the list is set ---
    conferences_enabled: bool = True
    # "mock" always shows demo conferences (tests and browser tests).
    conferences_mode: Literal["auto", "mock"] = "auto"
    conferences_sharepoint_list: str | None = None
    # The site that holds the list; defaults to SHAREPOINT_SITE_URL.
    conferences_sharepoint_site_url: str | None = None
    # JSON: our field -> the list's column internal name(s), e.g. {"role": "AvionRole"}.
    conferences_field_map: str | None = None

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
