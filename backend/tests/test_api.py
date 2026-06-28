import json
import re
import time
import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import db.models  # noqa: F401 — register ORM tables for metadata.create_all
from app.deps import get_db
from app.main import app
from app.seed_fixtures import (
    NEED_IDS,
    RUN_ID,
    THEME_DISCOVERY_ID,
    THEME_STALE_ID,
    THEME_UI_ID,
    seed_api_snapshot,
)
from db.base import Base

PII_PATTERNS = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),
    re.compile(r"@[A-Za-z0-9_]{3,}"),
]


@pytest.fixture
def seeded_client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    seed_session = factory()
    seed_api_snapshot(seed_session)
    seed_session.close()

    def override_get_db() -> Generator[Session, None, None]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _collect_response_text(payload: object) -> str:
    return json.dumps(payload)


def _assert_no_pii(payload: object) -> None:
    text = _collect_response_text(payload)
    for pattern in PII_PATTERNS:
        assert pattern.search(text) is None, f"PII pattern matched: {pattern.pattern}"


def test_openapi_lists_api_routes(seeded_client: TestClient):
    response = seeded_client.get("/api/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    for route in (
        "/api/overview",
        "/api/themes",
        "/api/themes/{theme_id}",
        "/api/questions",
        "/api/quotes",
        "/api/segments",
        "/api/unmet-needs",
        "/api/meta",
    ):
        assert route in paths


def test_overview_contract(seeded_client: TestClient):
    response = seeded_client.get("/api/overview")
    assert response.status_code == 200
    payload = response.json()

    assert payload["pipeline_run_id"] == str(RUN_ID)
    assert payload["total_items"] == 12
    assert payload["classified_items"] == 12
    assert payload["date_range"]["from"] == "2026-02-01"
    assert payload["date_range"]["to"] == "2026-05-15"
    assert payload["source_breakdown"]["play_store"] == 5
    assert payload["sentiment_distribution"]["negative"] == 6
    assert payload["headline_insight"]
    assert payload["counts"]["themes"] == 3
    _assert_no_pii(payload)


def test_themes_contract(seeded_client: TestClient):
    response = seeded_client.get("/api/themes")
    assert response.status_code == 200
    payload = response.json()

    assert payload["pipeline_run_id"] == str(RUN_ID)
    assert len(payload["items"]) == 3
    assert payload["items"][0]["name"] == "Stale Recommendations"
    assert payload["items"][0]["mention_volume"] == 5
    _assert_no_pii(payload)


def test_theme_detail_contract(seeded_client: TestClient):
    response = seeded_client.get(f"/api/themes/{THEME_STALE_ID}")
    assert response.status_code == 200
    payload = response.json()

    assert payload["id"] == str(THEME_STALE_ID)
    assert len(payload["quotes"]) >= 1
    assert payload["quotes"][0]["text"]
    assert any(pattern["label"] == "complaint" for pattern in payload["sub_patterns"])
    _assert_no_pii(payload)


