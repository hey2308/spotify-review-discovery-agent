"""Keep feedback_themes aligned with cluster assignments and theme.cluster_id."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from core.bot_filter import is_bot_post
from db.models import ClusterAssignment, FeedbackItem, FeedbackTheme, Theme


def sync_feedback_themes_from_clusters(
    session: Session,
    run_id: uuid.UUID,
    *,
    skip_bots: bool = True,
) -> dict[str, int]:
    """Rebuild feedback_themes from cluster_assignments → themes.cluster_id."""
    themes = list(session.scalars(select(Theme).where(Theme.pipeline_run_id == run_id)).all())
    themes_by_cluster = {
        int(theme.cluster_id): theme
        for theme in themes
        if theme.cluster_id is not None
    }
    if not themes_by_cluster:
        raise RuntimeError(f"No themes with cluster_id found for run {run_id}")

    theme_ids = [theme.id for theme in themes_by_cluster.values()]
    session.execute(delete(FeedbackTheme).where(FeedbackTheme.theme_id.in_(theme_ids)))
    session.flush()

    assignments = list(
        session.scalars(
            select(ClusterAssignment).where(ClusterAssignment.pipeline_run_id == run_id)
        ).all()
    )

    linked = 0
    skipped_bots = 0
    skipped_unmapped = 0

    for assignment in assignments:
        item = session.get(FeedbackItem, assignment.feedback_item_id)
        if item is None:
            continue
        if skip_bots and is_bot_post(item.text):
            skipped_bots += 1
            continue

        theme = themes_by_cluster.get(int(assignment.cluster_id))
        if theme is None:
            skipped_unmapped += 1
            continue

        session.add(
            FeedbackTheme(
                feedback_item_id=item.id,
                theme_id=theme.id,
            )
        )
        linked += 1

    for theme in themes_by_cluster.values():
        volume = session.scalar(
            select(func.count())
            .select_from(FeedbackTheme)
            .where(FeedbackTheme.theme_id == theme.id)
        )
        theme.mention_volume = int(volume or 0)

    session.flush()
    return {
        "linked": linked,
        "skipped_bots": skipped_bots,
        "skipped_unmapped": skipped_unmapped,
    }
