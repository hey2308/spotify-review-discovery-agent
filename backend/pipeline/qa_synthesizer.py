import logging
import re
import uuid
from collections import Counter
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from core.config import Settings
from core.llm import LLMClient, get_llm_client
from core.prompts.qa_synthesis import (
    QA_SYNTHESIS_REPAIR_SUFFIX,
    QA_SYNTHESIS_SYSTEM_PROMPT,
    build_qa_synthesis_prompt,
)
from core.questions import QUESTION_ORDER, QUESTION_RETRIEVAL_QUERIES, QUESTION_TEXT
from core.rate_limit import RateLimiter
from db.models import Answer, FeedbackItem
from pipeline.retrieval import quote_payload, retrieve_feedback_items
from pipeline.schemas import QASynthesisResponse

logger = logging.getLogger(__name__)

WISH_PATTERN = re.compile(r"\b(wish|want|need|missing|should|reset|control)\b", re.I)


@dataclass(slots=True)
class QAStats:
    answers_written: int = 0
    llm_calls: int = 0
    low_confidence: int = 0
    details: dict[str, object] = field(default_factory=dict)


def _source_breakdown(items: list[FeedbackItem]) -> dict[str, int]:
    return dict(Counter(item.source for item in items))


def _filter_allowed_ids(evidence_ids: list[str], allowed_ids: set[str]) -> list[str]:
    valid: list[str] = []
    for item_id in evidence_ids:
        try:
            normalized = str(uuid.UUID(item_id))
        except ValueError:
            continue
        if normalized in allowed_ids:
            valid.append(normalized)
    return valid


def _confidence_from_evidence(
    valid_ids: list[str],
    *,
    min_evidence: int,
    requested: str,
) -> str:
    if len(valid_ids) < min_evidence:
        return "low"
    if requested == "low":
        return "low"
    if len(valid_ids) >= min_evidence + 1:
        return requested
    return "medium"


def _heuristic_answer(
    question_id: str,
    quotes: list[FeedbackItem],
    *,
    min_evidence: int,
) -> QASynthesisResponse:
    texts = " ".join(item.text.lower() for item in quotes[:8])
    evidence_ids = [str(item.id) for item in quotes[: max(min_evidence, 3)]]

    templates = {
        "Q1": (
            "Users struggle because recommendations feel repetitive and discovery "
            "surfaces do not surface enough fresh or relevant music."
        ),
        "Q2": (
            "The most common frustrations are stale playlists, over-personalized "
            "loops, and recommendations that ignore recent taste changes."
        ),
        "Q3": (
            "Listeners are trying to explore new genres, match moods, and balance "
            "comfort listening with intentional discovery."
        ),
        "Q4": (
            "Repeat listening is driven by autoplay, daily mixes, and algorithmic "
            "loops that resurface the same artists and tracks."
        ),
        "Q5": (
            "Power users and long-term subscribers report narrower discovery, while "
            "new and casual listeners struggle with buried discovery features."
        ),
        "Q6": (
            "Users consistently want fresher recommendations, clearer discovery "
            "controls, and better ways to reset or broaden their taste profile."
        ),
    }
    answer_text = templates[question_id]
    if "stale" in texts or "repeat" in texts:
        answer_text = (
            "Users describe discovery as stale and repetitive, with algorithms "
            "recycling the same artists instead of broadening their listening."
        )
    if WISH_PATTERN.search(texts):
        answer_text = (
            "Users repeatedly ask for more control over recommendations, fresher "
            "weekly picks, and features that help them explore without getting stuck."
        )

    confidence = "high" if len(evidence_ids) >= min_evidence else "low"
    return QASynthesisResponse(
        answer_text=answer_text,
        evidence_ids=evidence_ids,
        confidence=confidence,
    )


