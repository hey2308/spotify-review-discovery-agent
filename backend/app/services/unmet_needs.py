from sqlalchemy import select
from sqlalchemy.orm import Session

from app.schemas.unmet_needs import UnmetNeedItem, UnmetNeedsResponse
from app.services import require_active_run
from db.models import UnmetNeed


def list_unmet_needs(session: Session) -> UnmetNeedsResponse:
    run = require_active_run(session)
    needs = list(
        session.scalars(
            select(UnmetNeed)
            .where(UnmetNeed.pipeline_run_id == run.id)
            .order_by(UnmetNeed.frequency.desc(), UnmetNeed.urgency_score.desc())
        ).all()
    )
    items = [
        UnmetNeedItem(
            id=need.id,
            description=need.description,
            frequency=need.frequency,
            urgency_score=need.urgency_score,
            source_attribution=need.source_attribution,
        )
        for need in needs
    ]
    return UnmetNeedsResponse(items=items, pipeline_run_id=run.id)
