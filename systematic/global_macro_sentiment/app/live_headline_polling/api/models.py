from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class GmsiHeadline(BaseModel):
    country: str
    topic: str
    match_type: str
    publication_time: datetime
    topic_probability: float | None = None
    directional_positive: float | None = None
    directional_neutral: float | None = None
    directional_negative: float | None = None
    directional_score: float | None = None
    semantic_sentiment_positive: float | None = None
    semantic_sentiment_neutral: float | None = None
    semantic_sentiment_negative: float | None = None
    semantic_sentiment_score: float | None = None


class CountrySignal(BaseModel):
    country: str
    topic: str
    publication_time: datetime
    directional_mean: float
    semantic_mean: float
    directional_smooth: float
    semantic_smooth: float
    headline_count: int
    signal: Literal["HIGH", "NEUTRAL", "LOW"]
    computed_at: datetime


class SignalPoint(BaseModel):
    country: str
    topic: str
    publication_time: datetime
    directional_mean: float
    semantic_mean: float
    directional_smooth: float
    semantic_smooth: float
    headline_count: int
    signal: Literal["HIGH", "NEUTRAL", "LOW"]


class HealthResponse(BaseModel):
    status: str
    db_path: str
    row_count: int | None = None
