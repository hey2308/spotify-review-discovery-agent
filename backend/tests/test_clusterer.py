import uuid
from datetime import UTC, datetime

import numpy as np
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from core.config import Settings
from core.embeddings import MockEmbeddingsClient
from core.vectorstore import MockVectorStore
from db.base import Base
from db.models import ClusterAssignment, FeedbackItem
from pipeline.clusterer import (
    _assign_noise,
    _merge_to_max_clusters,
    cluster_embeddings,
    cluster_feedback_items,
)
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
        MAX_THEMES=5,
        UMAP_N_NEIGHBORS=5,
        UMAP_N_COMPONENTS=2,
        UMAP_MIN_DIST=0.0,
        UMAP_RANDOM_STATE=42,
        HDBSCAN_MIN_CLUSTER_SIZE=5,
        HDBSCAN_MIN_SAMPLES=2,
        EMBEDDING_BATCH_SIZE=32,
    )


def _synthetic_embeddings(
    group_sizes: list[int],
    *,
    dim: int = 32,
    separation: float = 10.0,
    spread: float = 0.05,
) -> tuple[list[str], np.ndarray]:
    rng = np.random.default_rng(42)
    item_ids: list[str] = []
    vectors: list[np.ndarray] = []
    for group_index, size in enumerate(group_sizes):
        center = np.zeros(dim)
        center[group_index % dim] = separation * (group_index + 1)
        for _ in range(size):
            item_ids.append(str(uuid.uuid4()))
            vectors.append(center + rng.normal(0.0, spread, dim))
    return item_ids, np.array(vectors, dtype=float)


def _add_item(session: Session, *, text: str) -> FeedbackItem:
    item = FeedbackItem(
        source="play_store",
        external_id=str(uuid.uuid4()),
        text=text,
        rating=3,
        item_date=datetime(2026, 5, 1, tzinfo=UTC),
        content_hash=uuid.uuid4().hex,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def test_assign_noise_maps_points_to_nearest_cluster():
    coords = np.array(
        [
            [0.0, 0.0],
            [0.1, 0.0],
            [10.0, 10.0],
            [10.1, 10.0],
            [5.0, 5.0],
        ]
    )
    labels = np.array([0, 0, 1, 1, -1])

    updated, noise_assigned = _assign_noise(labels, coords)

    assert noise_assigned == 1
    assert updated[-1] in {0, 1}


def test_merge_to_max_clusters_enforces_cap():
    labels = np.array([0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6])
    coords = np.array(
        [
            [0.0, 0.0],
            [0.1, 0.0],
            [1.0, 0.0],
            [1.1, 0.0],
            [2.0, 0.0],
            [2.1, 0.0],
            [3.0, 0.0],
            [3.1, 0.0],
            [4.0, 0.0],
            [4.1, 0.0],
            [5.0, 0.0],
            [5.1, 0.0],
            [6.0, 0.0],
            [6.1, 0.0],
        ]
    )

    merged, merges = _merge_to_max_clusters(labels, coords, max_clusters=5)

    assert merges == 2
    assert len({int(label) for label in merged}) <= 5


def test_cluster_embeddings_finds_natural_groups(settings):
    item_ids, embeddings = _synthetic_embeddings([20, 20, 20])

    first = cluster_embeddings(item_ids, embeddings, settings)
    second = cluster_embeddings(item_ids, embeddings, settings)

    assert 1 <= first.n_clusters <= settings.max_themes
    assert first.cluster_ids == second.cluster_ids


def test_cluster_embeddings_merges_when_many_groups(settings):
    item_ids, embeddings = _synthetic_embeddings([12] * 8, separation=8.0)

    output = cluster_embeddings(item_ids, embeddings, settings)

    assert output.n_clusters <= settings.max_themes
    assert output.merges_performed >= 1


def test_cluster_embeddings_mock_mode(settings):
    item_ids, embeddings = _synthetic_embeddings([5, 5, 5, 5, 5, 5])

    output = cluster_embeddings(item_ids, embeddings, settings, mock=True)

    assert 1 <= output.n_clusters <= settings.max_themes
    assert len(output.cluster_ids) == len(item_ids)


def test_cluster_feedback_items_persists_assignments(db_session, settings):
    run_id = uuid.uuid4()
    store = MockVectorStore()
    client = MockEmbeddingsClient(dimension=32)

    for index in range(12):
        _add_item(db_session, text=f"Review text about discovery {index}")

    embed_feedback_items(
        db_session,
        settings,
        run_id,
        mock=True,
        vector_store=store,
        embeddings_client=client,
    )

    stats = cluster_feedback_items(
        db_session,
        settings,
        run_id,
        mock=True,
        vector_store=store,
    )
    db_session.commit()

    assignment_count = db_session.scalar(select(func.count()).select_from(ClusterAssignment)) or 0
    assert stats.clustered == 12
    assert 1 <= stats.n_clusters <= settings.max_themes
    assert assignment_count == 12

    clusters = db_session.scalars(
        select(ClusterAssignment.cluster_id).where(ClusterAssignment.pipeline_run_id == run_id)
    ).all()
    assert len(set(clusters)) == stats.n_clusters


def test_cluster_feedback_items_dry_run_skips_persistence(db_session, settings):
    run_id = uuid.uuid4()
    _add_item(db_session, text="Stale playlists every week")

    stats = cluster_feedback_items(db_session, settings, run_id, dry_run=True)
    db_session.commit()

    assert stats.clustered == 1
    assert db_session.scalar(select(func.count()).select_from(ClusterAssignment)) == 0


def test_cluster_feedback_items_requires_embeddings(db_session, settings):
    run_id = uuid.uuid4()
    _add_item(db_session, text="No vectors yet")

    with pytest.raises(RuntimeError, match="out of sync"):
        cluster_feedback_items(db_session, settings, run_id, mock=True)
