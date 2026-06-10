from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_url: str = "http://api:8000"
    refresh_interval_ms: int = 60_000

    countries: str = Field("US,JP,IT,GB,FR,DE,CA", validation_alias="COUNTRIES")
    topics: str = Field(
        "Monetary Policy-Policy Tools-Interest Rates,Economic Data-Inflation-Energy,Economic Data-Inflation-Food,Fiscal Policy-Fiscal Stance",
        validation_alias="TOPICS",
    )

    upper_threshold: float = 0.5
    lower_threshold: float = -0.5

    @computed_field  # type: ignore[misc]
    @property
    def countries_list(self) -> list[str]:
        return [c.strip() for c in self.countries.split(",") if c.strip()]

    @computed_field  # type: ignore[misc]
    @property
    def topics_list(self) -> list[str]:
        return [t.strip() for t in self.topics.split(",") if t.strip()]


settings = Settings()
