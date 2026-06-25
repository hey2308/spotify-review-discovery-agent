from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from core.config import get_settings
from db.models import RawDocument
from ingestion.connectors import (
    AppStoreConnector,
    CommunityConnector,
    PlayStoreConnector,
    RedditConnector,
    SocialConnector,
)
from ingestion.connectors.base import SourceConnector
from ingestion.pii import scrub_payload
from ingestion.service import expand_normalized_items, upsert_feedback_item
from ingestion.window import within_window

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def ingest_from_fixtures(
    session: Session,
    *,
    since: datetime,
    until: datetime,
    sources: list[str] | None = None,
) -> dict[str, int]:
    selected = sources or [
        "app_store",
        "play_store",
        "reddit",
        "community",
        "social",
    ]
    counts: dict[str, int] = {}

    loaders: dict[str, tuple[SourceConnector, str]] = {
        "app_store": (AppStoreConnector(), "app_store.json"),
        "play_store": (PlayStoreConnector(), "play_store.json"),
        "reddit": (RedditConnector(), "reddit.json"),
        "community": (CommunityConnector(), "community.xml"),
        "social": (SocialConnector(), "social.json"),
    }

    for source in selected:
        connector, filename = loaders[source]
        fixture_path = FIXTURE_DIR / filename
        connector_type = type(connector)
        records = connector_type.from_fixture(  # type: ignore[attr-defined]
            fixture_path, since=since, until=until
        )
        counts[source] = _persist_records(session, connector, records, since, until)

    session.commit()
    return counts


def _persist_records(
    session: Session,
    connector: SourceConnector,
    records: list,
    since: datetime,
    until: datetime,
) -> int:
    settings = get_settings()
    inserted_count = 0
    for record in records:
        if not within_window(record.item_date, since, until):
            continue

        raw_doc = RawDocument(
            source=connector.source_name,
            payload=scrub_payload(record.payload),
        )
        session.add(raw_doc)
        session.flush()

        for item in expand_normalized_items(connector, [record]):
            if not within_window(item.item_date, since, until):
                continue
            _, inserted, _rejection = upsert_feedback_item(
                session,
                item,
                raw_doc.id,
                settings=settings,
            )
            if inserted:
                inserted_count += 1
    return inserted_count
