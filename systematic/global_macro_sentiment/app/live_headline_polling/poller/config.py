from pydantic import AliasChoices, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_key: str = Field(
        ...,
        validation_alias=AliasChoices("API_KEY", "PERMUTABLE_API_KEY"),
        description="Permutable AI API key",
    )
    base_url: str = "https://copilot-api.permutable.ai/v1"

    # ISO-2 country codes — get valid values from GET /v1/countries
    countries: str = Field("US,JP,IT,GB,FR,DE,CA", validation_alias="COUNTRIES")

    # Full GMSI topic names — get valid values from GET /v1/headlines/topics/gmsi
    topics: str = Field(
        "Monetary Policy-Policy Tools-Interest Rates,Economic Data-Inflation-Energy,Economic Data-Inflation-Food,Fiscal Policy-Fiscal Stance",
        validation_alias="TOPICS",
    )

    # Coverage lens: DOMESTIC | INTERNATIONAL | COMBINED
    match_type: str = "COMBINED"

    poll_interval_seconds: int = 900  # 15 minutes
    backfill_days: int = 7

    db_path: str = "/data/gmsi_headlines.db"

    @computed_field  # type: ignore[misc]
    @property
    def countries_list(self) -> list[str]:
        return [c.strip() for c in self.countries.split(",") if c.strip()]

    @computed_field  # type: ignore[misc]
    @property
    def topics_list(self) -> list[str]:
        return [t.strip() for t in self.topics.split(",") if t.strip()]


settings = Settings()
