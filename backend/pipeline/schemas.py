from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ItemClassification(BaseModel):
    item_id: str
    sentiment_label: Literal["positive", "neutral", "negative"]
    sentiment_score: float = Field(ge=0.0, le=1.0)
    intent: str = Field(min_length=2, max_length=128)
    behavior_signals: list[str] = Field(default_factory=list, max_length=4)
    segment_hint: str = Field(min_length=2, max_length=128)

    @field_validator("behavior_signals")
    @classmethod
    def normalize_behavior_signals(cls, value: list[str]) -> list[str]:
        return [signal.strip() for signal in value if signal.strip()][:4]


class BatchClassificationResponse(BaseModel):
    classifications: list[ItemClassification]

    @field_validator("classifications")
    @classmethod
    def require_classifications(cls, value: list[ItemClassification]) -> list[ItemClassification]:
        if not value:
            raise ValueError("classifications must not be empty")
        return value


class ThemeLabelResponse(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    summary: str = Field(min_length=10, max_length=500)


class QASynthesisResponse(BaseModel):
    answer_text: str = Field(min_length=20, max_length=2000)
    evidence_ids: list[str] = Field(min_length=1, max_length=10)
    confidence: Literal["high", "medium", "low"]


class SegmentRollupItem(BaseModel):
    segment_key: str = Field(min_length=2, max_length=128)
    label: str = Field(min_length=3, max_length=128)
    top_frustration: str = Field(min_length=5, max_length=500)
    top_unmet_need: str = Field(min_length=5, max_length=500)
    top_behavior: str = Field(min_length=5, max_length=500)


class SegmentRollupResponse(BaseModel):
    segments: list[SegmentRollupItem] = Field(min_length=1, max_length=8)


class UnmetNeedExtractionItem(BaseModel):
    description: str = Field(min_length=5, max_length=500)
    supporting_ids: list[str] = Field(min_length=1, max_length=20)
    urgency_score: float = Field(ge=0.0, le=1.0)


class UnmetNeedsExtractionResponse(BaseModel):
    needs: list[UnmetNeedExtractionItem] = Field(min_length=1, max_length=12)
