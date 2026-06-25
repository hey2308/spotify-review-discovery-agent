import logging
import time
import uuid

from sqlalchemy.orm import Session

from core.config import Settings
from pipeline.evidence_builder import attach_theme_evidence
from pipeline.stages.base import PipelineStage, StageStats

logger = logging.getLogger(__name__)


class EvidenceStage(PipelineStage):
    name = "evidence"

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

        stats = attach_theme_evidence(
            session,
            settings,
            run_id,
            dry_run=dry_run,
            mock=mock,
        )

        return StageStats(
            stage=self.name,
            processed=stats.themes_updated,
            skipped=0,
            duration_seconds=time.perf_counter() - start,
            details={
                "representative_quotes": stats.quotes_selected,
                "report_path": stats.report_path,
                **stats.details,
            },
        )
