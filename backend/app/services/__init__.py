import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.questions import QUESTION_ORDER, QUESTION_TEXT
from db.models import PipelineRun, Theme


def resolve_active_run(session: Session) -> PipelineRun | None:
    completed = session.scalar(
        select(PipelineRun)
        .where(PipelineRun.status == "completed")
        .order_by(PipelineRun.completed_at.desc())
        .limit(1)
    )
    if completed is not None:
        return completed

    return session.scalar(
        select(PipelineRun)
        .join(Theme, Theme.pipeline_run_id == PipelineRun.id)
        .order_by(PipelineRun.started_at.desc())
        .limit(1)
    )


def require_active_run(session: Session) -> PipelineRun:
    from fastapi import HTTPException

    run = resolve_active_run(session)
    if run is None:
        raise HTTPException(status_code=404, detail="No analysis snapshot available")
    return run


def parse_uuid_list(values: list[str]) -> list[uuid.UUID]:
    return [uuid.UUID(value) for value in values]
