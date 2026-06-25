import logging
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from core.config import Settings
from core.llm import LLMClient, get_llm_client
from core.prompts.theme_labeling import (
    THEME_LABEL_REPAIR_SUFFIX,
    THEME_LABEL_SYSTEM_PROMPT,
    build_theme_label_prompt,
)
from core.rate_limit import RateLimiter
from core.vectorstore import VectorStore, get_vector_store
from db.models import Analysis, ClusterAssignment, FeedbackItem, FeedbackTheme, Theme
from pipeline.embedding_utils import nearest_to_centroid
from pipeline.schemas import ThemeLabelResponse

logger = logging.getLogger(__name__)

STALE_KEYWORDS = re.compile(r"\b(stale|repeat|repetitive|same artist|same songs)\b", re.I)
DISCOVERY_KEYWORDS = re.compile(r"\b(discover|recommend|algorithm|new music|playlist)\b", re.I)
QUALITY_KEYWORDS = re.compile(r"\b(bug|crash|broken|slow|glitch|update)\b", re.I)


@dataclass(slots=True)
class ThemeLabelStats:
    total_clusters: int = 0
    themes_created: int = 0
    items_linked: int = 0
    llm_calls: int = 0
    details: dict[str, object] = field(default_factory=dict)


def _truncate_text(text: str, max_chars: int = 400) -> str:
    cleaned = text.strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3] + "..."


def _load_cluster_groups(
    session: Session,
    run_id: uuid.UUID,
) -> dict[int, list[FeedbackItem]]:
    rows = session.execute(
        select(FeedbackItem, ClusterAssignment.cluster_id)
        .join(ClusterAssignment, ClusterAssignment.feedback_item_id == FeedbackItem.id)
        .where(ClusterAssignment.pipeline_run_id == run_id)
        .order_by(ClusterAssignment.cluster_id, FeedbackItem.item_date.desc())
    ).all()

    groups: dict[int, list[FeedbackItem]] = defaultdict(list)
    for item, cluster_id in rows:
        groups[int(cluster_id)].append(item)
    return dict(groups)


def _load_embedding_map(
    settings: Settings,
    *,
    mock: bool,
    vector_store: VectorStore | None,
) -> dict[str, list[float]]:
    store = vector_store or get_vector_store(settings, force_mock=mock)
    ids, embeddings, _metadatas = store.get_all_vectors()
    return dict(zip(ids, embeddings, strict=True))


def _quote_payload(item: FeedbackItem) -> dict[str, object]:
    return {
        "item_id": str(item.id),
        "source": item.source,
        "rating": item.rating,
        "text": _truncate_text(item.text),
    }


def _select_label_quotes(
    items: list[FeedbackItem],
    embedding_map: dict[str, list[float]],
    quote_count: int,
) -> list[FeedbackItem]:
    if not items:
        return []

    item_ids = [str(item.id) for item in items]
    nearest_ids = nearest_to_centroid(item_ids, embedding_map, n_results=quote_count)
    by_id = {str(item.id): item for item in items}

    selected = [by_id[item_id] for item_id in nearest_ids if item_id in by_id]
    if selected:
        return selected

    return items[:quote_count]


def _mean_sentiment(session: Session, items: list[FeedbackItem]) -> float | None:
    if not items:
        return None

    item_ids = [item.id for item in items]
    scores = list(
        session.scalars(
            select(Analysis.sentiment_score).where(
                Analysis.feedback_item_id.in_(item_ids),
                Analysis.sentiment_score.is_not(None),
            )
        ).all()
    )
    if not scores:
        return None
    return sum(scores) / len(scores)


def _heuristic_theme_label(items: list[FeedbackItem], cluster_id: int) -> ThemeLabelResponse:
    sample = " ".join(item.text.lower() for item in items[:20])
    if STALE_KEYWORDS.search(sample):
        return ThemeLabelResponse(
            name="Stale Recommendations",
            summary="Users report repetitive playlists and the same artists resurfacing.",
        )
    if QUALITY_KEYWORDS.search(sample):
        return ThemeLabelResponse(
            name="App Reliability Issues",
            summary="Users describe crashes, bugs, and performance problems with the app.",
        )
    if DISCOVERY_KEYWORDS.search(sample):
        return ThemeLabelResponse(
            name="Discovery Frustration",
            summary="Users struggle to find fresh music and trust the recommendation algorithm.",
        )
    return ThemeLabelResponse(
        name=f"Feedback Cluster {cluster_id + 1}",
        summary="Users share mixed feedback about their Spotify listening experience.",
    )


