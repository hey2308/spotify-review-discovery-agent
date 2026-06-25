import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import Settings
from core.embeddings import EmbeddingsClient, get_embeddings_client
from core.vectorstore import VectorStore, get_vector_store
from db.models import FeedbackItem

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EmbedStats:
    total_items: int = 0
    embedded: int = 0
    cached: int = 0
    deleted_orphans: int = 0
    failed: int = 0
    details: dict[str, object] = field(default_factory=dict)


def _truncate_text(text: str, max_chars: int) -> str:
    cleaned = text.strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3] + "..."


def _item_metadata(item: FeedbackItem) -> dict[str, str | int | float | bool]:
    return {
        "source": item.source,
        "content_hash": item.content_hash,
        "item_date": item.item_date.isoformat(),
    }


def _items_needing_embedding(
    items: list[FeedbackItem],
    stored: dict[str, dict[str, object]],
) -> tuple[list[FeedbackItem], int]:
    to_embed: list[FeedbackItem] = []
    cached = 0

    for item in items:
        item_id = str(item.id)
        existing = stored.get(item_id)
        if existing and existing.get("content_hash") == item.content_hash:
            cached += 1
            continue
        to_embed.append(item)

    return to_embed, cached


def _sync_orphan_vectors(
    store: VectorStore,
    feedback_ids: set[str],
) -> int:
    stored_ids = set(store.list_entries().keys())
    orphan_ids = sorted(stored_ids - feedback_ids)
    if orphan_ids:
        store.delete(orphan_ids)
    return len(orphan_ids)


def embed_feedback_items(
    session: Session,
    settings: Settings,
    run_id: uuid.UUID,
    *,
    dry_run: bool = False,
    mock: bool = False,
    embeddings_client: EmbeddingsClient | None = None,
    vector_store: VectorStore | None = None,
) -> EmbedStats:
    del run_id  # reserved for future run-stamped metadata
    stats = EmbedStats()
    items = list(session.scalars(select(FeedbackItem)).all())
    stats.total_items = len(items)

    if dry_run:
        stats.embedded = stats.total_items
        stats.details = {"mode": "dry_run", "model": settings.embedding_model}
        return stats

    store = vector_store or get_vector_store(settings, force_mock=mock)
    client = embeddings_client or get_embeddings_client(settings, force_mock=mock)
    feedback_ids = {str(item.id) for item in items}

    stats.deleted_orphans = _sync_orphan_vectors(store, feedback_ids)
    stored = store.list_entries()
    to_embed, cached = _items_needing_embedding(items, stored)
    stats.cached = cached

    batch_size = settings.embedding_batch_size
    for offset in range(0, len(to_embed), batch_size):
        batch = to_embed[offset : offset + batch_size]
        try:
            documents = [
                _truncate_text(item.text, settings.embedding_max_text_chars)
                for item in batch
            ]
            vectors = client.embed(documents)
            store.upsert(
                ids=[str(item.id) for item in batch],
                embeddings=vectors,
                documents=documents,
                metadatas=[_item_metadata(item) for item in batch],
            )
            stats.embedded += len(batch)
            logger.info(
                "Embedded batch %s-%s of %s",
                offset + 1,
                offset + len(batch),
                len(to_embed),
            )
        except Exception:
            logger.exception("Failed to embed batch starting at offset %s", offset)
            stats.failed += len(batch)

    stats.details = {
        "mode": "mock" if mock else "local",
        "model": settings.embedding_model,
        "collection_count": store.count(),
        "dimension": client.dimension,
    }
    return stats
