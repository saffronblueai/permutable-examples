from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # API credentials
    api_key: str = Field(..., description="Permutable AI API key")
    base_url: str = "https://copilot-api.permutable.ai/v1"

    # GCSI headline feed. The ticker is a query preset, not part of the path.
    feed_live_path: str = "/headlines/feed/live/gcsi"
    feed_historical_path: str = "/headlines/feed/historical/gcsi"
    page_limit: int = 1000

    # Stored as plain strings so pydantic-settings doesn't attempt json.loads on
    # comma-separated values. Exposed as lists via the computed properties below.
    tickers: str = Field("BZ_COM", validation_alias="TICKERS")
    # Empty = the API default, COMBINED.
    match_types: str = Field("", validation_alias="MATCH_TYPES")

    # Polling
    poll_interval_seconds: int = 900
    backfill_days: int = 3

    # Storage
    db_path: str = "/data/gcsi_headlines.db"

    @computed_field  # type: ignore[misc]
    @property
    def tickers_list(self) -> list[str]:
        return [t.strip() for t in self.tickers.split(",") if t.strip()]

    @computed_field  # type: ignore[misc]
    @property
    def match_types_list(self) -> list[str | None]:
        return [t.strip() for t in self.match_types.split(",") if t.strip()] or [None]


settings = Settings()
