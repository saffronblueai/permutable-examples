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

# Display names for common tickers. Any ticker not listed here is shown by its code.
TICKER_NAMES = {
    "BZ_COM": "Brent Crude",
    "CL_COM": "WTI Crude",
    "TFM_COM": "TTF Gas",
    "NG_COM": "Henry Hub Gas",
    "RB_COM": "RBOB Gasoline",
    "LNG_COM": "LNG",
    "QO_COM": "Gold",
    "QI_COM": "Silver",
    "QC_COM": "Copper",
    "PL_COM": "Platinum",
    "PA_COM": "Palladium",
    "ALI_COM": "Aluminium",
    "TIO_COM": "Iron Ore",
    "ZC_COM": "Corn",
    "ZW_COM": "Wheat",
    "ZS_COM": "Soybeans",
    "ZL_COM": "Soybean Oil",
    "FCPO_COM": "Palm Oil",
    "CT_COM": "Cotton",
    "CC_COM": "Cocoa",
    "EUA_COM": "EU Carbon",
}


def ticker_label(ticker: str) -> str:
    return TICKER_NAMES.get(ticker, ticker)
