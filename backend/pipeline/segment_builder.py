import logging
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from core.config import Settings
from core.llm import LLMClient, get_llm_client
from core.prompts.segments import (
    SEGMENT_ROLLUP_REPAIR_SUFFIX,
    SEGMENT_ROLLUP_SYSTEM_PROMPT,
    build_segment_rollup_prompt,
)
from core.rate_limit import RateLimiter
from db.models import Analysis, FeedbackItem, Segment
from pipeline.retrieval import truncate_text
from pipeline.schemas import SegmentRollupResponse

logger = logging.getLogger(__name__)

SEGMENT_LABELS: dict[str, str] = {
    "power_user": "Power listeners",
    "casual_listener": "Casual listeners",
    "new_user": "New subscribers",
    "long_term_subscriber": "Long-term subscribers",
}

INTENT_FRUSTRATIONS: dict[str, str] = {
    "discover_new_music": "Recommendations fail to surface fresh music",
    "repeat_listening": "Autoplay and mixes keep replaying the same content",
    "explore_genre": "Brief genre exploration gets over-indexed",
    "mood_matching": "Mood shifts are not reflected in recommendations",
    "complaint": "Discovery features feel broken or hard to use",
}

BEHAVIOR_LABELS: dict[str, str] = {
    "repeats_same_content": "Relies on comfort playlists and repeat listening",
    "discovery_focused": "Actively searches for new artists and genres",
    "autoplay": "Lets autoplay drive session flow",
    "feed_browsing": "Browses the home feed for suggestions",
    "external_discovery": "Uses blogs, friends, or other apps to find music",
    "shuffle": "Uses shuffle and radio for passive discovery",
    "release_radar": "Checks Release Radar and algorithmic playlists",
    "home_screen": "Starts discovery from the home screen",
    "navigation": "Looks for discovery features in the UI",
    "eclectic_taste": "Listens across many genres and eras",
    "daily_mix": "Uses Daily Mix for familiar listening",
    "local_discovery": "Seeks local or niche artist discovery",
}


@dataclass(slots=True)
class SegmentStats:
    segments_written: int = 0
    llm_calls: int = 0
    details: dict[str, object] = field(default_factory=dict)


def _behavior_values(raw: dict[str, object] | None) -> list[str]:
    if not raw:
        return []
    signals = raw.get("signals")
    if isinstance(signals, list):
        return [str(signal) for signal in signals if signal]
    return []


def _humanize(value: str) -> str:
    return value.replace("_", " ").strip()


def _aggregate_segment_data(
    session: Session,
    run_id: uuid.UUID,
    *,
    min_items: int,
) -> list[dict[str, object]]:
    rows = session.execute(
        select(
            Analysis.segment_hint,
            Analysis.intent,
            Analysis.behavior_signals,
            Analysis.sentiment_score,
            FeedbackItem.text,
        )
        .join(FeedbackItem, FeedbackItem.id == Analysis.feedback_item_id)
        .where(
            Analysis.pipeline_run_id == run_id,
            Analysis.segment_hint.is_not(None),
        )
    ).all()

    grouped: dict[str, list[tuple[str | None, dict[str, object] | None, float | None, str]]] = (
        defaultdict(list)
    )
    for segment_hint, intent, behavior_signals, sentiment_score, text in rows:
        grouped[str(segment_hint)].append((intent, behavior_signals, sentiment_score, text))

    payloads: list[dict[str, object]] = []
    for segment_key in sorted(grouped):
        entries = grouped[segment_key]
        if len(entries) < min_items:
            continue

        intents = Counter(intent for intent, _, _, _ in entries if intent)
        behaviors = Counter(
            signal
            for _, behavior_signals, _, _ in entries
            for signal in _behavior_values(behavior_signals)
        )
        sentiments = [score for _, _, score, _ in entries if score is not None]
        mean_sentiment = sum(sentiments) / len(sentiments) if sentiments else None
        sample_quotes = [
            truncate_text(text, 220)
            for _, _, _, text in sorted(entries, key=lambda row: len(row[3]), reverse=True)[:3]
        ]

        payloads.append(
            {
                "segment_key": segment_key,
                "label_hint": SEGMENT_LABELS.get(segment_key, _humanize(segment_key).title()),
                "item_count": len(entries),
                "top_intents": [label for label, _ in intents.most_common(3)],
                "top_behaviors": [label for label, _ in behaviors.most_common(3)],
                "mean_sentiment": round(mean_sentiment, 3) if mean_sentiment is not None else None,
                "sample_quotes": sample_quotes,
                "top_intent_key": intents.most_common(1)[0][0] if intents else None,
                "top_behavior_key": behaviors.most_common(1)[0][0] if behaviors else None,
            }
        )
    return payloads


