import hashlib
import logging
import uuid
from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from core.config import Settings
from core.vectorstore import VectorStore, get_vector_store
from db.models import ClusterAssignment, FeedbackItem

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ClusterStats:
    total_items: int = 0
    clustered: int = 0
    n_clusters: int = 0
    noise_assigned: int = 0
    merges_performed: int = 0
    details: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class ClusteringOutput:
    item_ids: list[str]
    cluster_ids: list[int]
    n_clusters: int
    noise_assigned: int
    merges_performed: int
    umap_coords: np.ndarray | None = None


def _cluster_id_list(labels: np.ndarray) -> list[int]:
    return sorted({int(label) for label in labels})


def _assign_noise(labels: np.ndarray, coords: np.ndarray) -> tuple[np.ndarray, int]:
    labels = labels.copy()
    noise_mask = labels == -1
    noise_count = int(noise_mask.sum())
    if noise_count == 0:
        return labels, 0

    positive = [cluster_id for cluster_id in _cluster_id_list(labels) if cluster_id != -1]
    if not positive:
        labels[noise_mask] = 0
        return labels, noise_count

    centroids = {
        cluster_id: coords[labels == cluster_id].mean(axis=0) for cluster_id in positive
    }
    for index in np.where(noise_mask)[0]:
        distances = {
            cluster_id: float(np.linalg.norm(coords[index] - centroid))
            for cluster_id, centroid in centroids.items()
        }
        labels[index] = min(distances, key=lambda cluster_id: (distances[cluster_id], cluster_id))
    return labels, noise_count


def _merge_to_max_clusters(
    labels: np.ndarray,
    coords: np.ndarray,
    max_clusters: int,
) -> tuple[np.ndarray, int]:
    labels = labels.copy()
    merges = 0

    while len(_cluster_id_list(labels)) > max_clusters:
        cluster_ids = _cluster_id_list(labels)
        sizes = {cluster_id: int((labels == cluster_id).sum()) for cluster_id in cluster_ids}
        smallest = min(cluster_ids, key=lambda cluster_id: (sizes[cluster_id], cluster_id))
        others = [cluster_id for cluster_id in cluster_ids if cluster_id != smallest]

        smallest_centroid = coords[labels == smallest].mean(axis=0)

        def distance_to(cluster_id: int) -> float:
            centroid = coords[labels == cluster_id].mean(axis=0)
            return float(np.linalg.norm(smallest_centroid - centroid))

        nearest = min(others, key=lambda cluster_id: (distance_to(cluster_id), cluster_id))
        labels[labels == smallest] = nearest
        merges += 1

    return labels, merges


def _renumber_clusters(labels: np.ndarray) -> np.ndarray:
    cluster_ids = _cluster_id_list(labels)
    sizes = {cluster_id: int((labels == cluster_id).sum()) for cluster_id in cluster_ids}
    order = sorted(cluster_ids, key=lambda cluster_id: (-sizes[cluster_id], cluster_id))
    mapping = {old: new for new, old in enumerate(order)}
    return np.array([mapping[int(label)] for label in labels], dtype=np.int64)


def _mock_cluster_labels(item_ids: list[str], max_clusters: int) -> np.ndarray:
    bucket_count = max(1, min(max_clusters, len(item_ids)))
    labels = np.array(
        [
            int(hashlib.sha256(item_id.encode()).hexdigest(), 16) % bucket_count
            for item_id in item_ids
        ],
        dtype=np.int64,
    )
    return _renumber_clusters(labels)


