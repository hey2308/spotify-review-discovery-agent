from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.schemas.common import CountsSnapshot
from app.schemas.meta import MetaResponse
from app.services import resolve_active_run
from app.services.overview import _counts_for_run
from db.models import FeedbackItem


def get_meta(session: Session) -> MetaResponse:
    run = resolve_active_run(session)

    if run is None:
        feedback_items = session.scalar(select(func.count()).select_from(FeedbackItem)) or 0
        return MetaResponse(
            pipeline_run_id=None,
            status=None,
            started_at=None,
            completed_at=None,
            last_updated=None,
            data_freshness="no_snapshot",
            counts=CountsSnapshot(feedback_items=feedback_items),
        )

    last_updated = run.completed_at or run.started_at
    if last_updated is not None and last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=UTC)

    freshness = "snapshot"
    if run.completed_at:
        age_days = (datetime.now(UTC) - run.completed_at.replace(tzinfo=UTC)).days
        if age_days > 30:
            freshness = "stale"
        elif age_days > 7:
            freshness = "aging"

    return MetaResponse(
        pipeline_run_id=run.id,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        last_updated=last_updated,
        data_freshness=freshness,
        counts=_counts_for_run(session, run),
    )
