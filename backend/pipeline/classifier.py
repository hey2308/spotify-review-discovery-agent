import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import Settings
from core.llm import LLMClient, get_llm_client
from core.prompts.classification import (
    CLASSIFICATION_REPAIR_SUFFIX,
    CLASSIFICATION_SYSTEM_PROMPT,
    build_classification_prompt,
)
from core.rate_limit import RateLimiter
from db.models import Analysis, FeedbackItem
from pipeline.schemas import BatchClassificationResponse, ItemClassification

logger = logging.getLogger(__name__)

NEGATIVE_KEYWORDS = re.compile(
    r"\b(broken|stale|repeat|repetitive|bad|worst|hate|never find|same artist|"
    r"disappoint|frustrat|useless|garbage|terrible|awful|bug|crash)\b",
    re.IGNORECASE,
)
POSITIVE_KEYWORDS = re.compile(
    r"\b(love|great|best|amazing|excellent|perfect|awesome|recommend)\b",
    re.IGNORECASE,
)
DISCOVERY_KEYWORDS = re.compile(
    r"\b(discover|recommend|playlist|algorithm|new music|find music)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class ClassifyStats:
    total_items: int = 0
    classified: int = 0
    cached: int = 0
    failed: int = 0
    llm_calls: int = 0
    details: dict[str, object] = field(default_factory=dict)


def _truncate_text(text: str, max_chars: int) -> str:
    cleaned = text.strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3] + "..."


def _item_payload(item: FeedbackItem, max_chars: int) -> dict[str, object]:
    return {
        "id": str(item.id),
        "source": item.source,
        "rating": item.rating,
        "title": item.title,
        "text": _truncate_text(item.text, max_chars),
    }


def _heuristic_classification(item: FeedbackItem) -> ItemClassification:
    text = item.text
    rating = item.rating

    if rating is not None:
        if rating <= 2:
            label = "negative"
            score = 0.2
        elif rating >= 4:
            label = "positive"
            score = 0.8
        else:
            label = "neutral"
            score = 0.5
    elif NEGATIVE_KEYWORDS.search(text):
        label = "negative"
        score = 0.25
    elif POSITIVE_KEYWORDS.search(text):
        label = "positive"
        score = 0.75
    else:
        label = "neutral"
        score = 0.5

    behavior_signals: list[str] = []
    if re.search(r"\b(repeat|same|stale)\b", text, re.IGNORECASE):
        behavior_signals.append("repeats_same_content")
    if DISCOVERY_KEYWORDS.search(text):
        behavior_signals.append("discovery_focused")

    intent = "discover_new_music" if DISCOVERY_KEYWORDS.search(text) else "general_listening"
    segment_hint = "casual_listener"
    if re.search(r"\b(premium|year|years|subscriber)\b", text, re.IGNORECASE):
        segment_hint = "long_term_subscriber"

    return ItemClassification(
        item_id=str(item.id),
        sentiment_label=label,
        sentiment_score=score,
        intent=intent,
        behavior_signals=behavior_signals,
        segment_hint=segment_hint,
    )


def _parse_batch_response(
    raw: dict[str, object],
    expected_ids: set[str],
) -> list[ItemClassification]:
    payload = BatchClassificationResponse.model_validate(raw)
    seen: set[str] = set()
    valid: list[ItemClassification] = []

    for classification in payload.classifications:
        if classification.item_id not in expected_ids:
            continue
        if classification.item_id in seen:
            continue
        seen.add(classification.item_id)
        valid.append(classification)

    missing = expected_ids - seen
    if missing:
        raise ValueError(f"missing classifications for item_ids: {sorted(missing)}")

    return valid


def _classify_batch_with_llm(
    llm: LLMClient,
    items: list[FeedbackItem],
    settings: Settings,
    rate_limiter: RateLimiter,
) -> tuple[list[ItemClassification], int]:
    payload = [_item_payload(item, settings.classification_max_text_chars) for item in items]
    expected_ids = {str(item.id) for item in items}
    prompt = build_classification_prompt(payload)
    llm_calls = 0

    for attempt in range(settings.groq_max_retries + 1):
        rate_limiter.wait()
        llm_calls += 1
        raw = llm.complete_json(
            prompt,
            system=CLASSIFICATION_SYSTEM_PROMPT,
            model=settings.groq_model_small,
            max_tokens=max(2048, len(items) * 180),
        )
        try:
            return _parse_batch_response(raw, expected_ids), llm_calls
        except (ValidationError, ValueError) as exc:
            if attempt >= settings.groq_max_retries:
                raise
            prompt = prompt + CLASSIFICATION_REPAIR_SUFFIX.format(error=exc)

    raise RuntimeError("classification retries exhausted")


