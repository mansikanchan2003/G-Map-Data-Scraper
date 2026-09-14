import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "sqlite:///data/gmaps_discovery.db"
    locations_file: str = "Geocoded_Ad_Targeting_Locations_FINAL.xlsx"
    categories_file: str = "G-Map Scraper Categories.xlsx"
    default_radius_km: float = 20.0
    log_level: str = "INFO"
    environment: str = "development"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()

# Ensure data directory exists for SQLite
if settings.database_url.startswith("sqlite:///"):
    db_path = settings.database_url.replace("sqlite:///", "")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