def cluster_embeddings(
    item_ids: list[str],
    embeddings: np.ndarray,
    settings: Settings,
    *,
    mock: bool = False,
) -> ClusteringOutput:
    if len(item_ids) == 0:
        raise ValueError("Cannot cluster zero items")

    if mock:
        labels = _mock_cluster_labels(item_ids, settings.max_themes)
        n_clusters = len(_cluster_id_list(labels))
        assert 1 <= n_clusters <= settings.max_themes
        return ClusteringOutput(
            item_ids=item_ids,
            cluster_ids=[int(label) for label in labels],
            n_clusters=n_clusters,
            noise_assigned=0,
            merges_performed=0,
        )

    if len(item_ids) == 1:
        return ClusteringOutput(
            item_ids=item_ids,
            cluster_ids=[0],
            n_clusters=1,
            noise_assigned=0,
            merges_performed=0,
        )

    import hdbscan
    import umap

    n_neighbors = min(settings.umap_n_neighbors, len(item_ids) - 1)
    reducer = umap.UMAP(
        n_neighbors=max(2, n_neighbors),
        n_components=min(settings.umap_n_components, len(item_ids) - 1),
        min_dist=settings.umap_min_dist,
        metric="cosine",
        random_state=settings.umap_random_state,
    )
    coords = reducer.fit_transform(embeddings)

    min_cluster_size = min(settings.hdbscan_min_cluster_size, max(2, len(item_ids) // 10))
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=max(2, min_cluster_size),
        min_samples=settings.hdbscan_min_samples,
        metric="euclidean",
        cluster_selection_method="eom",
    )
    raw_labels = clusterer.fit_predict(coords)
    labels, noise_assigned = _assign_noise(raw_labels, coords)
    labels, merges_performed = _merge_to_max_clusters(labels, coords, settings.max_themes)
    labels = _renumber_clusters(labels)

    cluster_ids = _cluster_id_list(labels)
    if not (1 <= len(cluster_ids) <= settings.max_themes):
        raise RuntimeError(
            f"Clustering produced {len(cluster_ids)} clusters; "
            f"expected 1–{settings.max_themes}"
        )

    return ClusteringOutput(
        item_ids=item_ids,
        cluster_ids=[int(label) for label in labels],
        n_clusters=len(cluster_ids),
        noise_assigned=noise_assigned,
        merges_performed=merges_performed,
        umap_coords=coords,
    )


def _load_embeddings(
    session: Session,
    settings: Settings,
    *,
    mock: bool,
    vector_store: VectorStore | None,
) -> tuple[list[str], np.ndarray]:
    feedback_ids = {
        str(item_id)
        for item_id in session.scalars(select(FeedbackItem.id)).all()
    }
    if not feedback_ids:
        return [], np.empty((0, 0))

    store = vector_store or get_vector_store(settings, force_mock=mock)
    ids, embeddings, _metadatas = store.get_all_vectors()
    if len(ids) != len(feedback_ids):
        missing = len(feedback_ids - set(ids))
        extra = len(set(ids) - feedback_ids)
        raise RuntimeError(
            "Vector store is out of sync with feedback_items "
            f"(db={len(feedback_ids)}, chroma={len(ids)}, missing={missing}, extra={extra}). "
            "Run the embed stage first."
        )

    ordered_ids = sorted(ids, key=lambda item_id: item_id)
    id_to_index = {item_id: index for index, item_id in enumerate(ids)}
    matrix = np.array([embeddings[id_to_index[item_id]] for item_id in ordered_ids], dtype=float)
    return ordered_ids, matrix


def _persist_assignments(
    session: Session,
    run_id: uuid.UUID,
    item_ids: list[str],
    cluster_ids: list[int],
) -> None:
    session.execute(delete(ClusterAssignment).where(ClusterAssignment.pipeline_run_id == run_id))
    session.add_all(
        [
            ClusterAssignment(
                feedback_item_id=uuid.UUID(item_id),
                pipeline_run_id=run_id,
                cluster_id=cluster_id,
            )
            for item_id, cluster_id in zip(item_ids, cluster_ids, strict=True)
        ]
    )
    session.flush()


def cluster_feedback_items(
    session: Session,
    settings: Settings,
    run_id: uuid.UUID,
    *,
    dry_run: bool = False,
    mock: bool = False,
    vector_store: VectorStore | None = None,
) -> ClusterStats:
    stats = ClusterStats()
    stats.total_items = session.scalar(select(func.count()).select_from(FeedbackItem)) or 0

    if stats.total_items == 0:
        stats.details = {"mode": "empty"}
        return stats

    if dry_run:
        stats.clustered = stats.total_items
        stats.n_clusters = min(settings.max_themes, stats.total_items)
        stats.details = {"mode": "dry_run", "max_themes": settings.max_themes}
        return stats

    item_ids, embeddings = _load_embeddings(
        session,
        settings,
        mock=mock,
        vector_store=vector_store,
    )
    output = cluster_embeddings(item_ids, embeddings, settings, mock=mock)
    _persist_assignments(session, run_id, output.item_ids, output.cluster_ids)

    stats.clustered = len(output.item_ids)
    stats.n_clusters = output.n_clusters
    stats.noise_assigned = output.noise_assigned
    stats.merges_performed = output.merges_performed
    stats.details = {
        "mode": "mock" if mock else "local",
        "max_themes": settings.max_themes,
        "umap_n_neighbors": settings.umap_n_neighbors,
        "hdbscan_min_cluster_size": settings.hdbscan_min_cluster_size,
    }
    logger.info(
        "Clustered %s items into %s themes (noise_assigned=%s, merges=%s)",
        stats.clustered,
        stats.n_clusters,
        stats.noise_assigned,
        stats.merges_performed,
    )
    return stats
