import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import Settings, get_settings
from db.models import FeedbackItem, PipelineRun, RawDocument
from ingestion.connectors import (
    ALL_SOURCES,
    DEFAULT_SOURCES,
    AppStoreConnector,
    CommunityConnector,
    PlayStoreConnector,
    RedditConnector,
    SocialConnector,
)
from ingestion.connectors.base import SourceConnector
from ingestion.connectors.reddit import RedditConnector as RedditConnectorClass
from ingestion.filters import review_rejection_reason
from ingestion.normalize import content_hash, prepare_item
from ingestion.pii import audit_value, scrub_payload
from ingestion.types import NormalizedItem
from ingestion.window import lookback_window, within_window

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IngestionStats:
    source: str
    fetched: int = 0
    inserted: int = 0
    skipped_duplicate: int = 0
    skipped_out_of_window: int = 0
    skipped_empty: int = 0
    skipped_too_short: int = 0
    skipped_non_english: int = 0
    skipped_empty_after_clean: int = 0


@dataclass(slots=True)
class IngestionResult:
    pipeline_run_id: uuid.UUID
    stats: dict[str, IngestionStats]


def build_connectors(settings: Settings) -> dict[str, SourceConnector]:
    return {
        "app_store": AppStoreConnector(),
        "play_store": PlayStoreConnector(
            max_reviews=settings.play_store_max_reviews,
            page_size=settings.play_store_page_size,
        ),
        "reddit": RedditConnector(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent,
        ),
        "community": CommunityConnector(feed_url=settings.community_feed_url),
        "social": SocialConnector(
            bluesky_queries=settings.bluesky_search_queries,
            mastodon_instances=settings.mastodon_instances,
            mastodon_tags=settings.mastodon_tags,
            max_items=settings.social_max_items,
            bluesky_page_size=settings.bluesky_page_size,
            mastodon_page_size=settings.mastodon_page_size,
            bluesky_slice_days=settings.bluesky_slice_days,
            mastodon_max_pages=settings.mastodon_max_pages,
            throttle_seconds=settings.ingest_throttle_seconds,
            user_agent=settings.reddit_user_agent,
        ),
    }


def expand_normalized_items(connector: SourceConnector, records: list) -> list[NormalizedItem]:
    if isinstance(connector, RedditConnectorClass):
        return connector.expand_records(records)

    items: list[NormalizedItem] = []
    for record in records:
        item = connector.normalize(record)
        if item:
            items.append(item)
    return items


def upsert_feedback_item(
    session: Session,
    item: NormalizedItem,
    raw_document_id: uuid.UUID,
    *,
    settings: Settings | None = None,
) -> tuple[FeedbackItem | None, bool, str | None]:
    settings = settings or get_settings()
    prepared = prepare_item(item)
    rejection = review_rejection_reason(
        prepared.text,
        min_words=settings.ingest_min_words,
        english_only=settings.ingest_english_only,
    )
    if rejection:
        return None, False, rejection

    hash_value = content_hash(prepared.source, prepared.text)

    existing = session.scalar(
        select(FeedbackItem).where(
            FeedbackItem.source == prepared.source,
            FeedbackItem.content_hash == hash_value,
        )
    )
    if existing:
        return existing, False, None

    feedback = FeedbackItem(
        source=prepared.source,
        external_id=prepared.external_id,
        title=prepared.title,
        text=prepared.text,
        rating=prepared.rating,
        item_date=prepared.item_date,
        content_hash=hash_value,
        raw_document_id=raw_document_id,
    )
    session.add(feedback)
    session.flush()
    return feedback, True, None


def ingest_source(
    session: Session,
    connector: SourceConnector,
    *,
    since: datetime,
    until: datetime,
    pipeline_run_id: uuid.UUID,
    throttle_seconds: float = 0.0,
    settings: Settings | None = None,
) -> IngestionStats:
    settings = settings or get_settings()
    stats = IngestionStats(source=connector.source_name)
    if throttle_seconds:
        time.sleep(throttle_seconds)

    records = connector.fetch(since=since, until=until)
    stats.fetched = len(records)

    for record in records:
        if not within_window(record.item_date, since, until):
            stats.skipped_out_of_window += 1
            continue

        raw_doc = RawDocument(
            source=connector.source_name,
            payload=scrub_payload(record.payload),
        )
        session.add(raw_doc)
        session.flush()

        normalized_items = expand_normalized_items(connector, [record])
        if not normalized_items:
            stats.skipped_empty += 1
            continue

        for item in normalized_items:
            if not within_window(item.item_date, since, until):
                stats.skipped_out_of_window += 1
                continue
            _, inserted, rejection = upsert_feedback_item(
                session,
                item,
                raw_doc.id,
                settings=settings,
            )
            if rejection == "too_short":
                stats.skipped_too_short += 1
                continue
            if rejection == "non_english":
                stats.skipped_non_english += 1
                continue
            if rejection == "empty_after_clean":
                stats.skipped_empty_after_clean += 1
                continue
            if inserted:
                stats.inserted += 1
            else:
                stats.skipped_duplicate += 1

    return stats


def ingest_all(
    session: Session,
    *,
    sources: list[str] | None = None,
    months: int = 6,
    settings: Settings | None = None,
) -> IngestionResult:
    settings = settings or get_settings()
    since, until = lookback_window(months)
    selected_sources = sources or list(DEFAULT_SOURCES)
    connectors = build_connectors(settings)

    pipeline_run = PipelineRun(
        status="running",
        config_snapshot={
            "sources": selected_sources,
            "months": months,
            "since": since.isoformat(),
            "until": until.isoformat(),
        },
        item_counts={},
    )
    session.add(pipeline_run)
    session.flush()

    stats_by_source: dict[str, IngestionStats] = {}
    for source_name in selected_sources:
        connector = connectors[source_name]
        try:
            stats = ingest_source(
                session,
                connector,
                since=since,
                until=until,
                pipeline_run_id=pipeline_run.id,
                throttle_seconds=settings.ingest_throttle_seconds,
                settings=settings,
            )
        except Exception:
            logger.exception("Ingestion failed for source %s", source_name)
            stats = IngestionStats(source=source_name)
        stats_by_source[source_name] = stats

    pipeline_run.status = "completed"
    pipeline_run.completed_at = datetime.now(UTC)
    pipeline_run.item_counts = {
        source: {
            "fetched": stat.fetched,
            "inserted": stat.inserted,
            "skipped_duplicate": stat.skipped_duplicate,
            "skipped_out_of_window": stat.skipped_out_of_window,
            "skipped_empty": stat.skipped_empty,
            "skipped_too_short": stat.skipped_too_short,
            "skipped_non_english": stat.skipped_non_english,
            "skipped_empty_after_clean": stat.skipped_empty_after_clean,
        }
        for source, stat in stats_by_source.items()
    }
    session.commit()
    return IngestionResult(pipeline_run_id=pipeline_run.id, stats=stats_by_source)


def audit_stored_data(session: Session) -> list[str]:
    hits: list[str] = []
    for raw_doc in session.scalars(select(RawDocument)).all():
        audit_value(raw_doc.payload, hits, path=f"raw_documents.{raw_doc.id}")
    for item in session.scalars(select(FeedbackItem)).all():
        audit_value(item.title, hits, path=f"feedback_items.{item.id}.title")
        audit_value(item.text, hits, path=f"feedback_items.{item.id}.text")
    return hits
