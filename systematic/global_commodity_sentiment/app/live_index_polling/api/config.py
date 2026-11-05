from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_path: str = "/data/gcsi_index.db"

    # Smoothing: Σ sentiment_sum / Σ headline_count over a time-based window, so missing hours are handled correctly.
    smoothing_hours: int = 24
    min_headlines: int = 5  # fewer topic-links than this in the window → no reading

    # Indicator thresholds. GCSI averages usually sit well inside ±0.3, so by default the
    # thresholds are calibrated per ticker and horizon from the stored history.
    threshold_mode: str = "percentile"  # percentile | fixed
    upper_percentile: float = 0.90
    lower_percentile: float = 0.10
    upper_threshold: float = 0.15  # used when threshold_mode=fixed
    lower_threshold: float = -0.15
    calibration_hours: int = 720  # history used for percentile thresholds


settings = Settings()
