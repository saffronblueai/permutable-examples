from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_path: str = "/data/gmsi_headlines.db"

    # Signal thresholds for directional_score ∈ [−1, +1]
    upper_threshold: float = 0.1
    lower_threshold: float = -0.1


settings = Settings()
