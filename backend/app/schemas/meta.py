import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.common import CountsSnapshot


class MetaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pipeline_run_id: uuid.UUID | None = None
    status: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_updated: datetime | None = None
    data_freshness: str
    counts: CountsSnapshot
