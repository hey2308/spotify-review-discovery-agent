import logging
import time
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.config import Settings
from db.models import FeedbackItem
from pipeline.clusterer import cluster_feedback_items
from pipeline.stages.base import PipelineStage, StageStats

logger = logging.getLogger(__name__)


class ClusterStage(PipelineStage):
    name = "cluster"

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
        item_count = session.scalar(select(func.count()).select_from(FeedbackItem)) or 0

        if item_count == 0:
            logger.warning("No feedback items found; skipping clustering")
            return StageStats(
                stage=self.name,
                processed=0,
                skipped=0,
                duration_seconds=time.perf_counter() - start,
                details={"feedback_items": 0},
            )

        stats = cluster_feedback_items(
            session,
            settings,
            run_id,
            dry_run=dry_run,
            mock=mock,
        )

        return StageStats(
            stage=self.name,
            processed=stats.clustered,
            skipped=0,
            duration_seconds=time.perf_counter() - start,
            details={
                "feedback_items": stats.total_items,
                "n_clusters": stats.n_clusters,
                "noise_assigned": stats.noise_assigned,
                "merges_performed": stats.merges_performed,
                "max_themes": settings.max_themes,
                **stats.details,
            },
        )
