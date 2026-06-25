import sys
import uuid
from pathlib import Path

import pytest

from core.config import Settings
from core.embeddings import MockEmbeddingsClient
from core.vectorstore import ChromaVectorStore, MockVectorStore, get_vector_store


def test_mock_vector_store_roundtrip():
    store = get_vector_store(force_mock=True)
    assert isinstance(store, MockVectorStore)
    embeddings = MockEmbeddingsClient().embed(["discovery feels repetitive"])

    item_id = str(uuid.uuid4())
    store.upsert(
        ids=[item_id],
        embeddings=embeddings,
        documents=["discovery feels repetitive"],
        metadatas=[{"source": "reddit", "content_hash": "abc123"}],
    )

    assert store.count() == 1
    assert store.list_entries()[item_id]["content_hash"] == "abc123"

    results = store.query(embeddings[0], n_results=1)
    assert results["ids"][0][0] == item_id

    store.delete([item_id])
    assert store.count() == 0


@pytest.mark.skipif(sys.platform == "win32", reason="Chroma Rust backend unstable on Windows CI")
def test_chroma_vector_store_roundtrip(tmp_path: Path):
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://user:pass@localhost/db",
        GROQ_API_KEY=None,
        CHROMA_PERSIST_DIR=str(tmp_path / "chroma"),
        CHROMA_COLLECTION="test_feedback_embeddings",
    )
    store = ChromaVectorStore(settings)
    embeddings = MockEmbeddingsClient().embed(["discovery feels repetitive"])

    item_id = str(uuid.uuid4())
    store.upsert(
        ids=[item_id],
        embeddings=embeddings,
        documents=["discovery feels repetitive"],
        metadatas=[{"source": "reddit", "theme_id": "none"}],
    )

    results = store.query(embeddings[0], n_results=1)
    assert results["ids"][0][0] == item_id
