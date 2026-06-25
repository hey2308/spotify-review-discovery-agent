from abc import ABC, abstractmethod

from core.config import Settings, get_settings


class EmbeddingsClient(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    @property
    @abstractmethod
    def dimension(self) -> int:
        raise NotImplementedError


class MockEmbeddingsClient(EmbeddingsClient):
    def __init__(self, dimension: int = 384) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            seed = sum(ord(char) for char in text) or 1
            vectors.append(
                [((seed * (index + 1)) % 997) / 997.0 for index in range(self._dimension)]
            )
        return vectors


class SentenceTransformerEmbeddingsClient(EmbeddingsClient):
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self._model_name = model_name
        self._model = SentenceTransformer(model_name)
        sample = self._model.encode(["dimension probe"], show_progress_bar=False)
        self._dimension = len(sample[0])

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        kwargs: dict[str, object] = {"show_progress_bar": False}
        if "bge" in self._model_name.lower():
            kwargs["normalize_embeddings"] = True
        vectors = self._model.encode(texts, **kwargs)
        return [vector.tolist() for vector in vectors]


def get_embeddings_client(
    settings: Settings | None = None,
    *,
    force_mock: bool = False,
) -> EmbeddingsClient:
    settings = settings or get_settings()
    if force_mock:
        return MockEmbeddingsClient()
    return SentenceTransformerEmbeddingsClient(settings.embedding_model)
