import numpy as np


def _normalize(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector)
    if norm == 0.0:
        return vector
    return vector / norm


def nearest_to_centroid(
    item_ids: list[str],
    embedding_map: dict[str, list[float]],
    *,
    n_results: int,
) -> list[str]:
    if not item_ids:
        return []

    available = [item_id for item_id in item_ids if item_id in embedding_map]
    if not available:
        return item_ids[:n_results]

    vectors = np.array([embedding_map[item_id] for item_id in available], dtype=float)
    centroid = _normalize(vectors.mean(axis=0))
    normalized = np.array([_normalize(vector) for vector in vectors])
    similarities = normalized @ centroid
    ranked = sorted(
        zip(available, similarities, strict=True),
        key=lambda pair: (-pair[1], pair[0]),
    )
    return [item_id for item_id, _score in ranked[:n_results]]
