from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class IndexRecord(BaseModel):
    ticker: str
    publication_time: datetime
    topic_name: str
    index_type: str | None = None
    headline_count: int | None = None
    sentiment_sum: float | None = None
    sentiment_abs_sum: float | None = None
    sentiment_std: float | None = None


class TickerConviction(BaseModel):
    ticker: str
    publication_time: datetime
    conviction_ratio: float
    conviction_smooth: float
    headline_count: int
    indicator: Literal["HIGH", "NEUTRAL", "LOW"]
    computed_at: datetime


class ConvictionPoint(BaseModel):
    ticker: str
    publication_time: datetime
    conviction_ratio: float
    conviction_smooth: float
    headline_count: int
    indicator: Literal["HIGH", "NEUTRAL", "LOW"]


class HealthResponse(BaseModel):
    status: str
    db_path: str
    row_count: int | None = None
