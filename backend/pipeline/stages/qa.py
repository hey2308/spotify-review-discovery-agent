import logging
import time
import uuid

from sqlalchemy.orm import Session

from core.config import Settings
from pipeline.qa_synthesizer import synthesize_qa_for_run
from pipeline.stages.base import PipelineStage, StageStats

logger = logging.getLogger(__name__)


class QAStage(PipelineStage):
    name = "qa"

    def run(
        self,
        session: Session,
        settings: Settings,
        run_id: uuid.UUID,
        *,
        dry_run: bool = False,
        mock: bool = False,
    ) -> StageStats:
        start = time.perf_counter()
        stats = synthesize_qa_for_run(
            session,
            settings,
            run_id,
            dry_run=dry_run,
            mock=mock,
        )
        return StageStats(
            stage=self.name,
            processed=stats.answers_written,
            skipped=stats.low_confidence,
            duration_seconds=time.perf_counter() - start,
            details={
                "llm_calls": stats.llm_calls,
                "low_confidence": stats.low_confidence,
                **stats.details,
            },
        )
