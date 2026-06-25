from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.base import Base
from db.models import FeedbackItem, PipelineRun, RawDocument
from ingestion.connectors import (
    AppStoreConnector,
    CommunityConnector,
    PlayStoreConnector,
    RedditConnector,
    SocialConnector,
)
from ingestion.connectors.social import strip_html
from ingestion.fixture_loader import FIXTURE_DIR, ingest_from_fixtures
from ingestion.pii import REDACTED, audit_value, contains_pii, scrub_text
from ingestion.service import audit_stored_data, ingest_all
from ingestion.window import lookback_window, within_window


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def window() -> tuple[datetime, datetime]:
    return lookback_window(6)


@pytest.mark.parametrize(
    ("connector_cls", "fixture_name", "expected_rating"),
    [
        (AppStoreConnector, "app_store.json", 2),
        (PlayStoreConnector, "play_store.json", 2),
        (RedditConnector, "reddit.json", None),
        (CommunityConnector, "community.xml", None),
        (SocialConnector, "social.json", None),
    ],
)
def test_connectors_parse_fixtures(connector_cls, fixture_name, expected_rating, window):
    since, until = window
    records = connector_cls.from_fixture(FIXTURE_DIR / fixture_name, since=since, until=until)
    assert records

    connector = connector_cls()
    if connector_cls is RedditConnector:
        items = connector.expand_records(records)
    else:
        items = [connector.normalize(record) for record in records]
        items = [item for item in items if item]

    assert items
    first = items[0]
    assert first.source == connector.source_name
    assert first.text
    assert within_window(first.item_date, since, until)
    assert first.rating == expected_rating


def test_pii_scrubber_redacts_sensitive_values():
    raw = "Contact user@example.com or @handle or device id: abc123xyz789"
    cleaned = scrub_text(raw)
    assert "user@example.com" not in cleaned
    assert "@handle" not in cleaned
    assert REDACTED in cleaned
    assert contains_pii(cleaned) is False


def test_fixture_ingestion_is_idempotent(db_session, window):
    since, until = window
    first = ingest_from_fixtures(db_session, since=since, until=until)
    total_first = sum(first.values())

    second = ingest_from_fixtures(db_session, since=since, until=until)
    total_second = sum(second.values())

    assert total_first > 0
    assert total_second == 0

    stored = db_session.query(FeedbackItem).count()
    assert stored == total_first


def test_content_hash_dedup_collapses_duplicate_play_store_reviews(db_session, window):
    since, until = window
    ingest_from_fixtures(db_session, since=since, until=until, sources=["play_store"])

    play_store_items = (
        db_session.query(FeedbackItem).filter(FeedbackItem.source == "play_store").all()
    )
    assert len(play_store_items) == 1


def test_pii_audit_returns_zero_hits_after_ingestion(db_session, window):
    since, until = window
    ingest_from_fixtures(db_session, since=since, until=until)
    hits = audit_stored_data(db_session)
    assert hits == []


def test_items_linked_to_raw_documents(db_session, window):
    since, until = window
    ingest_from_fixtures(db_session, since=since, until=until)

    items = db_session.query(FeedbackItem).all()
    assert items
    for item in items:
        assert item.raw_document_id is not None
        raw = db_session.get(RawDocument, item.raw_document_id)
        assert raw is not None
        assert raw.source == item.source


def test_out_of_window_items_are_excluded(db_session):
    since = datetime(2026, 4, 1, tzinfo=UTC)
    until = datetime(2026, 6, 1, tzinfo=UTC)
    ingest_from_fixtures(db_session, since=since, until=until, sources=["community"])

    community_items = (
        db_session.query(FeedbackItem).filter(FeedbackItem.source == "community").all()
    )
    assert community_items == []


def test_ingest_all_records_pipeline_run(db_session, monkeypatch):
    since, until = lookback_window(6)

    class FakeConnector:
        source_name = "app_store"

        def fetch(self, since, until):
            return AppStoreConnector.from_fixture(
                FIXTURE_DIR / "app_store.json",
                since=since,
                until=until,
            )

        def normalize(self, record):
            return AppStoreConnector().normalize(record)

    def fake_build_connectors(settings):
        return {name: FakeConnector() for name in ["app_store"]}

    monkeypatch.setattr("ingestion.service.build_connectors", fake_build_connectors)

    result = ingest_all(db_session, sources=["app_store"], months=6)
    assert result.pipeline_run_id is not None
    assert result.stats["app_store"].inserted > 0

    run = db_session.get(PipelineRun, result.pipeline_run_id)
    assert run is not None
    assert run.status == "completed"
    assert run.item_counts["app_store"]["inserted"] > 0


def test_audit_value_detects_unscrubbed_email():
    hits: list[str] = []
    audit_value({"note": "email me at secret@example.com"}, hits)
    assert hits


