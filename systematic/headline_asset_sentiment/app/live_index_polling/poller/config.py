from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # API credentials
    api_key: str = Field(..., description="Permutable AI API key")
    base_url: str = "https://copilot-api.permutable.ai/v1"

    # Stored as a plain str so pydantic-settings doesn't attempt json.loads on
    # a comma-separated value. Exposed as a list via the computed property below.
    tickers: str = Field(
        "BTC_CRY,ETH_CRY,BZ_COM,EUR_IND",
        validation_alias="TICKERS",
    )

    # Index configuration
    index_type: str = "COMBINED"   # COMBINED | EXPLICIT | IMPLICIT
    topic_preset: str = "ALL"
    sparse: bool = True            # only return buckets that have headlines
    align_to_period_end: bool = True  # timestamp each bucket at hour close

    # Polling
    poll_interval_seconds: int = 900
    backfill_days: int = 7

    # Storage
    db_path: str = "/data/headline_index.db"

    @computed_field  # type: ignore[misc]
    @property
    def tickers_list(self) -> list[str]:
        return [t.strip() for t in self.tickers.split(",") if t.strip()]


settings = Settings()
