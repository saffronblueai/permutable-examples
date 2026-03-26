from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # API credentials
    api_key: str = Field(..., description="Permutable AI API key")
    base_url: str = "https://copilot-api.permutable.ai/v1"

    # Regional macro model
    model_id: str = "macro_1"  # macro_1 | macro_2 | macro_3

    # Country and topic filters
    # Stored as plain str — pydantic-settings does not attempt json.loads on a
    # comma-separated value. Exposed as a list via the computed property below.
    country_preset: str = "G20"  # G20 | G7 | ALL | individual country name
    topic_preset: str = "ALL"
    language_preset: str = "ALL"
    source_preset: str = "ALL"
    source_country_preset: str = "ALL"

    # Index types to poll (all three are fetched every cycle)
    sparse: bool = True                # only return buckets that have headlines
    align_to_period_end: bool = True   # timestamp each bucket at close of hour

    # Polling
    poll_interval_seconds: int = 900   # 15 minutes
    backfill_days: int = 7

    # Storage
    db_path: str = "/data/macro_regional.db"

    @computed_field  # type: ignore[misc]
    @property
    def base_params(self) -> dict:
        """Base query params shared across all index-type requests (index_type added per-call)."""
        return {
            "country_preset"       : self.country_preset,
            "topic_preset"         : self.topic_preset,
            "language_preset"      : self.language_preset,
            "source_preset"        : self.source_preset,
            "source_country_preset": self.source_country_preset,
            "sparse"               : str(self.sparse).lower(),
            "align_to_period_end"  : str(self.align_to_period_end).lower(),
        }


INDEX_TYPES = ["COMBINED", "DOMESTIC", "INTERNATIONAL"]


settings = Settings()