def _upsert_analysis(
    session: Session,
    item: FeedbackItem,
    classification: ItemClassification,
    run_id: uuid.UUID,
) -> None:
    existing = session.scalar(
        select(Analysis).where(Analysis.feedback_item_id == item.id)
    )
    if existing:
        existing.sentiment_label = classification.sentiment_label
        existing.sentiment_score = classification.sentiment_score
        existing.intent = classification.intent
        existing.behavior_signals = {"signals": classification.behavior_signals}
        existing.segment_hint = classification.segment_hint
        existing.pipeline_run_id = run_id
        return

    session.add(
        Analysis(
            feedback_item_id=item.id,
            sentiment_label=classification.sentiment_label,
            sentiment_score=classification.sentiment_score,
            intent=classification.intent,
            behavior_signals={"signals": classification.behavior_signals},
            segment_hint=classification.segment_hint,
            pipeline_run_id=run_id,
        )
    )


def _load_unclassified_items(session: Session) -> list[FeedbackItem]:
    return list(
        session.scalars(
            select(FeedbackItem)
            .outerjoin(Analysis, FeedbackItem.id == Analysis.feedback_item_id)
            .where(Analysis.id.is_(None))
            .order_by(FeedbackItem.item_date.desc())
        ).all()
    )


def classify_feedback_items(
    session: Session,
    settings: Settings,
    run_id: uuid.UUID,
    *,
    dry_run: bool = False,
    mock: bool = False,
    llm: LLMClient | None = None,
) -> ClassifyStats:
    stats = ClassifyStats()
    all_items = list(session.scalars(select(FeedbackItem)).all())
    stats.total_items = len(all_items)

    if dry_run:
        stats.classified = stats.total_items
        stats.details = {"mode": "dry_run"}
        return stats

    unclassified = _load_unclassified_items(session)
    stats.cached = stats.total_items - len(unclassified)

    if not unclassified:
        stats.details = {"mode": "cache_hit"}
        return stats

    use_heuristic = mock or settings.mock_mode
    llm_client = None if use_heuristic else (llm or get_llm_client(settings))
    rate_limiter = RateLimiter(settings.groq_small_rpm)
    llm_calls = 0

    batch_size = settings.classification_batch_size
    for offset in range(0, len(unclassified), batch_size):
        batch = unclassified[offset : offset + batch_size]
        try:
            if use_heuristic:
                classifications = [_heuristic_classification(item) for item in batch]
            else:
                classifications, batch_calls = _classify_batch_with_llm(
                    llm_client,
                    batch,
                    settings,
                    rate_limiter,
                )
                llm_calls += batch_calls

            for item, classification in zip(batch, classifications, strict=True):
                _upsert_analysis(session, item, classification, run_id)
                stats.classified += 1

            session.commit()
        except Exception:
            logger.exception("Failed to classify batch starting at offset %s", offset)
            stats.failed += len(batch)
            session.rollback()

    stats.llm_calls = llm_calls
    stats.details = {
        "mode": "heuristic" if use_heuristic else "groq",
        "batch_size": batch_size,
        "model": settings.groq_model_small if not use_heuristic else "heuristic",
    }
    return stats


def load_sentiment_golden(path: Path) -> list[dict[str, object]]:
    return json.loads(path.read_text(encoding="utf-8"))


def sentiment_macro_f1(
  predictions: list[str],
  labels: list[str],
) -> float:
    classes = sorted({"positive", "neutral", "negative"})
    f1_scores: list[float] = []

    for label in classes:
        pairs = list(zip(predictions, labels, strict=True))
        tp = sum(1 for pred, gold in pairs if pred == label and gold == label)
        fp = sum(1 for pred, gold in pairs if pred == label and gold != label)
        fn = sum(1 for pred, gold in pairs if pred != label and gold == label)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        f1_scores.append(f1)

    return sum(f1_scores) / len(f1_scores)


def evaluate_sentiment_golden(path: Path) -> float:
    examples = load_sentiment_golden(path)
    predictions: list[str] = []
    labels: list[str] = []

    for example in examples:
        item = FeedbackItem(
            id=uuid.uuid4(),
            source=str(example.get("source", "app_store")),
            text=str(example["text"]),
            rating=example.get("rating"),
            item_date=example.get("item_date"),
            content_hash=uuid.uuid4().hex,
        )
        if item.item_date is None:
            from datetime import UTC, datetime

            item.item_date = datetime.now(UTC)
        classification = _heuristic_classification(item)
        predictions.append(classification.sentiment_label)
        labels.append(str(example["sentiment_label"]))

    return sentiment_macro_f1(predictions, labels)
