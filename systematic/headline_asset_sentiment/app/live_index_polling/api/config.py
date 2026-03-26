from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_path: str = "/data/headline_index.db"

    # Sentiment thresholds — sentiment_avg = sentiment_sum / headline_count ∈ [−1, +1]
    upper_threshold: float = 0.5
    lower_threshold: float = -0.5


settings = Settings()