def _synthesize_with_llm(
    llm: LLMClient,
    *,
    question_id: str,
    question_text: str,
    quotes: list[FeedbackItem],
    settings: Settings,
    rate_limiter: RateLimiter,
) -> tuple[QASynthesisResponse, int]:
    allowed_ids = {str(item.id) for item in quotes}
    prompt = build_qa_synthesis_prompt(
        question_id=question_id,
        question_text=question_text,
        quotes=[quote_payload(item) for item in quotes],
    )
    llm_calls = 0

    for attempt in range(settings.groq_max_retries + 1):
        rate_limiter.wait()
        llm_calls += 1
        raw = llm.complete_json(
            prompt,
            system=QA_SYNTHESIS_SYSTEM_PROMPT,
            model=settings.groq_model_large,
        )
        try:
            response = QASynthesisResponse.model_validate(raw)
            valid_ids = _filter_allowed_ids(response.evidence_ids, allowed_ids)
            if not valid_ids:
                raise ValidationError.from_exception_data(
                    "QASynthesisResponse",
                    [{"type": "value_error", "loc": ("evidence_ids",), "msg": "no valid ids"}],
                )
            confidence = _confidence_from_evidence(
                valid_ids,
                min_evidence=settings.qa_min_evidence,
                requested=response.confidence,
            )
            return (
                QASynthesisResponse(
                    answer_text=response.answer_text,
                    evidence_ids=valid_ids[: settings.qa_synthesis_quote_count],
                    confidence=confidence,
                ),
                llm_calls,
            )
        except ValidationError as exc:
            if attempt >= settings.groq_max_retries:
                raise
            prompt = prompt + QA_SYNTHESIS_REPAIR_SUFFIX.format(error=exc)

    raise RuntimeError("Q&A synthesis retries exhausted")


def _clear_run_answers(session: Session, run_id: uuid.UUID) -> None:
    session.execute(delete(Answer).where(Answer.pipeline_run_id == run_id))
    session.flush()


def synthesize_qa_for_run(
    session: Session,
    settings: Settings,
    run_id: uuid.UUID,
    *,
    dry_run: bool = False,
    mock: bool = False,
    llm: LLMClient | None = None,
) -> QAStats:
    stats = QAStats()

    if dry_run:
        stats.answers_written = len(QUESTION_ORDER)
        stats.details = {"mode": "dry_run", "questions": list(QUESTION_ORDER)}
        return stats

    use_heuristic = mock or settings.mock_mode
    llm_client = None if use_heuristic else (llm or get_llm_client(settings))
    rate_limiter = RateLimiter(settings.groq_large_rpm)
    llm_calls = 0

    _clear_run_answers(session, run_id)

    for question_id in QUESTION_ORDER:
        query_text = QUESTION_RETRIEVAL_QUERIES[question_id]
        retrieved = retrieve_feedback_items(
            session,
            settings,
            query_text,
            n_results=settings.qa_retrieval_count,
            mock=mock,
        )
        quotes = retrieved[: settings.qa_synthesis_quote_count]
        if not quotes:
            logger.warning("No evidence retrieved for %s", question_id)
            continue

        if use_heuristic:
            synthesis = _heuristic_answer(
                question_id,
                quotes,
                min_evidence=settings.qa_min_evidence,
            )
        else:
            synthesis, question_calls = _synthesize_with_llm(
                llm_client,
                question_id=question_id,
                question_text=QUESTION_TEXT[question_id],
                quotes=quotes,
                settings=settings,
                rate_limiter=rate_limiter,
            )
            llm_calls += question_calls

        evidence_items = [
            item
            for item in quotes
            if str(item.id) in set(synthesis.evidence_ids)
        ]
        if len(evidence_items) < settings.qa_min_evidence:
            stats.low_confidence += 1

        session.add(
            Answer(
                question_id=question_id,
                answer_text=synthesis.answer_text,
                evidence_ids=synthesis.evidence_ids,
                confidence=synthesis.confidence,
                source_breakdown=_source_breakdown(evidence_items),
                pipeline_run_id=run_id,
            )
        )
        stats.answers_written += 1
        logger.info(
            "Synthesized %s with %s evidence ids (confidence=%s)",
            question_id,
            len(synthesis.evidence_ids),
            synthesis.confidence,
        )

    session.flush()
    stats.llm_calls = llm_calls
    stats.details = {
        "mode": "heuristic" if use_heuristic else "groq",
        "model": settings.groq_model_large if not use_heuristic else "heuristic",
        "min_evidence": settings.qa_min_evidence,
    }
    return stats
