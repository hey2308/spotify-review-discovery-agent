import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.base import Base
from db.models import FeedbackItem, PipelineRun
from pipeline.orchestrator import run_analysis
from pipeline.stages import ALL_STAGES, INTELLIGENCE_STAGES
from pipeline.stages.base import PipelineStage, StageStats


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _add_feedback_item(session: Session, *, text: str = "Spotify discovery is stale") -> None:
    session.add(
        FeedbackItem(
            source="app_store",
            external_id=str(uuid.uuid4()),
            text=text,
            item_date=datetime(2026, 5, 1, tzinfo=UTC),
            content_hash=uuid.uuid4().hex,
        )
    )
    session.commit()


class RecordingStage(PipelineStage):
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[uuid.UUID] = []

    def run(
        self,
        session: Session,
        settings,
        run_id: uuid.UUID,
        *,
        dry_run: bool = False,
        mock: bool = False,
    ) -> StageStats:
        self.calls.append(run_id)
        return StageStats(
            stage=self.name,
            processed=1,
            details={"dry_run": dry_run, "mock": mock},
        )


class FailingStage(PipelineStage):
    name = "cluster"

    def run(self, session, settings, run_id, *, dry_run=False, mock=False) -> StageStats:
        raise RuntimeError("cluster failed")


def test_run_analysis_executes_stages_in_order(db_session):
    stages = {
        "classify": RecordingStage("classify"),
        "embed": RecordingStage("embed"),
        "cluster": RecordingStage("cluster"),
        "theme_labels": RecordingStage("theme_labels"),
        "evidence": RecordingStage("evidence"),
        "qa": RecordingStage("qa"),
        "segments": RecordingStage("segments"),
        "unmet_needs": RecordingStage("unmet_needs"),
    }

    result = run_analysis(db_session, dry_run=True, stages_by_name=stages)

    assert result.status == "completed"
    assert list(result.stats.keys()) == list(ALL_STAGES)
    for stage in stages.values():
        assert len(stage.calls) == 1


def test_run_analysis_writes_pipeline_run_metadata(db_session):
    _add_feedback_item(db_session)

    result = run_analysis(db_session, dry_run=True)

    run = db_session.get(PipelineRun, result.pipeline_run_id)
    assert run is not None
    assert run.status == "completed"
    assert run.completed_at is not None
    assert run.config_snapshot["type"] == "analysis"
    assert run.config_snapshot["dry_run"] is True
    assert set(run.item_counts.keys()) == set(ALL_STAGES)
    assert run.item_counts["classify"]["details"]["mode"] == "dry_run"


def test_run_analysis_marks_failed_and_preserves_prior_stages(db_session):
    stages = {
        "classify": RecordingStage("classify"),
        "embed": RecordingStage("embed"),
        "cluster": FailingStage(),
        "theme_labels": RecordingStage("theme_labels"),
        "evidence": RecordingStage("evidence"),
    }

    with pytest.raises(RuntimeError, match="cluster failed"):
        run_analysis(db_session, stages=["classify", "embed", "cluster"], stages_by_name=stages)

    run = db_session.query(PipelineRun).one()
    assert run.status == "failed"
    assert run.item_counts["classify"]["status"] == "completed"
    assert run.item_counts["embed"]["status"] == "completed"
    assert run.item_counts["cluster"]["status"] == "failed"
    assert "theme_labels" not in run.item_counts


def test_run_analysis_resumes_failed_run_skipping_completed_stages(db_session):
    stages = {
        "classify": RecordingStage("classify"),
        "embed": RecordingStage("embed"),
        "cluster": FailingStage(),
        "theme_labels": RecordingStage("theme_labels"),
        "evidence": RecordingStage("evidence"),
    }

    with pytest.raises(RuntimeError):
        run_analysis(db_session, stages=["classify", "embed", "cluster"], stages_by_name=stages)

    failed_run = db_session.query(PipelineRun).one()
    stages["cluster"] = RecordingStage("cluster")

    result = run_analysis(
        db_session,
        stages=["classify", "embed", "cluster"],
        run_id=failed_run.id,
        stages_by_name=stages,
    )

    assert result.status == "completed"
    assert len(stages["classify"].calls) == 1
    assert len(stages["embed"].calls) == 1
    assert len(stages["cluster"].calls) == 1


def test_run_analysis_rejects_unknown_stage(db_session):
    with pytest.raises(ValueError, match="Unknown stages"):
        run_analysis(db_session, stages=["classify", "unknown"])


def test_run_analysis_resumes_completed_run_for_intelligence_only(db_session):
    stages = {
        "classify": RecordingStage("classify"),
        "embed": RecordingStage("embed"),
        "cluster": RecordingStage("cluster"),
        "theme_labels": RecordingStage("theme_labels"),
        "evidence": RecordingStage("evidence"),
        "qa": RecordingStage("qa"),
        "segments": RecordingStage("segments"),
        "unmet_needs": RecordingStage("unmet_needs"),
    }

    completed = run_analysis(db_session, dry_run=True, stages=["classify"], stages_by_name=stages)
    run = db_session.get(PipelineRun, completed.pipeline_run_id)
    assert run is not None
    assert run.status == "completed"

    result = run_analysis(
        db_session,
        stages=list(INTELLIGENCE_STAGES),
        run_id=completed.pipeline_run_id,
        dry_run=True,
        stages_by_name=stages,
    )

    assert result.status == "completed"
    assert len(stages["qa"].calls) == 1
    assert len(stages["classify"].calls) == 1


def test_run_analysis_rejects_resume_of_completed_run_for_core_stages(db_session):
    result = run_analysis(db_session, dry_run=True, stages=["classify"])

    with pytest.raises(ValueError, match="already completed"):
        run_analysis(db_session, run_id=result.pipeline_run_id, stages=["classify"])
