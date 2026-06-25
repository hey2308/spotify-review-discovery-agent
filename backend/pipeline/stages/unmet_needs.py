import logging
import time
import uuid

from sqlalchemy.orm import Session

from core.config import Settings
from pipeline.stages.base import PipelineStage, StageStats
from pipeline.unmet_needs_extractor import extract_unmet_needs_for_run

logger = logging.getLogger(__name__)


class UnmetNeedsStage(PipelineStage):
    name = "unmet_needs"

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
        stats = extract_unmet_needs_for_run(
            session,
            settings,
            run_id,
            dry_run=dry_run,
            mock=mock,
        )
        return StageStats(
            stage=self.name,
            processed=stats.needs_written,
            skipped=0,
            duration_seconds=time.perf_counter() - start,
            details={
                "llm_calls": stats.llm_calls,
                **stats.details,
            },
        )
