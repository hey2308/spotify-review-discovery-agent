import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from core.config import Settings
from core.embeddings import MockEmbeddingsClient
from core.vectorstore import MockVectorStore
from db.base import Base
from db.models import Analysis, Answer, FeedbackItem, Segment, UnmetNeed
from pipeline.embedder import embed_feedback_items
from pipeline.qa_synthesizer import synthesize_qa_for_run
from pipeline.segment_builder import build_segments_for_run
from pipeline.unmet_needs_extractor import extract_unmet_needs_for_run


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
        QA_MIN_EVIDENCE=3,
        QA_RETRIEVAL_COUNT=10,
        QA_SYNTHESIS_QUOTE_COUNT=6,
        SEGMENT_MIN_ITEMS=2,
        UNMET_NEEDS_MAX_ITEMS=4,
        UNMET_NEEDS_RETRIEVAL_COUNT=10,
        EMBEDDING_BATCH_SIZE=16,
    )


def _add_item(
    session: Session,
    *,
    text: str,
    run_id: uuid.UUID,
    source: str = "play_store",
    rating: int = 2,
    segment_hint: str = "casual_listener",
    sentiment_score: float = 0.25,
    intent: str = "discover_new_music",
    behaviors: list[str] | None = None,
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
    session.flush()
    session.add(
        Analysis(
            feedback_item_id=item.id,
            sentiment_label="negative" if sentiment_score < 0.5 else "positive",
            sentiment_score=sentiment_score,
            intent=intent,
            behavior_signals={"signals": behaviors or ["discovery_focused"]},
            segment_hint=segment_hint,
            pipeline_run_id=run_id,
        )
    )
    session.commit()
    session.refresh(item)
    return item


class FakeQALLM:
    def complete_json(self, prompt, *, model=None, system=None, max_tokens=8192):
        del model, system, max_tokens
        if "Segment key" in prompt:
            return {
                "segments": [
                    {
                        "segment_key": "casual_listener",
                        "label": "Casual listeners",
                        "top_frustration": "Autoplay feels repetitive",
                        "top_unmet_need": "Easier surprise picks",
                        "top_behavior": "Uses Daily Mix for comfort",
                    },
                    {
                        "segment_key": "power_user",
                        "label": "Power listeners",
                        "top_frustration": "Recommendations ignore eclectic taste",
                        "top_unmet_need": "Broader underground discovery",
                        "top_behavior": "Uses external blogs for new music",
                    },
                ]
            }
        if "Extract ranked unmet needs" in prompt:
            return {
                "needs": [
                    {
                        "description": "Fresher weekly recommendations",
                        "supporting_ids": _extract_ids(prompt)[:3],
                        "urgency_score": 0.82,
                    },
                    {
                        "description": "Explicit controls to reset taste",
                        "supporting_ids": _extract_ids(prompt)[1:4],
                        "urgency_score": 0.71,
                    },
                ]
            }
        return {
            "answer_text": (
                "Users struggle because recommendations repeat and discovery "
                "features do not reflect their current mood or taste."
            ),
            "evidence_ids": _extract_ids(prompt)[:3],
            "confidence": "high",
        }


def _extract_ids(prompt: str) -> list[str]:
    ids: list[str] = []
    for line in prompt.splitlines():
        if line.strip().startswith("item_id:"):
            ids.append(line.split(":", 1)[1].strip())
    return ids


def test_synthesize_qa_writes_six_grounded_answers(db_session, settings):
    run_id = uuid.uuid4()
    texts = [
        "I want to discover new indie artists but Spotify keeps replaying the same songs.",
        "Discover Weekly feels stale and never surprises me with fresh music anymore.",
        "I wish there was a way to reset my taste profile and explore jazz lightly.",
        "The algorithm knows me too well and stopped trying to recommend new genres.",
        "I need better mood-based discovery when I want energetic music after a breakup.",
        "Release Radar keeps suggesting artists I stopped caring about years ago.",
        "I want underground artists but my home feed is all mainstream pop repeats.",
        "Shuffle and radio play the same twenty songs every week without variety.",
    ]
    items = [_add_item(db_session, text=text, run_id=run_id) for text in texts]
    db_session.commit()

    store = MockVectorStore()
    client = MockEmbeddingsClient(dimension=32)
    embed_feedback_items(
        db_session,
        settings,
        run_id,
        mock=True,
        vector_store=store,
        embeddings_client=client,
    )

    stats = synthesize_qa_for_run(
        db_session,
        settings,
        run_id,
        mock=True,
        llm=FakeQALLM(),
    )

    answers = list(db_session.scalars(select(Answer).where(Answer.pipeline_run_id == run_id)).all())
    assert stats.answers_written == 6
    assert len(answers) == 6
    for answer in answers:
        assert answer.answer_text
        assert len(answer.evidence_ids) >= settings.qa_min_evidence
        assert answer.source_breakdown
        for evidence_id in answer.evidence_ids:
            assert db_session.get(FeedbackItem, uuid.UUID(evidence_id)) is not None


def test_build_segments_writes_rollups(db_session, settings):
    run_id = uuid.uuid4()
    for segment_hint, text in [
        ("casual_listener", "Autoplay keeps replaying the same songs and I want surprise picks."),
        ("casual_listener", "Daily Mix is comfort listening but discovery feels repetitive."),
        ("power_user", "I use blogs to find underground artists because Spotify ignores eclectic taste."),
        ("power_user", "Recommendations never surface niche genres I actually want to explore."),
    ]:
        item = _add_item(db_session, text=text, segment_hint=segment_hint, run_id=run_id)
    db_session.commit()

    stats = build_segments_for_run(
        db_session,
        settings,
        run_id,
        mock=True,
        llm=FakeQALLM(),
    )

    segments = list(
        db_session.scalars(select(Segment).where(Segment.pipeline_run_id == run_id)).all()
    )
    assert stats.segments_written == 2
    assert len(segments) == 2
    for segment in segments:
        assert segment.label
        assert segment.top_frustration
        assert segment.top_unmet_need
        assert segment.top_behavior


def test_extract_unmet_needs_ranks_with_attribution(db_session, settings):
    run_id = uuid.uuid4()
    texts = [
        "I wish Spotify would reset my recommendations and help me explore jazz lightly.",
        "I need fresher Discover Weekly picks instead of the same artists every week.",
        "Missing controls to tell the app I want energetic music now, not sad indie.",
        "Better genre diversity would help me discover underground artists across sources.",
    ]
    for index, text in enumerate(texts):
        item = _add_item(
            db_session,
            text=text,
            source=["play_store", "social", "reddit", "app_store"][index % 4],
            run_id=run_id,
        )
    db_session.commit()

    store = MockVectorStore()
    client = MockEmbeddingsClient(dimension=32)
    embed_feedback_items(
        db_session,
        settings,
        run_id,
        mock=True,
        vector_store=store,
        embeddings_client=client,
    )

    stats = extract_unmet_needs_for_run(
        db_session,
        settings,
        run_id,
        mock=True,
        llm=FakeQALLM(),
    )

    needs = list(
        db_session.scalars(
            select(UnmetNeed)
            .where(UnmetNeed.pipeline_run_id == run_id)
            .order_by(UnmetNeed.frequency.desc())
        ).all()
    )
    assert stats.needs_written >= 2
    assert needs[0].frequency >= needs[-1].frequency or needs[0].urgency_score >= needs[-1].urgency_score
    for need in needs:
        assert need.description
        assert need.urgency_score is not None
        assert need.source_attribution
