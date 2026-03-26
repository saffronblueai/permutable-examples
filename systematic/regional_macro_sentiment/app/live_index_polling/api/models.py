from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class RegionalRecord(BaseModel):
    publication_time: datetime
    topic_name: str
    country: str
    index_type: str | None = None
    headline_count: int | None = None
    sentiment_avg: float | None = None
    sentiment_sum: float | None = None
    sentiment_std: float | None = None


class CountrySentiment(BaseModel):
    country: str
    publication_time: datetime
    sentiment_avg: float
    sentiment_smooth: float
    headline_count: int
    indicator: Literal["HIGH", "NEUTRAL", "LOW"]
    computed_at: datetime


class SentimentPoint(BaseModel):
    country: str
    publication_time: datetime
    sentiment_avg: float
    sentiment_smooth: float
    headline_count: int
    indicator: Literal["HIGH", "NEUTRAL", "LOW"]


class HealthResponse(BaseModel):
    status: str
    db_path: str
    row_count: int | None = None