def test_theme_not_found_returns_404(seeded_client: TestClient):
    missing = uuid.uuid4()
    response = seeded_client.get(f"/api/themes/{missing}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Theme not found"


def test_questions_contract(seeded_client: TestClient):
    response = seeded_client.get("/api/questions")
    assert response.status_code == 200
    payload = response.json()

    assert payload["pipeline_run_id"] == str(RUN_ID)
    assert len(payload["items"]) == 6
    assert payload["items"][0]["question_id"] == "Q1"
    assert payload["items"][0]["question_text"]
    assert payload["items"][0]["evidence_ids"]
    assert payload["items"][0]["confidence"] == "high"
    _assert_no_pii(payload)


def test_quotes_contract(seeded_client: TestClient):
    response = seeded_client.get("/api/quotes")
    assert response.status_code == 200
    payload = response.json()

    assert payload["total"] == 7
    assert len(payload["items"]) == 7
    first = payload["items"][0]
    assert first["text"]
    assert first["source"]
    assert first["sentiment_label"]
    assert first["theme_ids"]
    assert first["theme_names"]
    _assert_no_pii(payload)


def test_quotes_filter_by_theme(seeded_client: TestClient):
    response = seeded_client.get("/api/quotes", params={"theme_id": str(THEME_UI_ID)})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 0


def test_quotes_filter_by_source(seeded_client: TestClient):
    response = seeded_client.get("/api/quotes", params={"source": "play_store"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert all(item["source"] == "play_store" for item in payload["items"])


def test_quotes_filter_by_rating(seeded_client: TestClient):
    response = seeded_client.get("/api/quotes", params={"rating": 2})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert all(item["rating"] == 2 for item in payload["items"])


def test_quotes_filter_by_date_range(seeded_client: TestClient):
    response = seeded_client.get(
        "/api/quotes",
        params={"date_from": "2026-05-01", "date_to": "2026-05-31"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2


def test_quotes_search(seeded_client: TestClient):
    response = seeded_client.get("/api/quotes", params={"q": "Discover Weekly"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert "Discover Weekly" in payload["items"][0]["text"]


def test_quotes_returns_recommendation_related_only(seeded_client: TestClient):
    response = seeded_client.get("/api/quotes", params={"page_size": 100})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] > 0
    for item in payload["items"]:
        text = item["text"].lower()
        assert any(
            term in text
            for term in (
                "recommend",
                "discover",
                "algorithm",
                "discover weekly",
                "release radar",
                "daily mix",
                "new music",
                "new artist",
            )
        )


def test_quotes_pagination_is_stable(seeded_client: TestClient):
    page_size = 5
    collected: list[str] = []

    for page in range(1, 3):
        response = seeded_client.get(
            "/api/quotes",
            params={"page": page, "page_size": page_size},
        )
        assert response.status_code == 200
        payload = response.json()
        collected.extend(item["id"] for item in payload["items"])

    assert len(collected) == 7
    assert len(set(collected)) == 7


def test_segments_contract(seeded_client: TestClient):
    response = seeded_client.get("/api/segments")
    assert response.status_code == 200
    payload = response.json()

    assert payload["pipeline_run_id"] == str(RUN_ID)
    assert len(payload["items"]) == 3
    labels = {item["label"] for item in payload["items"]}
    assert "Power listeners" in labels
    assert payload["items"][0]["top_frustration"]
    _assert_no_pii(payload)


def test_unmet_needs_contract(seeded_client: TestClient):
    response = seeded_client.get("/api/unmet-needs")
    assert response.status_code == 200
    payload = response.json()

    assert payload["pipeline_run_id"] == str(RUN_ID)
    assert len(payload["items"]) == 4
    assert payload["items"][0]["id"] == str(NEED_IDS["fresh"])
    assert payload["items"][0]["frequency"] == 18
    assert payload["items"][0]["source_attribution"]["play_store"] == 8
    _assert_no_pii(payload)


def test_meta_contract_and_cache_header(seeded_client: TestClient):
    response = seeded_client.get("/api/meta")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=300"

    payload = response.json()
    assert payload["pipeline_run_id"] == str(RUN_ID)
    assert payload["status"] == "completed"
    assert payload["data_freshness"] in {"snapshot", "aging", "stale"}
    assert payload["counts"]["feedback_items"] == 12
    assert payload["counts"]["answers"] == 6
    _assert_no_pii(payload)


def test_invalid_quote_page_returns_422(seeded_client: TestClient):
    response = seeded_client.get("/api/quotes", params={"page": 0})
    assert response.status_code == 422


def test_api_latency_baseline(seeded_client: TestClient):
    durations: list[float] = []
    endpoints = [
        "/api/overview",
        "/api/themes",
        f"/api/themes/{THEME_DISCOVERY_ID}",
        "/api/questions",
        "/api/quotes?page_size=5",
        "/api/segments",
        "/api/unmet-needs",
        "/api/meta",
    ]

    for _ in range(5):
        for endpoint in endpoints:
            start = time.perf_counter()
            response = seeded_client.get(endpoint)
            durations.append(time.perf_counter() - start)
            assert response.status_code == 200

    durations.sort()
    p95 = durations[int(len(durations) * 0.95)]
    assert p95 < 0.3
