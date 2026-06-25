import uuid

from pydantic import BaseModel, ConfigDict


class UnmetNeedItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    description: str
    frequency: int
    urgency_score: float | None = None
    source_attribution: dict[str, int] | None = None


class UnmetNeedsResponse(BaseModel):
    items: list[UnmetNeedItem]
    pipeline_run_id: uuid.UUID | None = None
