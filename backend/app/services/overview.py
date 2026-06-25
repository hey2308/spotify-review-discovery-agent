from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.schemas.common import CountsSnapshot, DateRange, to_date
from app.schemas.overview import OverviewResponse, SentimentDistribution
from app.services import resolve_active_run
from db.models import Analysis, Answer, FeedbackItem, PipelineRun, Segment, Theme, UnmetNeed


def _build_headline_insight(
    themes: list[Theme],
    sentiment: SentimentDistribution,
    total_items: int,
) -> str:
    if total_items == 0:
        return "No feedback items ingested yet."

    if themes:
        top_theme = max(themes, key=lambda theme: theme.mention_volume)
        sentiment_note = ""
        if top_theme.sentiment_score is not None and top_theme.sentiment_score < 0.45:
            sentiment_note = " with predominantly negative sentiment"
        return (
            f"'{top_theme.name}' is the largest theme "
            f"({top_theme.mention_volume} mentions{sentiment_note})."
        )

    negative_share = sentiment.negative / total_items if total_items else 0.0
    if negative_share >= 0.4:
        return (
            f"Negative sentiment dominates "
            f"({sentiment.negative} of {total_items} classified items)."
        )
    return f"Analysis covers {total_items} feedback items across multiple sources."


def _counts_for_run(session: Session, run: PipelineRun | None) -> CountsSnapshot:
    feedback_items = session.scalar(select(func.count()).select_from(FeedbackItem)) or 0
    analyses = session.scalar(select(func.count()).select_from(Analysis)) or 0

    if run is None:
        return CountsSnapshot(
            feedback_items=feedback_items,
            analyses=analyses,
        )

    themes = (
        session.scalar(
            select(func.count())
            .select_from(Theme)
            .where(Theme.pipeline_run_id == run.id)
        )
        or 0
    )
    answers = (
        session.scalar(
            select(func.count())
            .select_from(Answer)
            .where(Answer.pipeline_run_id == run.id)
        )
        or 0
    )
    segments = (
        session.scalar(
            select(func.count())
            .select_from(Segment)
            .where(Segment.pipeline_run_id == run.id)
        )
        or 0
    )
    unmet_needs = (
        session.scalar(
            select(func.count())
            .select_from(UnmetNeed)
            .where(UnmetNeed.pipeline_run_id == run.id)
        )
        or 0
    )
    return CountsSnapshot(
        feedback_items=feedback_items,
        analyses=analyses,
        themes=themes,
        answers=answers,
        segments=segments,
        unmet_needs=unmet_needs,
    )


def get_overview(session: Session) -> OverviewResponse:
    run = resolve_active_run(session)

    total_items = session.scalar(select(func.count()).select_from(FeedbackItem)) or 0
    classified_items = session.scalar(select(func.count()).select_from(Analysis)) or 0

    source_rows = session.execute(
        select(FeedbackItem.source, func.count())
        .group_by(FeedbackItem.source)
        .order_by(FeedbackItem.source)
    ).all()
    source_breakdown = {source: count for source, count in source_rows}

    sentiment_rows = session.execute(
        select(Analysis.sentiment_label, func.count())
        .where(Analysis.sentiment_label.is_not(None))
        .group_by(Analysis.sentiment_label)
    ).all()
    sentiment_counter = Counter({label: count for label, count in sentiment_rows})
    sentiment_distribution = SentimentDistribution(
        positive=sentiment_counter.get("positive", 0),
        neutral=sentiment_counter.get("neutral", 0),
        negative=sentiment_counter.get("negative", 0),
    )

    if total_items == 0:
        today = datetime.now(UTC).date()
        date_range = DateRange(from_date=today, to_date=today)
    else:
        min_date, max_date = session.execute(
            select(func.min(FeedbackItem.item_date), func.max(FeedbackItem.item_date))
        ).one()
        date_range = DateRange(
            from_date=to_date(min_date),
            to_date=to_date(max_date),
        )

    themes: list[Theme] = []
    if run is not None:
        themes = list(
            session.scalars(
                select(Theme)
                .where(Theme.pipeline_run_id == run.id)
                .order_by(Theme.mention_volume.desc())
            ).all()
        )

    headline = _build_headline_insight(themes, sentiment_distribution, classified_items)

    return OverviewResponse(
        pipeline_run_id=run.id if run else None,
        total_items=total_items,
        classified_items=classified_items,
        date_range=date_range,
        source_breakdown=source_breakdown,
        sentiment_distribution=sentiment_distribution,
        headline_insight=headline,
        counts=_counts_for_run(session, run),
    )
