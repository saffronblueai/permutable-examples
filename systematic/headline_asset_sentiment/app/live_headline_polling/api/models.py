from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Headline(BaseModel):
    ticker: str
    publication_time: datetime
    topic_name: str
    ticker_name: str | None = None
    sentiment_score: float | None = None
    bearish_probability: float | None = None
    neutral_probability: float | None = None
    bullish_probability: float | None = None
    topic_probability: float | None = None
    match_type: str | None = None
    language: str | None = None
    countries: str | None = None


class TickerSignal(BaseModel):
    ticker: str
    publication_time: datetime
    sentiment_mean: float
    conviction: float
    headline_count: int
    signal_smooth: float
    signal: Literal["LONG", "SHORT", "FLAT"]
    computed_at: datetime


class SignalPoint(BaseModel):
    ticker: str
    publication_time: datetime
    sentiment_mean: float
    signal_smooth: float
    signal: Literal["LONG", "SHORT", "FLAT"]
    headline_count: int


class HealthResponse(BaseModel):
    status: str
    db_path: str
    row_count: int | None = None
