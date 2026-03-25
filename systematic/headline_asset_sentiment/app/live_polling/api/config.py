from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_path: str = "/data/headline_sentiment.db"

    # Signal thresholds — must match the poller's signal logic
    bullish_threshold: float = 0.05
    bearish_threshold: float = -0.05


settings = Settings()