def test_play_store_pagination_loops_until_max_reviews(monkeypatch, window):
    since, until = window
    page_size = 200
    max_reviews = 1000
    calls: list[int] = []

    def fake_reviews(
        app_id,
        lang="en",
        country="us",
        sort=None,
        count=100,
        continuation_token=None,
        **kwargs,
    ):
        calls.append(count)
        assert count == page_size
        batch = [
            {
                "reviewId": f"review-{continuation_token or 'start'}-{index}",
                "content": f"Review text {index}",
                "score": 4,
                "at": datetime(2026, 5, 1, tzinfo=UTC),
            }
            for index in range(page_size)
        ]
        next_token = f"token-{len(calls)}" if len(calls) < (max_reviews // page_size) else None
        return batch, next_token

    import google_play_scraper

    monkeypatch.setattr(google_play_scraper, "reviews", fake_reviews)

    connector = PlayStoreConnector(max_reviews=max_reviews, page_size=page_size)
    records = connector.fetch(since, until)

    assert len(calls) == max_reviews // page_size
    assert len(records) == max_reviews


def test_play_store_pagination_stops_when_batch_older_than_window(monkeypatch):
    since = datetime(2026, 4, 1, tzinfo=UTC)
    until = datetime(2026, 6, 1, tzinfo=UTC)

    def fake_reviews(
        app_id,
        lang="en",
        country="us",
        sort=None,
        count=100,
        continuation_token=None,
        **kwargs,
    ):
        if continuation_token is None:
            batch = [
                {
                    "reviewId": "recent-1",
                    "content": "Recent review",
                    "score": 3,
                    "at": datetime(2026, 5, 15, tzinfo=UTC),
                }
            ]
            return batch, "older-page"

        batch = [
            {
                "reviewId": "old-1",
                "content": "Old review",
                "score": 2,
                "at": datetime(2026, 1, 1, tzinfo=UTC),
            }
        ]
        return batch, "another-page"

    import google_play_scraper

    monkeypatch.setattr(google_play_scraper, "reviews", fake_reviews)

    connector = PlayStoreConnector(max_reviews=1000, page_size=200)
    records = connector.fetch(since, until)

    assert len(records) == 1
    assert records[0].external_id == "recent-1"


def test_strip_html_removes_markup():
    assert strip_html("<p>Spotify <strong>discovery</strong> is stale.</p>") == (
        "Spotify discovery is stale."
    )


def test_mastodon_tag_timeline_filters_broad_spotify_tag(window):
    since, until = window
    connector = SocialConnector()
    statuses = [
        {
            "id": "1",
            "content": "<p>Spotify recommendations keep repeating.</p>",
            "created_at": "2026-05-01T08:00:00.000Z",
        },
        {
            "id": "2",
            "content": "<p>Now playing on BBC 6 Music.</p>",
            "created_at": "2026-05-02T08:00:00.000Z",
        },
    ]
    records = connector.parse_mastodon_tag_payload(
        statuses,
        instance="mastodon.social",
        tag="spotify",
        since=since,
        until=until,
    )
    assert len(records) == 1
    assert "recommendations" in records[0].payload["text"]


def test_mastodon_discovery_tag_keeps_all_posts(window):
    since, until = window
    connector = SocialConnector()
    statuses = [
        {
            "id": "9",
            "content": "<p>Hello fediverse.</p>",
            "created_at": "2026-05-01T08:00:00.000Z",
        }
    ]
    records = connector.parse_mastodon_tag_payload(
        statuses,
        instance="mastodon.social",
        tag="spotifydiscovery",
        since=since,
        until=until,
    )
    assert len(records) == 1


def test_mastodon_pagination_follows_max_id(monkeypatch, window):
    since, until = window
    pages = [
        [
            {
                "id": "200",
                "content": "<p>Spotify playlist keeps repeating.</p>",
                "created_at": "2026-05-02T08:00:00.000Z",
            }
        ],
        [
            {
                "id": "100",
                "content": "<p>Spotify algorithm feels stale.</p>",
                "created_at": "2026-05-01T08:00:00.000Z",
            }
        ],
    ]
    max_ids: list[str | None] = []

    class FakeResponse:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def json(self):
            return self._payload

    def fake_get(url, params=None):
        max_ids.append((params or {}).get("max_id"))
        if (params or {}).get("max_id") == "100":
            return FakeResponse([])
        page_index = 0 if (params or {}).get("max_id") is None else 1
        return FakeResponse(pages[page_index])

    connector = SocialConnector(
        bluesky_queries=[],
        mastodon_instances=["https://mastodon.social"],
        mastodon_tags=["spotify"],
        max_items=10,
        mastodon_page_size=1,
        throttle_seconds=0,
    )
    monkeypatch.setattr(connector._client, "get", fake_get)

    records = connector.fetch(since, until)
    assert max_ids[:2] == [None, "200"]
    assert len(records) == 2


def test_social_fetch_stops_at_max_items(monkeypatch, window):
    since, until = window

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "posts": [
                    {
                        "uri": f"at://example/app.bsky.feed.post/{index}",
                        "record": {
                            "text": f"spotify discovery post {index}",
                            "createdAt": "2026-05-01T08:00:00.000Z",
                        },
                    }
                    for index in range(5)
                ]
            }

    connector = SocialConnector(
        mastodon_instances=[],
        mastodon_tags=[],
        max_items=3,
        bluesky_slice_days=180,
        throttle_seconds=0,
    )
    monkeypatch.setattr(connector._client, "get", lambda *args, **kwargs: FakeResponse())

    records = connector.fetch(since, until)
    assert len(records) == 3
