import logging
import time
import uuid

from sqlalchemy.orm import Session

from core.config import Settings
from pipeline.stages.base import PipelineStage, StageStats

logger = logging.getLogger(__name__)


class ThemeLabelsStage(PipelineStage):
    name = "theme_labels"

    def run(
        self,
        session: Session,
        settings: Settings,
        run_id: uuid.UUID,
        *,
        dry_run: bool = False,
        mock: bool = False,
    ) -> StageStats:
        from pipeline.theme_labeler import label_themes_for_run

        start = time.perf_counter()

        stats = label_themes_for_run(
            session,
            settings,
            run_id,
            dry_run=dry_run,
            mock=mock,
        )

        return StageStats(
            stage=self.name,
            processed=stats.themes_created,
            skipped=0,
            duration_seconds=time.perf_counter() - start,
            details={
                "themes": stats.themes_created,
                "items_linked": stats.items_linked,
                "total_clusters": stats.total_clusters,
                "llm_calls": stats.llm_calls,
                **stats.details,
            },
        )
