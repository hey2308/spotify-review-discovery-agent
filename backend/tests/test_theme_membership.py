import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from core.bot_filter import is_bot_post
from db.base import Base
from db.models import ClusterAssignment, FeedbackItem, FeedbackTheme, Theme
from pipeline.theme_membership import sync_feedback_themes_from_clusters

RUN_ID = uuid.UUID("669ca52cc5eb4c6f852a9a278f2679cc")
THEME_A = uuid.UUID("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
THEME_B = uuid.UUID("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _add_item(session: Session, text: str) -> FeedbackItem:
    item = FeedbackItem(
        source="social",
        external_id=str(uuid.uuid4()),
        text=text,
        item_date=datetime(2026, 5, 1, tzinfo=UTC),
        content_hash=uuid.uuid4().hex,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def test_sync_feedback_themes_from_clusters_links_by_cluster_id(db_session: Session):
    theme_a = Theme(
        id=THEME_A,
        name="Theme A",
        cluster_id=0,
        pipeline_run_id=RUN_ID,
    )
    theme_b = Theme(
        id=THEME_B,
        name="Theme B",
        cluster_id=1,
        pipeline_run_id=RUN_ID,
    )
    db_session.add_all([theme_a, theme_b])

    item_a = _add_item(db_session, "Discover Weekly feels stale and repetitive.")
    item_b = _add_item(db_session, "Shuffle keeps replaying the same songs.")
    bot = _add_item(
        db_session,
        "#NowPlaying on #BBC6Music Automagic show playlist on Spotify Song on #Spotify:",
    )

    db_session.add_all(
        [
            ClusterAssignment(feedback_item_id=item_a.id, pipeline_run_id=RUN_ID, cluster_id=0),
            ClusterAssignment(feedback_item_id=item_b.id, pipeline_run_id=RUN_ID, cluster_id=1),
            ClusterAssignment(feedback_item_id=bot.id, pipeline_run_id=RUN_ID, cluster_id=0),
            FeedbackTheme(feedback_item_id=item_b.id, theme_id=THEME_A),
        ]
    )
    db_session.commit()

    stats = sync_feedback_themes_from_clusters(db_session, RUN_ID)
    db_session.commit()

    links = list(db_session.scalars(select(FeedbackTheme)).all())
    assert stats["linked"] == 2
    assert stats["skipped_bots"] == 1
    assert len(links) == 2
    assert {link.feedback_item_id for link in links} == {item_a.id, item_b.id}
    assert db_session.get(FeedbackTheme, (item_a.id, THEME_A)) is not None
    assert db_session.get(FeedbackTheme, (item_b.id, THEME_B)) is not None
    assert is_bot_post(bot.text)
