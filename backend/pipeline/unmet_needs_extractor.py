import logging
import re
import uuid
from collections import Counter
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from core.config import Settings
from core.llm import LLMClient, get_llm_client
from core.prompts.unmet_needs import (
    UNMET_NEEDS_REPAIR_SUFFIX,
    UNMET_NEEDS_SYSTEM_PROMPT,
    build_unmet_needs_prompt,
)
from core.rate_limit import RateLimiter
from db.models import Analysis, FeedbackItem, UnmetNeed
from pipeline.retrieval import quote_payload, retrieve_feedback_items
from pipeline.schemas import UnmetNeedsExtractionResponse

logger = logging.getLogger(__name__)

NEED_QUERY = (
    "wish want need missing should feature workaround unmet reset taste "
    "discover weekly stale recommendations control explore genre"
)
WISH_PATTERN = re.compile(r"\b(wish|want|need|missing|should|reset|control|better)\b", re.I)

HEURISTIC_NEEDS: list[tuple[str, float]] = [
    ("Fresher weekly recommendations", 0.84),
    ("Better genre diversity in mixes", 0.76),
    ("Explicit controls to reset recommendation taste", 0.71),
    ("Easier exploration without over-indexing one genre", 0.68),
    ("Surprise picks that reflect current mood", 0.62),
    ("Broader underground and niche discovery", 0.58),
]


@dataclass(slots=True)
class UnmetNeedsStats:
    needs_written: int = 0
    llm_calls: int = 0
    details: dict[str, object] = field(default_factory=dict)


def _filter_allowed_ids(supporting_ids: list[str], allowed_ids: set[str]) -> list[str]:
    valid: list[str] = []
    for item_id in supporting_ids:
        try:
            normalized = str(uuid.UUID(item_id))
        except ValueError:
            continue
        if normalized in allowed_ids:
            valid.append(normalized)
    return valid


def _negative_discovery_items(session: Session, run_id: uuid.UUID, limit: int) -> list[FeedbackItem]:
    return list(
        session.scalars(
            select(FeedbackItem)
            .join(Analysis, Analysis.feedback_item_id == FeedbackItem.id)
            .where(
                Analysis.pipeline_run_id == run_id,
                Analysis.sentiment_score.is_not(None),
                Analysis.sentiment_score < 0.55,
            )
            .options(selectinload(FeedbackItem.analysis))
            .order_by(Analysis.sentiment_score.asc(), FeedbackItem.item_date.desc())
            .limit(limit)
        ).all()
    )


def _source_attribution(items: list[FeedbackItem]) -> dict[str, int]:
    return dict(Counter(item.source for item in items))


def _heuristic_needs(
    quotes: list[FeedbackItem],
    *,
    max_items: int,
) -> UnmetNeedsExtractionResponse:
    needs = []
    for index, (description, urgency) in enumerate(HEURISTIC_NEEDS[:max_items]):
        start = index * 2
        supporting = quotes[start : start + 3] or quotes[:3]
        needs.append(
            {
                "description": description,
                "supporting_ids": [str(item.id) for item in supporting],
                "urgency_score": urgency,
            }
        )
    return UnmetNeedsExtractionResponse.model_validate({"needs": needs})


def _extract_with_llm(
    llm: LLMClient,
    quotes: list[FeedbackItem],
    settings: Settings,
    rate_limiter: RateLimiter,
) -> tuple[UnmetNeedsExtractionResponse, int]:
    allowed_ids = {str(item.id) for item in quotes}
    prompt = build_unmet_needs_prompt([quote_payload(item) for item in quotes])
    llm_calls = 0

    for attempt in range(settings.groq_max_retries + 1):
        rate_limiter.wait()
        llm_calls += 1
        raw = llm.complete_json(
            prompt,
            system=UNMET_NEEDS_SYSTEM_PROMPT,
            model=settings.groq_model_large,
        )
        try:
            response = UnmetNeedsExtractionResponse.model_validate(raw)
            cleaned_needs = []
            for need in response.needs:
                valid_ids = _filter_allowed_ids(need.supporting_ids, allowed_ids)
                if not valid_ids:
                    continue
                cleaned_needs.append(
                    need.model_copy(
                        update={
                            "supporting_ids": valid_ids,
                        }
                    )
                )
            if not cleaned_needs:
                raise ValidationError.from_exception_data(
                    "UnmetNeedsExtractionResponse",
                    [{"type": "value_error", "loc": ("needs",), "msg": "no valid needs"}],
                )
            return UnmetNeedsExtractionResponse(needs=cleaned_needs), llm_calls
        except ValidationError as exc:
            if attempt >= settings.groq_max_retries:
                raise
            prompt = prompt + UNMET_NEEDS_REPAIR_SUFFIX.format(error=exc)

    raise RuntimeError("unmet needs extraction retries exhausted")


def _clear_run_needs(session: Session, run_id: uuid.UUID) -> None:
    session.execute(delete(UnmetNeed).where(UnmetNeed.pipeline_run_id == run_id))
    session.flush()


def extract_unmet_needs_for_run(
    session: Session,
    settings: Settings,
    run_id: uuid.UUID,
    *,
    dry_run: bool = False,
    mock: bool = False,
    llm: LLMClient | None = None,
) -> UnmetNeedsStats:
    stats = UnmetNeedsStats()

    if dry_run:
        stats.needs_written = settings.unmet_needs_max_items
        stats.details = {"mode": "dry_run"}
        return stats

    retrieved = retrieve_feedback_items(
        session,
        settings,
        NEED_QUERY,
        n_results=settings.unmet_needs_retrieval_count,
        mock=mock,
    )
    negative_items = _negative_discovery_items(
        session,
        run_id,
        limit=settings.unmet_needs_retrieval_count,
    )

    by_id = {str(item.id): item for item in retrieved}
    for item in negative_items:
        by_id.setdefault(str(item.id), item)

    wish_items = [item for item in by_id.values() if WISH_PATTERN.search(item.text)]
    quotes = (wish_items or list(by_id.values()))[: settings.unmet_needs_retrieval_count]
    if not quotes:
        logger.warning("No evidence available for unmet needs on run %s", run_id)
        stats.details = {"mode": "empty"}
        return stats

    use_heuristic = mock or settings.mock_mode
    llm_client = None if use_heuristic else (llm or get_llm_client(settings))
    rate_limiter = RateLimiter(settings.groq_large_rpm)

    if use_heuristic:
        extraction = _heuristic_needs(quotes, max_items=settings.unmet_needs_max_items)
        llm_calls = 0
    else:
        extraction, llm_calls = _extract_with_llm(
            llm_client,
            quotes,
            settings,
            rate_limiter,
        )

    _clear_run_needs(session, run_id)

    items_by_id = {str(item.id): item for item in quotes}
    ranked = sorted(
        extraction.needs,
        key=lambda need: (len(need.supporting_ids), need.urgency_score),
        reverse=True,
    )[: settings.unmet_needs_max_items]

    for need in ranked:
        supporting_items = [
            items_by_id[item_id]
            for item_id in need.supporting_ids
            if item_id in items_by_id
        ]
        session.add(
            UnmetNeed(
                description=need.description,
                frequency=len(supporting_items),
                urgency_score=need.urgency_score,
                source_attribution=_source_attribution(supporting_items),
                pipeline_run_id=run_id,
            )
        )
        stats.needs_written += 1

    session.flush()
    stats.llm_calls = llm_calls
    stats.details = {
        "mode": "heuristic" if use_heuristic else "groq",
        "evidence_count": len(quotes),
    }
    return stats
