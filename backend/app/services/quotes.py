import math
import uuid
from datetime import UTC, datetime, time

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.schemas.quotes import PaginatedQuotes, QuoteFilters, QuoteItem
from app.services import resolve_active_run
from core.bot_filter import sql_bot_exclusion_clauses
from core.discovery_filter import sql_discovery_inclusion_clauses, sql_discovery_priority
from db.models import Analysis, FeedbackItem, FeedbackTheme, Theme

ThemeLinkMap = dict[uuid.UUID, list[tuple[uuid.UUID, str]]]


def _theme_map_for_run(session: Session, run_id: uuid.UUID | None) -> ThemeLinkMap:
    if run_id is None:
        return {}

    rows = session.execute(
        select(FeedbackTheme.feedback_item_id, Theme.id, Theme.name)
        .join(Theme, Theme.id == FeedbackTheme.theme_id)
        .where(Theme.pipeline_run_id == run_id)
    ).all()

    mapping: dict = {}
    for item_id, theme_id, theme_name in rows:
        mapping.setdefault(item_id, []).append((theme_id, theme_name))
    return mapping


def list_quotes(session: Session, filters: QuoteFilters) -> PaginatedQuotes:
    run = resolve_active_run(session)
    page = max(filters.page, 1)
    page_size = min(max(filters.page_size, 1), 100)

    query = (
        select(FeedbackItem)
        .outerjoin(Analysis, Analysis.feedback_item_id == FeedbackItem.id)
        .options(selectinload(FeedbackItem.analysis))
        .where(sql_bot_exclusion_clauses(FeedbackItem.text))
    )

    if filters.theme_id is not None:
        query = query.join(
            FeedbackTheme,
            FeedbackTheme.feedback_item_id == FeedbackItem.id,
        ).where(FeedbackTheme.theme_id == filters.theme_id)

    if filters.source:
        query = query.where(FeedbackItem.source == filters.source)

    if filters.rating is not None:
        query = query.where(FeedbackItem.rating == filters.rating)
    else:
        if filters.rating_min is not None:
            query = query.where(FeedbackItem.rating >= filters.rating_min)
        if filters.rating_max is not None:
            query = query.where(FeedbackItem.rating <= filters.rating_max)

    if filters.date_from is not None:
        start = datetime.combine(filters.date_from, time.min, tzinfo=UTC)
        query = query.where(FeedbackItem.item_date >= start)
    if filters.date_to is not None:
        end = datetime.combine(filters.date_to, time.max, tzinfo=UTC)
        query = query.where(FeedbackItem.item_date <= end)

    if filters.q:
        pattern = f"%{filters.q.strip()}%"
        query = query.where(
            or_(
                FeedbackItem.text.ilike(pattern),
                FeedbackItem.title.ilike(pattern),
            )
        )

    if filters.discovery_only:
        query = query.where(
            sql_discovery_inclusion_clauses(
                text_column=FeedbackItem.text,
                intent_column=Analysis.intent,
                behavior_signals_column=Analysis.behavior_signals,
            )
        )

    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total = session.scalar(count_query) or 0
    total_pages = math.ceil(total / page_size) if total else 0

    order_columns = [FeedbackItem.item_date.desc(), FeedbackItem.id.asc()]
    if filters.discovery_only:
        order_columns = [
            sql_discovery_priority(intent_column=Analysis.intent),
            *order_columns,
        ]

    items = list(
        session.scalars(
            query.order_by(*order_columns)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )

    theme_map = _theme_map_for_run(session, run.id if run else None)
    quote_items: list[QuoteItem] = []
    for item in items:
        themes = theme_map.get(item.id, [])
        quote_items.append(
            QuoteItem(
                id=item.id,
                text=item.text,
                source=item.source,
                rating=item.rating,
                item_date=item.item_date,
                sentiment_label=item.analysis.sentiment_label if item.analysis else None,
                sentiment_score=item.analysis.sentiment_score if item.analysis else None,
                theme_ids=[theme_id for theme_id, _ in themes],
                theme_names=[name for _, name in themes],
            )
        )

    return PaginatedQuotes(
        items=quote_items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )
