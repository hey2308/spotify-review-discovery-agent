import uuid

from pydantic import BaseModel, ConfigDict


class SegmentItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    top_frustration: str | None = None
    top_unmet_need: str | None = None
    top_behavior: str | None = None


class SegmentsResponse(BaseModel):
    items: list[SegmentItem]
    pipeline_run_id: uuid.UUID | None = None
