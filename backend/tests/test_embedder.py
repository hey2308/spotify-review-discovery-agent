import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from core.config import Settings
from core.embeddings import MockEmbeddingsClient
from core.vectorstore import MockVectorStore
from db.base import Base
from db.models import FeedbackItem
from pipeline.embedder import embed_feedback_items


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
def settings() -> Settings:
    return Settings(
        _env_file=None,
        DATABASE_URL="sqlite+pysqlite:///:memory:",
        GROQ_API_KEY=None,
        EMBEDDING_BATCH_SIZE=2,
        EMBEDDING_MAX_TEXT_CHARS=500,
        EMBEDDING_MODEL="BAAI/bge-small-en-v1.5",
    )


def _add_item(
    session: Session,
    *,
    text: str,
    content_hash: str | None = None,
) -> FeedbackItem:
    item = FeedbackItem(
        source="play_store",
        external_id=str(uuid.uuid4()),
        text=text,
        rating=2,
        item_date=datetime(2026, 5, 1, tzinfo=UTC),
        content_hash=content_hash or uuid.uuid4().hex,
    )
    session.add(item)
    session.commit()
    return item


def test_embed_feedback_items_writes_vectors(db_session, settings):
    run_id = uuid.uuid4()
    store = MockVectorStore()
    client = MockEmbeddingsClient()
    _add_item(db_session, text="Spotify discovery feels stale and repetitive")
    _add_item(db_session, text="Love the recommendations lately")

    stats = embed_feedback_items(
        db_session,
        settings,
        run_id,
        mock=True,
        vector_store=store,
        embeddings_client=client,
    )

    assert stats.embedded == 2
    assert stats.cached == 0
    assert store.count() == 2


def test_embed_feedback_items_skips_cached_hashes(db_session, settings):
    run_id = uuid.uuid4()
    store = MockVectorStore()
    client = MockEmbeddingsClient()
    _add_item(db_session, text="Same stale playlists every day", content_hash="fixed-hash")

    first = embed_feedback_items(
        db_session,
        settings,
        run_id,
        mock=True,
        vector_store=store,
        embeddings_client=client,
    )
    second = embed_feedback_items(
        db_session,
        settings,
        run_id,
        mock=True,
        vector_store=store,
        embeddings_client=client,
    )

    assert first.embedded == 1
    assert second.embedded == 0
    assert second.cached == 1
    assert store.count() == 1


def test_embed_feedback_items_reembeds_when_content_hash_changes(db_session, settings):
    run_id = uuid.uuid4()
    store = MockVectorStore()
    client = MockEmbeddingsClient()
    item = _add_item(db_session, text="Original review", content_hash="hash-v1")

    embed_feedback_items(
        db_session,
        settings,
        run_id,
        mock=True,
        vector_store=store,
        embeddings_client=client,
    )

    item.text = "Updated review with new discovery complaint"
    item.content_hash = "hash-v2"
    db_session.commit()

    stats = embed_feedback_items(
        db_session,
        settings,
        run_id,
        mock=True,
        vector_store=store,
        embeddings_client=client,
    )

    assert stats.embedded == 1
    assert store.list_entries()[str(item.id)]["content_hash"] == "hash-v2"


def test_embed_feedback_items_deletes_orphan_vectors(db_session, settings):
    run_id = uuid.uuid4()
    store = MockVectorStore()
    client = MockEmbeddingsClient()
    _add_item(db_session, text="Active review")

    embed_feedback_items(
        db_session,
        settings,
        run_id,
        mock=True,
        vector_store=store,
        embeddings_client=client,
    )

    orphan_id = str(uuid.uuid4())
    store.upsert(
        ids=[orphan_id],
        embeddings=client.embed(["orphan review"]),
        documents=["orphan review"],
        metadatas=[{"source": "play_store", "content_hash": "orphan", "item_date": "2026-01-01"}],
    )
    assert store.count() == 2

    stats = embed_feedback_items(
        db_session,
        settings,
        run_id,
        mock=True,
        vector_store=store,
        embeddings_client=client,
    )

    assert stats.deleted_orphans == 1
    assert store.count() == 1
    assert orphan_id not in store.list_entries()


def test_embed_dry_run_does_not_write(db_session, settings):
    run_id = uuid.uuid4()
    store = MockVectorStore()
    _add_item(db_session, text="Dry run only")

    stats = embed_feedback_items(
        db_session,
        settings,
        run_id,
        dry_run=True,
        vector_store=store,
    )

    assert stats.embedded == 1
    assert store.count() == 0


def test_embed_query_roundtrip_to_postgres_id(db_session, settings):
    run_id = uuid.uuid4()
    store = MockVectorStore()
    client = MockEmbeddingsClient()
    anchor = _add_item(db_session, text="Spotify discovery is broken and repetitive")
    _add_item(db_session, text="Great sound quality, love this app")

    embed_feedback_items(
        db_session,
        settings,
        run_id,
        mock=True,
        vector_store=store,
        embeddings_client=client,
    )

    query_vector = client.embed(["Spotify discovery feels repetitive"])[0]
    results = store.query(query_vector, n_results=1)
    returned_id = results["ids"][0][0]

    item = db_session.scalar(select(FeedbackItem).where(FeedbackItem.id == uuid.UUID(returned_id)))
    assert item is not None
    assert item.id == anchor.id
