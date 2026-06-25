import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from core.config import Settings, get_settings
from db.models import PipelineRun
from pipeline.stages import ALL_STAGES, INTELLIGENCE_STAGES, StageStats, build_stages
from pipeline.stages.base import PipelineStage

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AnalysisResult:
    pipeline_run_id: uuid.UUID
    status: str
    stats: dict[str, StageStats]


def _resolve_stages(
    selected: list[str] | None,
    stages_by_name: dict[str, PipelineStage],
) -> list[PipelineStage]:
    if selected is None:
        return [stages_by_name[name] for name in ALL_STAGES]

    invalid = [name for name in selected if name not in stages_by_name]
    if invalid:
        raise ValueError(f"Unknown stages: {', '.join(invalid)}")

    return [stages_by_name[name] for name in selected]


def _stages_pending(
    selected_names: list[str],
    item_counts: dict[str, Any] | None,
) -> list[str]:
    if not item_counts:
        return selected_names

    return [
        name
        for name in selected_names
        if item_counts.get(name, {}).get("status") != "completed"
    ]


def _can_resume_completed(selected_stage_names: list[str]) -> bool:
    return bool(selected_stage_names) and all(
        name in INTELLIGENCE_STAGES for name in selected_stage_names
    )


def _load_or_create_run(
    session: Session,
    *,
    run_id: uuid.UUID | None,
    selected_stage_names: list[str],
    dry_run: bool,
    mock: bool,
) -> PipelineRun:
    if run_id is not None:
        pipeline_run = session.get(PipelineRun, run_id)
        if pipeline_run is None:
            raise ValueError(f"Pipeline run not found: {run_id}")
        if pipeline_run.status == "completed" and not _can_resume_completed(selected_stage_names):
            raise ValueError(f"Pipeline run already completed: {run_id}")
        pipeline_run.status = "running"
        return pipeline_run

    pipeline_run = PipelineRun(
        status="running",
        config_snapshot={
            "type": "analysis",
            "stages": selected_stage_names,
            "dry_run": dry_run,
            "mock": mock,
        },
        item_counts={},
    )
    session.add(pipeline_run)
    session.flush()
    return pipeline_run


def run_analysis(
    session: Session,
    *,
    stages: list[str] | None = None,
    run_id: uuid.UUID | None = None,
    settings: Settings | None = None,
    dry_run: bool = False,
    mock: bool = False,
    stages_by_name: dict[str, PipelineStage] | None = None,
) -> AnalysisResult:
    settings = settings or get_settings()
    stages_by_name = stages_by_name or build_stages()
    selected_stages = _resolve_stages(stages, stages_by_name)
    selected_names = [stage.name for stage in selected_stages]

    pipeline_run = _load_or_create_run(
        session,
        run_id=run_id,
        selected_stage_names=selected_names,
        dry_run=dry_run,
        mock=mock,
    )

    item_counts: dict[str, Any] = dict(pipeline_run.item_counts or {})
    pending_names = _stages_pending(selected_names, item_counts)
    stats_by_stage: dict[str, StageStats] = {}

    for stage in selected_stages:
        if stage.name not in pending_names:
            logger.info("Skipping already completed stage: %s", stage.name)
            continue

        logger.info("Running stage: %s", stage.name)
        try:
            stats = stage.run(
                session,
                settings,
                pipeline_run.id,
                dry_run=dry_run,
                mock=mock,
            )
        except Exception:
            logger.exception("Stage %s failed", stage.name)
            item_counts[stage.name] = {
                "status": "failed",
                "processed": 0,
                "skipped": 0,
                "duration_seconds": 0.0,
                "details": {},
            }
            pipeline_run.status = "failed"
            pipeline_run.item_counts = dict(item_counts)
            flag_modified(pipeline_run, "item_counts")
            session.commit()
            raise

        stats_by_stage[stage.name] = stats
        item_counts[stage.name] = stats.to_dict()
        pipeline_run.item_counts = dict(item_counts)
        flag_modified(pipeline_run, "item_counts")
        session.flush()

    pipeline_run.status = "completed"
    pipeline_run.completed_at = datetime.now(UTC)
    pipeline_run.item_counts = dict(item_counts)
    flag_modified(pipeline_run, "item_counts")
    session.commit()

    return AnalysisResult(
        pipeline_run_id=pipeline_run.id,
        status=pipeline_run.status,
        stats=stats_by_stage,
    )
