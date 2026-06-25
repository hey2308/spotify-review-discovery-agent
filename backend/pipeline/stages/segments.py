import logging
import time
import uuid

from sqlalchemy.orm import Session

from core.config import Settings
from pipeline.segment_builder import build_segments_for_run
from pipeline.stages.base import PipelineStage, StageStats

logger = logging.getLogger(__name__)


class SegmentsStage(PipelineStage):
    name = "segments"

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
        stats = build_segments_for_run(
            session,
            settings,
            run_id,
            dry_run=dry_run,
            mock=mock,
        )
        return StageStats(
            stage=self.name,
            processed=stats.segments_written,
            skipped=0,
            duration_seconds=time.perf_counter() - start,
            details={
                "llm_calls": stats.llm_calls,
                **stats.details,
            },
        )
