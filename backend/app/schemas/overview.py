import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import CountsSnapshot, DateRange


class SentimentDistribution(BaseModel):
    positive: int = 0
    neutral: int = 0
    negative: int = 0


class OverviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pipeline_run_id: uuid.UUID | None = None
    total_items: int
    classified_items: int
    date_range: DateRange
    source_breakdown: dict[str, int]
    sentiment_distribution: SentimentDistribution
    headline_insight: str
    counts: CountsSnapshot = Field(default_factory=CountsSnapshot)
