from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_path: str = "/data/macro_regional.db"

    # Sentiment indicator thresholds.
    # sentiment_avg ∈ [−1, +1] — narrower thresholds than conviction ratio
    # because sentiment_avg is already a mean rather than a ratio.
    upper_threshold: float = 0.5
    lower_threshold: float = -0.5


settings = Settings()
