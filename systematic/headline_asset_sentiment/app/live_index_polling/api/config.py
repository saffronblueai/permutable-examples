from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_path: str = "/data/headline_index.db"

    # Conviction thresholds — conviction_ratio = sentiment_sum / sentiment_abs_sum ∈ [−1, +1]
    upper_threshold: float = 0.7
    lower_threshold: float = -0.7


settings = Settings()
