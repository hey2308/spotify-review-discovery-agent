from pipeline.embedding_utils import nearest_to_centroid


def test_nearest_to_centroid_prefers_cluster_core():
    embedding_map = {
        "a": [1.0, 0.0, 0.0],
        "b": [0.99, 0.01, 0.0],
        "c": [0.0, 1.0, 0.0],
    }

    selected = nearest_to_centroid(["a", "b", "c"], embedding_map, n_results=2)

    assert set(selected) == {"a", "b"}
