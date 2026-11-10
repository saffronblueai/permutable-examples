from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_path: str = "/data/gcsi_headlines.db"

    # Own aggregation: bins on processed_at (receipt), labelled by their end, like the hourly index.
    bin_minutes: int = 15
    smoothing_hours: int = 6
    min_headlines: int = 5  # fewer rows than this in the smoothing window → no reading
    min_topic_probability: float = 0.0


settings = Settings()
