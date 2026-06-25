from datetime import UTC, datetime

from ingestion.filters import (
    english_word_count,
    review_rejection_reason,
    strip_emojis,
)
from ingestion.normalize import prepare_item
from ingestion.types import NormalizedItem


def test_strip_emojis_removes_emoji_characters():
    text = "Great app 😍 love the playlists 🔥"
    assert strip_emojis(text) == "Great app love the playlists"


def test_english_word_count_ignores_emoji_and_punctuation():
    assert english_word_count("One two three four five six.") == 6
    assert english_word_count("One two three four five") == 5


def test_review_rejection_reason_too_short():
    reason = review_rejection_reason(
        "Too short review here",
        min_words=6,
        english_only=True,
    )
    assert reason == "too_short"


def test_review_rejection_reason_non_english():
    reason = review_rejection_reason(
        "Esta aplicación de música es muy mala para descubrir canciones nuevas",
        min_words=6,
        english_only=True,
    )
    assert reason == "non_english"


def test_review_rejection_reason_accepts_english_review():
    reason = review_rejection_reason(
        "Spotify discovery feels stale and repetitive every single week",
        min_words=6,
        english_only=True,
    )
    assert reason is None


def test_prepare_item_strips_emojis_before_storage():
    item = NormalizedItem(
        source="play_store",
        external_id="1",
        title=None,
        text="I love discovery 😀 but repeats are annoying every week",
        rating=3,
        item_date=datetime(2026, 5, 1, tzinfo=UTC),
        raw_payload={},
    )
    prepared = prepare_item(item)
    assert "😀" not in prepared.text
    assert english_word_count(prepared.text) >= 6
