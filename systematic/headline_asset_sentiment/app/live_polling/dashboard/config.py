from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_url: str = "http://api:8000"
    refresh_interval_ms: int = 60_000

    # Stored as plain str — pydantic-settings would attempt json.loads on a
    # comma-separated value if typed as list[str], which raises JSONDecodeError.
    tickers: str = Field(
        "BTC_CRY,ETH_CRY,BZ_COM,EUR_IND",
        validation_alias="TICKERS",
    )

    # Must match api/signals.py thresholds so threshold lines align with signal colours
    bullish_threshold: float = 0.05
    bearish_threshold: float = -0.05

    @computed_field  # type: ignore[misc]
    @property
    def tickers_list(self) -> list[str]:
        return [t.strip() for t in self.tickers.split(",") if t.strip()]


settings = Settings()
