import os
import sys
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional


class Settings(BaseSettings):
    # -----------------------------------------------------------------------
    # Database
    # -----------------------------------------------------------------------
    database_url: str = "sqlite:///data/gmaps_discovery.db"

    # -----------------------------------------------------------------------
    # Source data files
    # -----------------------------------------------------------------------
    locations_file: str = "Geocoded_Ad_Targeting_Locations_FINAL.xlsx"
    categories_file: str = "G-Map Scraper Categories.xlsx"

    # -----------------------------------------------------------------------
    # Discovery tuning
    # -----------------------------------------------------------------------
    default_radius_km: float = 20.0
    browser_headless: bool = True
    browser_timeout_ms: int = 30000          # page navigation timeout (ms)
    element_timeout_ms: int = 6000           # element wait timeout (ms)
    discovery_concurrency: int = 1           # simultaneous browser contexts
    max_scroll_attempts: int = 4             # feed scroll iterations
    search_delay_seconds: float = 2.0        # delay between jobs in a batch
    listing_delay_seconds: float = 1.0       # pause after each detail page
    max_results_per_job: int = 200           # safety cap on listings per job

    # -----------------------------------------------------------------------
    # Job management
    # -----------------------------------------------------------------------
    batch_size: int = 50
    job_retry_limit: int = 3
    stale_job_age_minutes: int = 30

    # -----------------------------------------------------------------------
    # Email enrichment
    # -----------------------------------------------------------------------
    email_max_pages_per_site: int = 4
    email_navigation_timeout_ms: int = 15000
    email_max_concurrency: int = 5

    # -----------------------------------------------------------------------
    # API / Server
    # -----------------------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000"

    # -----------------------------------------------------------------------
    # n8n / integration
    # -----------------------------------------------------------------------
    backend_base_url: str = "http://localhost:8000"
    n8n_output_spreadsheet_id: str = ""

    # -----------------------------------------------------------------------
    # Logging & environment
    # -----------------------------------------------------------------------
    log_level: str = "INFO"
    environment: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # -----------------------------------------------------------------------
    # Derived / validated properties
    # -----------------------------------------------------------------------

    @field_validator("database_url")
    @classmethod
    def database_url_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("DATABASE_URL must not be empty")
        return v.strip()

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"LOG_LEVEL must be one of {valid}")
        return upper

    @field_validator("batch_size")
    @classmethod
    def validate_batch_size(cls, v: int) -> int:
        if v < 1 or v > 500:
            raise ValueError("BATCH_SIZE must be between 1 and 500")
        return v

    @field_validator("job_retry_limit")
    @classmethod
    def validate_retry_limit(cls, v: int) -> int:
        if v < 0 or v > 20:
            raise ValueError("JOB_RETRY_LIMIT must be between 0 and 20")
        return v

    @field_validator("default_radius_km")
    @classmethod
    def validate_radius(cls, v: float) -> float:
        if v <= 0 or v > 500:
            raise ValueError("DEFAULT_RADIUS_KM must be between 0 and 500")
        return v

    @property
    def is_postgresql(self) -> bool:
        return self.database_url.startswith("postgresql")

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse comma-separated CORS_ORIGINS into a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

# ---------------------------------------------------------------------------
# Ensure SQLite data directory exists for local development
# ---------------------------------------------------------------------------
if settings.is_sqlite:
    db_path = settings.database_url.replace("sqlite:///", "")
    dir_name = os.path.dirname(db_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
