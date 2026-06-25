from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, cast

import chromadb

from core.config import Settings, get_settings


class VectorStore(ABC):
    @abstractmethod
    def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def query(
        self,
        query_embedding: list[float],
        *,
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_all_vectors(
        self,
    ) -> tuple[list[str], list[list[float]], list[dict[str, Any]]]:
        """Return aligned ids, embeddings, and metadata for all stored vectors."""
        raise NotImplementedError

    @abstractmethod
    def count(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def list_entries(self) -> dict[str, dict[str, Any]]:
        """Return id → metadata for all stored vectors."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, ids: list[str]) -> None:
        raise NotImplementedError

    def reset(self) -> None:
        """Remove all vectors from the collection."""
        entries = self.list_entries()
        if entries:
            self.delete(list(entries.keys()))


class MockVectorStore(VectorStore):
    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        for index, item_id in enumerate(ids):
            self._store[item_id] = {
                "embedding": embeddings[index],
                "document": documents[index],
                "metadata": (metadatas or [{}] * len(ids))[index],
            }

    def query(
        self,
        query_embedding: list[float],
        *,
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ids = list(self._store.keys())[:n_results]
        return {
            "ids": [ids],
            "documents": [[self._store[item_id]["document"] for item_id in ids]],
            "metadatas": [[self._store[item_id]["metadata"] for item_id in ids]],
            "distances": [[0.0 for _ in ids]],
        }

    def get_all_vectors(
        self,
    ) -> tuple[list[str], list[list[float]], list[dict[str, Any]]]:
        ids = sorted(self._store.keys())
        embeddings = [self._store[item_id]["embedding"] for item_id in ids]
        metadatas = [self._store[item_id]["metadata"] for item_id in ids]
        return ids, embeddings, metadatas

    def count(self) -> int:
        return len(self._store)

    def list_entries(self) -> dict[str, dict[str, Any]]:
        return {item_id: data["metadata"] for item_id, data in self._store.items()}

    def delete(self, ids: list[str]) -> None:
        for item_id in ids:
            self._store.pop(item_id, None)


class ChromaVectorStore(VectorStore):
    def __init__(self, settings: Settings) -> None:
        persist_dir = Path(settings.chroma_persist_dir)
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection = self._client.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,  # type: ignore[arg-type]
            documents=documents,
            metadatas=metadatas,  # type: ignore[arg-type]
        )

    def query(
        self,
        query_embedding: list[float],
        *,
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._collection.query(
                query_embeddings=[query_embedding],  # type: ignore[arg-type]
                n_results=n_results,
                where=where,
            ),
        )

    def get_all_vectors(
        self,
    ) -> tuple[list[str], list[list[float]], list[dict[str, Any]]]:
        result = self._collection.get(include=["embeddings", "metadatas"])
        ids = result.get("ids", [])
        embeddings = result.get("embeddings", [])
        metadatas = result.get("metadatas", [])
        if embeddings is None:
            embeddings = []
        return (
            ids,
            cast(list[list[float]], embeddings),
            [metadata or {} for metadata in metadatas],
        )

    def count(self) -> int:
        return self._collection.count()

    def list_entries(self) -> dict[str, dict[str, Any]]:
        result = self._collection.get(include=["metadatas"])
        ids = result.get("ids", [])
        metadatas = result.get("metadatas", [])
        return {
            item_id: metadata or {}
            for item_id, metadata in zip(ids, metadatas, strict=False)
        }

    def delete(self, ids: list[str]) -> None:
        if ids:
            self._collection.delete(ids=ids)


def get_vector_store(
    settings: Settings | None = None,
    *,
    force_mock: bool = False,
) -> VectorStore:
    settings = settings or get_settings()
    if force_mock:
        return MockVectorStore()
    return ChromaVectorStore(settings)


def reset_vector_store(settings: Settings | None = None) -> None:
    """Delete all vectors in the configured Chroma collection (dev helper)."""
    store = get_vector_store(settings)
    store.reset()
