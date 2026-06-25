import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from core.config import Settings
from core.embeddings import MockEmbeddingsClient
from core.vectorstore import MockVectorStore
from db.base import Base
from db.models import (
    Analysis,
    ClusterAssignment,
    FeedbackItem,
    FeedbackTheme,
    Theme,
)
from pipeline.embedder import embed_feedback_items
from pipeline.evidence_builder import attach_theme_evidence
from pipeline.theme_labeler import label_themes_for_run


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
        THEME_LABEL_QUOTE_COUNT=3,
        THEME_REPRESENTATIVE_QUOTES=2,
        ANALYSIS_EXPORT_DIR="../data/analyzed-test",
        EMBEDDING_BATCH_SIZE=16,
    )


def _add_item(
    session: Session,
    *,
    text: str,
    source: str = "play_store",
    rating: int = 2,
) -> FeedbackItem:
    item = FeedbackItem(
        source=source,
        external_id=str(uuid.uuid4()),
        text=text,
        rating=rating,
        item_date=datetime(2026, 5, 1, tzinfo=UTC),
        content_hash=uuid.uuid4().hex,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def _add_analysis(session: Session, item: FeedbackItem, run_id: uuid.UUID, score: float) -> None:
    session.add(
        Analysis(
            feedback_item_id=item.id,
            sentiment_label="negative" if score < 0.5 else "positive",
            sentiment_score=score,
            intent="discover_new_music",
            behavior_signals={"signals": ["repeats_same_content"]},
            segment_hint="casual_listener",
            pipeline_run_id=run_id,
        )
    )
    session.commit()


def _assign_clusters(
    session: Session,
    run_id: uuid.UUID,
    assignments: list[tuple[FeedbackItem, int]],
) -> None:
    session.add_all(
        [
            ClusterAssignment(
                feedback_item_id=item.id,
                pipeline_run_id=run_id,
                cluster_id=cluster_id,
            )
            for item, cluster_id in assignments
        ]
    )
    session.commit()


class FakeThemeLLM:
    def __init__(self) -> None:
        self.calls = 0

    def complete_json(self, prompt, *, model=None, system=None, max_tokens=8192):
        del max_tokens
        self.calls += 1
        return {
            "name": "Discovery Frustration",
            "summary": "Users want fresher recommendations and more variety.",
        }


def test_label_themes_creates_rows_and_links(db_session, settings):
    run_id = uuid.uuid4()
    store = MockVectorStore()
    client = MockEmbeddingsClient(dimension=32)

    stale_items = [
        _add_item(db_session, text="Same stale playlists every week"),
        _add_item(db_session, text="Recommendations repeat the same artists"),
    ]
    quality_items = [
        _add_item(db_session, text="App crashes whenever I open playlists"),
    ]

    for item in stale_items + quality_items:
        _add_analysis(db_session, item, run_id, 0.2)

    _assign_clusters(
        db_session,
        run_id,
        [(item, 0) for item in stale_items] + [(quality_items[0], 1)],
    )

    embed_feedback_items(
        db_session,
        settings,
        run_id,
        mock=True,
        vector_store=store,
        embeddings_client=client,
    )

    stats = label_themes_for_run(
        db_session,
        settings,
        run_id,
        mock=True,
        vector_store=store,
    )
    db_session.commit()

    themes = db_session.scalars(select(Theme).where(Theme.pipeline_run_id == run_id)).all()
    links = db_session.scalar(select(func.count()).select_from(FeedbackTheme)) or 0

    assert stats.themes_created == 2
    assert stats.items_linked == 3
    assert len(themes) == 2
    assert links == 3
    assert all(theme.name and theme.summary for theme in themes)
    assert all(theme.mention_volume > 0 for theme in themes)
    assert themes[0].sentiment_score is not None


def test_label_themes_uses_groq_large_model(db_session, settings):
    run_id = uuid.uuid4()
    store = MockVectorStore()
    client = MockEmbeddingsClient(dimension=32)
    item = _add_item(db_session, text="Discover weekly keeps repeating artists")
    _add_analysis(db_session, item, run_id, 0.3)
    _assign_clusters(db_session, run_id, [(item, 0)])
    embed_feedback_items(
        db_session,
        settings,
        run_id,
        mock=True,
        vector_store=store,
        embeddings_client=client,
    )

    llm = FakeThemeLLM()
    settings_with_key = settings.model_copy(update={"groq_api_key": "test-key"})
    stats = label_themes_for_run(
        db_session,
        settings_with_key,
        run_id,
        llm=llm,
        vector_store=store,
    )
    db_session.commit()

    theme = db_session.scalar(select(Theme).where(Theme.pipeline_run_id == run_id))
    assert llm.calls == 1
    assert stats.llm_calls == 1
    assert theme is not None
    assert theme.name == "Discovery Frustration"


def test_label_themes_replaces_existing_run_themes(db_session, settings):
    run_id = uuid.uuid4()
    store = MockVectorStore()
    client = MockEmbeddingsClient(dimension=32)
    item = _add_item(db_session, text="Stale discovery feed")
    _assign_clusters(db_session, run_id, [(item, 0)])
    embed_feedback_items(
        db_session,
        settings,
        run_id,
        mock=True,
        vector_store=store,
        embeddings_client=client,
    )

    label_themes_for_run(db_session, settings, run_id, mock=True, vector_store=store)
    db_session.commit()
    first_theme_id = db_session.scalar(select(Theme.id).where(Theme.pipeline_run_id == run_id))

    label_themes_for_run(db_session, settings, run_id, mock=True, vector_store=store)
    db_session.commit()
    second_theme_id = db_session.scalar(select(Theme.id).where(Theme.pipeline_run_id == run_id))

    assert first_theme_id != second_theme_id


def test_attach_theme_evidence_selects_quotes_and_report(db_session, settings, tmp_path):
    run_id = uuid.uuid4()
    store = MockVectorStore()
    client = MockEmbeddingsClient(dimension=32)
    settings = settings.model_copy(update={"ANALYSIS_EXPORT_DIR": str(tmp_path)})

    items = [
        _add_item(db_session, text="Stale playlists", source="play_store"),
        _add_item(db_session, text="Same artists again", source="social"),
        _add_item(db_session, text="Need new music", source="app_store"),
    ]
    for item in items:
        _add_analysis(db_session, item, run_id, 0.25)
    _assign_clusters(db_session, run_id, [(item, 0) for item in items])
    embed_feedback_items(
        db_session,
        settings,
        run_id,
        mock=True,
        vector_store=store,
        embeddings_client=client,
    )
    label_themes_for_run(db_session, settings, run_id, mock=True, vector_store=store)
    db_session.commit()

    stats = attach_theme_evidence(
        db_session,
        settings,
        run_id,
        mock=True,
        vector_store=store,
    )
    db_session.commit()

    theme = db_session.scalar(select(Theme).where(Theme.pipeline_run_id == run_id))
    assert theme is not None
    assert len(theme.representative_quote_ids) >= 1
    member_ids = {str(item.id) for item in items}
    assert all(quote_id in member_ids for quote_id in theme.representative_quote_ids)
    assert theme.source_breakdown == {"app_store": 1, "play_store": 1, "social": 1}
    assert stats.report_path is not None
    assert (Path(stats.report_path)).exists()
