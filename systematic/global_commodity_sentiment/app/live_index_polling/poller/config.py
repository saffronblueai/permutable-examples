from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # API credentials
    api_key: str = Field(..., description="Permutable AI API key")
    base_url: str = "https://copilot-api.permutable.ai/v1"

    # GCSI index routes. The ticker is a query preset, not part of the path.
    index_live_path: str = "/headlines/index/gcsi/live"
    index_historical_path: str = "/headlines/index/gcsi/historical"
    page_limit: int = 1000

    # Stored as plain strings so pydantic-settings doesn't attempt json.loads on
    # comma-separated values. Exposed as lists via the computed properties below.
    tickers: str = Field("BZ_COM,QO_COM,ZC_COM,EUA_COM", validation_alias="TICKERS")
    index_types: str = Field("COMBINED", validation_alias="INDEX_TYPES")
    sentiment_types: str = Field("short_term,medium_term,long_term", validation_alias="SENTIMENT_TYPES")

    # Polling
    poll_interval_seconds: int = 900
    backfill_days: int = 30
    # Re-fetch this many hours behind the newest stored bar on restart, so late revisions are picked up.
    revision_hours: int = 6

    # Storage
    db_path: str = "/data/gcsi_index.db"

    @computed_field  # type: ignore[misc]
    @property
    def tickers_list(self) -> list[str]:
        return _split(self.tickers)

    @computed_field  # type: ignore[misc]
    @property
    def index_types_list(self) -> list[str]:
        return _split(self.index_types)

    @computed_field  # type: ignore[misc]
    @property
    def sentiment_types_list(self) -> list[str]:
        return _split(self.sentiment_types)


settings = Settings()
