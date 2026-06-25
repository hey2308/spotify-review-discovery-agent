import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.schemas.themes import SubPattern, ThemeDetail, ThemeQuote, ThemesResponse, ThemeSummary
from app.services import parse_uuid_list, require_active_run
from db.models import Analysis, FeedbackItem, FeedbackTheme, Theme


def _theme_summaries(themes: list[Theme]) -> list[ThemeSummary]:
    summaries: list[ThemeSummary] = []
    for theme in themes:
        quote_ids = parse_uuid_list(theme.representative_quote_ids or [])
        summaries.append(
            ThemeSummary(
                id=theme.id,
                name=theme.name,
                summary=theme.summary,
                mention_volume=theme.mention_volume,
                sentiment_score=theme.sentiment_score,
                representative_quote_ids=quote_ids,
            )
        )
    return summaries


def list_themes(session: Session) -> ThemesResponse:
    run = require_active_run(session)
    themes = list(
        session.scalars(
            select(Theme)
            .where(Theme.pipeline_run_id == run.id)
            .order_by(Theme.mention_volume.desc())
        ).all()
    )
    return ThemesResponse(
        items=_theme_summaries(themes),
        pipeline_run_id=run.id,
    )


def _sub_patterns(session: Session, theme_id: uuid.UUID) -> list[SubPattern]:
    rows = session.execute(
        select(Analysis.intent, func.count())
        .join(FeedbackItem, FeedbackItem.id == Analysis.feedback_item_id)
        .join(FeedbackTheme, FeedbackTheme.feedback_item_id == FeedbackItem.id)
        .where(FeedbackTheme.theme_id == theme_id, Analysis.intent.is_not(None))
        .group_by(Analysis.intent)
        .order_by(func.count().desc())
    ).all()
    return [SubPattern(label=label, count=count) for label, count in rows]


def _theme_quotes(session: Session, theme: Theme) -> list[ThemeQuote]:
    quote_ids = parse_uuid_list(theme.representative_quote_ids or [])
    if quote_ids:
        items = list(
            session.scalars(
                select(FeedbackItem)
                .where(FeedbackItem.id.in_(quote_ids))
                .options(selectinload(FeedbackItem.analysis))
            ).all()
        )
        items_by_id = {item.id: item for item in items}
        ordered = [items_by_id[item_id] for item_id in quote_ids if item_id in items_by_id]
    else:
        ordered = list(
            session.scalars(
                select(FeedbackItem)
                .join(FeedbackTheme, FeedbackTheme.feedback_item_id == FeedbackItem.id)
                .where(FeedbackTheme.theme_id == theme.id)
                .options(selectinload(FeedbackItem.analysis))
                .order_by(FeedbackItem.item_date.desc())
                .limit(5)
            ).all()
        )

    quotes: list[ThemeQuote] = []
    for item in ordered:
        quotes.append(
            ThemeQuote(
                id=item.id,
                text=item.text,
                source=item.source,
                sentiment_label=item.analysis.sentiment_label if item.analysis else None,
            )
        )
    return quotes


def get_theme(session: Session, theme_id: uuid.UUID) -> ThemeDetail:
    run = require_active_run(session)
    theme = session.get(Theme, theme_id)
    if theme is None or theme.pipeline_run_id != run.id:
        raise HTTPException(status_code=404, detail="Theme not found")

    summary = _theme_summaries([theme])[0]
    return ThemeDetail(
        **summary.model_dump(),
        quotes=_theme_quotes(session, theme),
        sub_patterns=_sub_patterns(session, theme.id),
    )