def _heuristic_rollups(payloads: list[dict[str, object]]) -> SegmentRollupResponse:
    segments = []
    for payload in payloads:
        intent_key = payload.get("top_intent_key")
        behavior_key = payload.get("top_behavior_key")
        segments.append(
            {
                "segment_key": payload["segment_key"],
                "label": payload["label_hint"],
                "top_frustration": INTENT_FRUSTRATIONS.get(
                    str(intent_key),
                    "Discovery recommendations feel repetitive or hard to trust",
                ),
                "top_unmet_need": "Clearer ways to explore new music without getting stuck in a loop",
                "top_behavior": BEHAVIOR_LABELS.get(
                    str(behavior_key),
                    "Uses algorithmic playlists for everyday listening",
                ),
            }
        )
    return SegmentRollupResponse.model_validate({"segments": segments})


def _rollup_with_llm(
    llm: LLMClient,
    payloads: list[dict[str, object]],
    settings: Settings,
    rate_limiter: RateLimiter,
) -> tuple[SegmentRollupResponse, int]:
    prompt = build_segment_rollup_prompt(payloads)
    llm_calls = 0

    for attempt in range(settings.groq_max_retries + 1):
        rate_limiter.wait()
        llm_calls += 1
        raw = llm.complete_json(
            prompt,
            system=SEGMENT_ROLLUP_SYSTEM_PROMPT,
            model=settings.groq_model_large,
        )
        try:
            return SegmentRollupResponse.model_validate(raw), llm_calls
        except ValidationError as exc:
            if attempt >= settings.groq_max_retries:
                raise
            prompt = prompt + SEGMENT_ROLLUP_REPAIR_SUFFIX.format(error=exc)

    raise RuntimeError("segment rollup retries exhausted")


def _clear_run_segments(session: Session, run_id: uuid.UUID) -> None:
    session.execute(delete(Segment).where(Segment.pipeline_run_id == run_id))
    session.flush()


def build_segments_for_run(
    session: Session,
    settings: Settings,
    run_id: uuid.UUID,
    *,
    dry_run: bool = False,
    mock: bool = False,
    llm: LLMClient | None = None,
) -> SegmentStats:
    stats = SegmentStats()
    payloads = _aggregate_segment_data(session, run_id, min_items=settings.segment_min_items)

    if dry_run:
        stats.segments_written = len(payloads)
        stats.details = {"mode": "dry_run", "segment_keys": [p["segment_key"] for p in payloads]}
        return stats

    if not payloads:
        logger.warning("No segment groups met minimum item threshold for run %s", run_id)
        stats.details = {"mode": "empty", "min_items": settings.segment_min_items}
        return stats

    use_heuristic = mock or settings.mock_mode
    llm_client = None if use_heuristic else (llm or get_llm_client(settings))
    rate_limiter = RateLimiter(settings.groq_large_rpm)

    if use_heuristic:
        rollup = _heuristic_rollups(payloads)
        llm_calls = 0
    else:
        rollup, llm_calls = _rollup_with_llm(
            llm_client,
            payloads,
            settings,
            rate_limiter,
        )

    _clear_run_segments(session, run_id)

    rollup_by_key = {item.segment_key: item for item in rollup.segments}
    for payload in payloads:
        segment_key = str(payload["segment_key"])
        item = rollup_by_key.get(segment_key)
        if item is None:
            item = _heuristic_rollups([payload]).segments[0]

        session.add(
            Segment(
                label=item.label,
                top_frustration=item.top_frustration,
                top_unmet_need=item.top_unmet_need,
                top_behavior=item.top_behavior,
                pipeline_run_id=run_id,
            )
        )
        stats.segments_written += 1

    session.flush()
    stats.llm_calls = llm_calls
    stats.details = {
        "mode": "heuristic" if use_heuristic else "groq",
        "segment_keys": [str(payload["segment_key"]) for payload in payloads],
    }
    return stats
