import uuid

from pydantic import BaseModel, ConfigDict


class SubPattern(BaseModel):
    label: str
    count: int


class ThemeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    summary: str | None = None
    mention_volume: int
    sentiment_score: float | None = None
    representative_quote_ids: list[uuid.UUID] = []


class ThemeQuote(BaseModel):
    id: uuid.UUID
    text: str
    source: str
    sentiment_label: str | None = None


class ThemeDetail(ThemeSummary):
    quotes: list[ThemeQuote] = []
    sub_patterns: list[SubPattern] = []


class ThemesResponse(BaseModel):
    items: list[ThemeSummary]
    pipeline_run_id: uuid.UUID | None = None
