import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from core.config import Settings
from db.base import Base
from db.models import Analysis, FeedbackItem
from pipeline.classifier import (
    _heuristic_classification,
    _parse_batch_response,
    classify_feedback_items,
    evaluate_sentiment_golden,
    sentiment_macro_f1,
)
from pipeline.schemas import ItemClassification

GOLDEN_PATH = Path(__file__).resolve().parents[2] / "evals" / "golden" / "sentiment.json"


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
        CLASSIFICATION_BATCH_SIZE=2,
        GROQ_SMALL_RPM=60,
    )


def _add_item(session: Session, *, text: str, rating: int | None = 2) -> FeedbackItem:
    item = FeedbackItem(
        source="play_store",
        external_id=str(uuid.uuid4()),
        text=text,
        rating=rating,
        item_date=datetime(2026, 5, 1, tzinfo=UTC),
        content_hash=uuid.uuid4().hex,
    )
    session.add(item)
    session.commit()
    return item


class FakeLLM:
    def __init__(self, responses: list[dict] | None = None) -> None:
        self._responses = responses or []
        self.calls = 0

    def complete_json(self, prompt, *, model=None, system=None, max_tokens=8192):
        del max_tokens
        self.calls += 1
        if self._responses:
            response = self._responses[min(self.calls - 1, len(self._responses) - 1)]
            return response

        item_ids = re.findall(
            r"item_id: ([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
            prompt,
            flags=re.IGNORECASE,
        )
        return {
            "classifications": [
                {
                    "item_id": item_id,
                    "sentiment_label": "neutral",
                    "sentiment_score": 0.5,
                    "intent": "general_listening",
                    "behavior_signals": [],
                    "segment_hint": "casual_listener",
                }
                for item_id in item_ids
            ]
        }


def test_parse_batch_response_requires_all_item_ids():
    raw = {
        "classifications": [
            {
                "item_id": "abc",
                "sentiment_label": "negative",
                "sentiment_score": 0.2,
                "intent": "discover_new_music",
                "behavior_signals": ["repeats_same_content"],
                "segment_hint": "casual_listener",
            }
        ]
    }
    with pytest.raises(ValueError, match="missing classifications"):
        _parse_batch_response(raw, {"abc", "def"})


def test_parse_batch_response_accepts_valid_payload():
    raw = {
        "classifications": [
            {
                "item_id": "abc",
                "sentiment_label": "negative",
                "sentiment_score": 0.2,
                "intent": "discover_new_music",
                "behavior_signals": ["repeats_same_content"],
                "segment_hint": "casual_listener",
            }
        ]
    }
    result = _parse_batch_response(raw, {"abc"})
    assert len(result) == 1
    assert result[0].sentiment_label == "negative"


def test_classify_feedback_items_writes_analyses(db_session, settings):
    run_id = uuid.uuid4()
    _add_item(db_session, text="Spotify discovery is broken and repetitive")
    _add_item(db_session, text="Love this app, amazing playlists")

    stats = classify_feedback_items(
        db_session,
        settings,
        run_id,
        mock=True,
    )

    assert stats.classified == 2
    assert stats.cached == 0
    assert db_session.scalar(select(func.count()).select_from(Analysis)) == 2


def test_classify_feedback_items_skips_cached_items(db_session, settings):
    run_id = uuid.uuid4()
    _add_item(db_session, text="Same stale recommendations every day")

    first = classify_feedback_items(db_session, settings, run_id, mock=True)
    second = classify_feedback_items(db_session, settings, run_id, mock=True)

    assert first.classified == 1
    assert second.classified == 0
    assert second.cached == 1


def test_classify_feedback_items_uses_llm_batches(db_session, settings):
    run_id = uuid.uuid4()
    for index in range(3):
        _add_item(db_session, text=f"Review number {index}")
    llm = FakeLLM()

    settings_with_key = Settings(
        _env_file=None,
        DATABASE_URL="sqlite+pysqlite:///:memory:",
        GROQ_API_KEY="test-key",
        CLASSIFICATION_BATCH_SIZE=2,
        GROQ_SMALL_RPM=120,
        GROQ_MAX_RETRIES=0,
    )
    stats = classify_feedback_items(
        db_session,
        settings_with_key,
        run_id,
        llm=llm,
    )

    assert stats.classified == 3
    assert llm.calls == 2
    assert db_session.scalar(select(func.count()).select_from(Analysis)) == 3


def test_classify_dry_run_does_not_write(db_session, settings):
    run_id = uuid.uuid4()
    _add_item(db_session, text="Discovery is stale")

    stats = classify_feedback_items(db_session, settings, run_id, dry_run=True)

    assert stats.classified == 1
    assert db_session.scalar(select(func.count()).select_from(Analysis)) == 0


def test_sentiment_macro_f1_perfect_score():
    labels = ["positive", "negative", "neutral"]
    assert sentiment_macro_f1(labels, labels) == 1.0


def test_golden_sentiment_meets_threshold():
    score = evaluate_sentiment_golden(GOLDEN_PATH)
    assert score >= 0.8


def test_heuristic_classification_schema():
    item = FeedbackItem(
        id=uuid.uuid4(),
        source="play_store",
        text="Spotify recommendations are terrible and repetitive",
        rating=1,
        item_date=datetime(2026, 5, 1, tzinfo=UTC),
        content_hash="hash",
    )
    result = _heuristic_classification(item)
    ItemClassification.model_validate(result.model_dump())
    assert result.sentiment_label == "negative"
