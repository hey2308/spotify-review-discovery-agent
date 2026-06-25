import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from core.config import Settings
from core.embeddings import EmbeddingsClient, get_embeddings_client
from core.vectorstore import VectorStore, get_vector_store
from db.models import FeedbackItem


def _normalize_ids(raw_ids: list[str]) -> list[str]:
    normalized: list[str] = []
    for item_id in raw_ids:
        try:
            normalized.append(str(uuid.UUID(item_id)))
        except ValueError:
            continue
    return normalized


def retrieve_feedback_items(
    session: Session,
    settings: Settings,
    query_text: str,
    *,
    n_results: int,
    mock: bool = False,
    vector_store: VectorStore | None = None,
    embedder: EmbeddingsClient | None = None,
) -> list[FeedbackItem]:
    store = vector_store or get_vector_store(settings, force_mock=mock)
    client = embedder or get_embeddings_client(settings, force_mock=mock)

    if store.count() == 0:
        return list(session.scalars(select(FeedbackItem).limit(n_results)).all())

    query_embedding = client.embed([query_text])[0]
    results = store.query(query_embedding, n_results=n_results)
    raw_ids = results.get("ids", [[]])
    if not raw_ids or not raw_ids[0]:
        return []

    item_ids = _normalize_ids(raw_ids[0])
    if not item_ids:
        return []

    items = list(
        session.scalars(
            select(FeedbackItem)
            .where(FeedbackItem.id.in_([uuid.UUID(item_id) for item_id in item_ids]))
            .options(selectinload(FeedbackItem.analysis))
        ).all()
    )
    order = {item_id: index for index, item_id in enumerate(item_ids)}
    return sorted(items, key=lambda item: order.get(str(item.id), len(order)))


def truncate_text(text: str, max_chars: int = 400) -> str:
    cleaned = text.strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3] + "..."


def quote_payload(item: FeedbackItem, *, max_chars: int = 400) -> dict[str, object]:
    payload: dict[str, object] = {
        "item_id": str(item.id),
        "source": item.source,
        "rating": item.rating,
        "text": truncate_text(item.text, max_chars),
    }
    if item.analysis is not None:
        payload["sentiment_label"] = item.analysis.sentiment_label
        payload["intent"] = item.analysis.intent
        payload["segment_hint"] = item.analysis.segment_hint
    return payload