def _label_cluster_with_llm(
    llm: LLMClient,
    *,
    cluster_id: int,
    quotes: list[FeedbackItem],
    settings: Settings,
    rate_limiter: RateLimiter,
) -> tuple[ThemeLabelResponse, int]:
    prompt = build_theme_label_prompt(
        cluster_id=cluster_id,
        quotes=[_quote_payload(item) for item in quotes],
    )
    llm_calls = 0

    for attempt in range(settings.groq_max_retries + 1):
        rate_limiter.wait()
        llm_calls += 1
        raw = llm.complete_json(
            prompt,
            system=THEME_LABEL_SYSTEM_PROMPT,
            model=settings.groq_model_large,
        )
        try:
            return ThemeLabelResponse.model_validate(raw), llm_calls
        except ValidationError as exc:
            if attempt >= settings.groq_max_retries:
                raise
            prompt = prompt + THEME_LABEL_REPAIR_SUFFIX.format(error=exc)

    raise RuntimeError("theme labeling retries exhausted")


def _clear_run_themes(session: Session, run_id: uuid.UUID) -> None:
    theme_ids = list(
        session.scalars(select(Theme.id).where(Theme.pipeline_run_id == run_id)).all()
    )
    if theme_ids:
        session.execute(delete(FeedbackTheme).where(FeedbackTheme.theme_id.in_(theme_ids)))
    session.execute(delete(Theme).where(Theme.pipeline_run_id == run_id))
    session.flush()


def label_themes_for_run(
    session: Session,
    settings: Settings,
    run_id: uuid.UUID,
    *,
    dry_run: bool = False,
    mock: bool = False,
    llm: LLMClient | None = None,
    vector_store: VectorStore | None = None,
) -> ThemeLabelStats:
    stats = ThemeLabelStats()
    groups = _load_cluster_groups(session, run_id)
    stats.total_clusters = len(groups)

    if dry_run:
        stats.themes_created = len(groups)
        stats.items_linked = sum(len(items) for items in groups.values())
        stats.details = {"mode": "dry_run", "max_themes": settings.max_themes}
        return stats

    if not groups:
        raise RuntimeError(
            f"No cluster assignments found for run {run_id}. Run the cluster stage first."
        )

    if len(groups) > settings.max_themes:
        raise RuntimeError(
            f"Found {len(groups)} clusters for run {run_id}; max allowed is {settings.max_themes}"
        )

    embedding_map = _load_embedding_map(settings, mock=mock, vector_store=vector_store)
    use_heuristic = mock or settings.mock_mode
    llm_client = None if use_heuristic else (llm or get_llm_client(settings))
    rate_limiter = RateLimiter(settings.groq_large_rpm)
    llm_calls = 0

    _clear_run_themes(session, run_id)

    for cluster_id in sorted(groups):
        items = groups[cluster_id]
        quotes = _select_label_quotes(
            items,
            embedding_map,
            settings.theme_label_quote_count,
        )

        if use_heuristic:
            label = _heuristic_theme_label(items, cluster_id)
        else:
            label, cluster_calls = _label_cluster_with_llm(
                llm_client,
                cluster_id=cluster_id,
                quotes=quotes,
                settings=settings,
                rate_limiter=rate_limiter,
            )
            llm_calls += cluster_calls

        theme = Theme(
            name=label.name,
            summary=label.summary,
            mention_volume=len(items),
            sentiment_score=_mean_sentiment(session, items),
            cluster_id=cluster_id,
            pipeline_run_id=run_id,
        )
        session.add(theme)
        session.flush()

        for item in items:
            session.add(
                FeedbackTheme(
                    feedback_item_id=item.id,
                    theme_id=theme.id,
                )
            )
            stats.items_linked += 1

        stats.themes_created += 1
        logger.info(
            "Labeled cluster %s as %r (%s items)",
            cluster_id,
            label.name,
            len(items),
        )

    session.flush()
    stats.llm_calls = llm_calls
    stats.details = {
        "mode": "heuristic" if use_heuristic else "groq",
        "model": settings.groq_model_large if not use_heuristic else "heuristic",
        "quote_count": settings.theme_label_quote_count,
    }
    return stats
