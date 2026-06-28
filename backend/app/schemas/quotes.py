import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class QuoteItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    text: str
    source: str
    rating: int | None = None
    item_date: datetime
    sentiment_label: str | None = None
    sentiment_score: float | None = None
    theme_ids: list[uuid.UUID] = Field(default_factory=list)
    theme_names: list[str] = Field(default_factory=list)


class PaginatedQuotes(BaseModel):
    items: list[QuoteItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class QuoteFilters(BaseModel):
    theme_id: uuid.UUID | None = None
    source: str | None = None
    rating: int | None = None
    rating_min: int | None = None
    rating_max: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    q: str | None = None
    page: int = 1
    page_size: int = 20
