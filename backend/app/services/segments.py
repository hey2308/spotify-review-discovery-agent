from sqlalchemy import select
from sqlalchemy.orm import Session

from app.schemas.segments import SegmentItem, SegmentsResponse
from app.services import require_active_run
from db.models import Segment


def list_segments(session: Session) -> SegmentsResponse:
    run = require_active_run(session)
    segments = list(
        session.scalars(
            select(Segment)
            .where(Segment.pipeline_run_id == run.id)
            .order_by(Segment.label)
        ).all()
    )
    items = [
        SegmentItem(
            id=segment.id,
            label=segment.label,
            top_frustration=segment.top_frustration,
            top_unmet_need=segment.top_unmet_need,
            top_behavior=segment.top_behavior,
        )
        for segment in segments
    ]
    return SegmentsResponse(items=items, pipeline_run_id=run.id)
