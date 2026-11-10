from datetime import datetime

from pydantic import BaseModel


class Headline(BaseModel):
    ticker: str
    match_type: str | None = None
    topic: str | None = None
    topic_probability: float | None = None
    short_term_sentiment_score: float | None = None
    medium_term_sentiment_score: float | None = None
    long_term_sentiment_score: float | None = None
    headline: str | None = None
    link: str | None = None
    source_name: str | None = None
    processed_at: datetime | None = None


class BinPoint(BaseModel):
    ticker: str
    match_type: str
    bin_end: datetime
    headline_count: int
    sentiment_avg: float
    sentiment_std: float
    sentiment_smooth: float | None
    window_count: int


class TopicSentiment(BaseModel):
    topic: str
    headline_count: int
    sentiment_avg: float


class MatchTypeSummary(BaseModel):
    match_type: str
    rows: int
    articles: int
    avg_short_term: float | None
    avg_medium_term: float | None
    avg_long_term: float | None


class EntityTypeCount(BaseModel):
    entity_type: str
    family: str
    articles: int


class HealthResponse(BaseModel):
    status: str
    db_path: str
    row_count: int | None = None
    latest_processed_at: datetime | None = None
