from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Indicator = Literal["HIGH", "NEUTRAL", "LOW", "NO_READING"]


class IndexRecord(BaseModel):
    ticker: str
    topic_name: str
    topic_id: str | None = None
    index_type: str
    sentiment_type: str
    processed_at: datetime
    headline_count: int | None = None
    sentiment_sum: float | None = None
    sentiment_abs_sum: float | None = None
    sentiment_std: float | None = None


class SentimentPoint(BaseModel):
    ticker: str
    sentiment_type: str
    index_type: str
    processed_at: datetime
    headline_count: int
    sentiment_avg: float
    sentiment_smooth: float | None
    window_count: int
    upper: float | None
    lower: float | None
    indicator: Indicator


class TickerSentiment(SentimentPoint):
    computed_at: datetime


class TopicSentiment(BaseModel):
    topic_name: str
    headline_count: int
    sentiment_avg: float


class HealthResponse(BaseModel):
    status: str
    db_path: str
    row_count: int | None = None
    latest_processed_at: datetime | None = None
