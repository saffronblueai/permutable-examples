from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_url: str = "http://api:8000"
    refresh_interval_ms: int = 60_000
    dashboard_hours: int = 168

    tickers: str = Field("BZ_COM,QO_COM,ZC_COM,EUA_COM", validation_alias="TICKERS")
    index_types: str = Field("COMBINED", validation_alias="INDEX_TYPES")

    @computed_field  # type: ignore[misc]
    @property
    def tickers_list(self) -> list[str]:
        return [t.strip() for t in self.tickers.split(",") if t.strip()]

    @computed_field  # type: ignore[misc]
    @property
    def index_types_list(self) -> list[str]:
        return [t.strip() for t in self.index_types.split(",") if t.strip()]


settings = Settings()
