from core.config import Settings
from core.embeddings import MockEmbeddingsClient, get_embeddings_client


def test_mock_embeddings_are_deterministic():
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://user:pass@localhost/db",
        GROQ_API_KEY=None,
    )
    client = get_embeddings_client(settings, force_mock=True)
    assert isinstance(client, MockEmbeddingsClient)
    assert client.dimension == 384

    first = client.embed(["spotify discovery is hard"])
    second = client.embed(["spotify discovery is hard"])
    assert first == second
    assert len(first[0]) == 384
