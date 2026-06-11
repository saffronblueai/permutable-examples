from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class GmsiIndexRecord(BaseModel):
    country: str
    topic: str
    sentiment_type: str
    index_type: str
    publication_time: datetime
    headline_count: int | None = None
    sentiment_sum: float | None = None
    sentiment_abs_sum: float | None = None
    sentiment_std: float | None = None


class CountrySentiment(BaseModel):
    country: str
    topic: str
    sentiment_type: str
    index_type: str
    publication_time: datetime
    sentiment_avg: float
    sentiment_smooth: float
    activity_weighted: float
    headline_count: int
    indicator: Literal["HIGH", "NEUTRAL", "LOW"]
    computed_at: datetime


class SentimentPoint(BaseModel):
    country: str
    topic: str
    sentiment_type: str
    index_type: str
    publication_time: datetime
    sentiment_avg: float
    sentiment_smooth: float
    activity_weighted: float
    headline_count: int
    indicator: Literal["HIGH", "NEUTRAL", "LOW"]


class HealthResponse(BaseModel):
    status: str
    db_path: str
    row_count: int | None = None
