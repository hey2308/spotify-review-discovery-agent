import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ingestion.connectors.base import SourceConnector
from ingestion.types import FetchedRecord, NormalizedItem

SPOTIFY_PACKAGE = "com.spotify.music"
DEFAULT_PAGE_SIZE = 200
DEFAULT_MAX_REVIEWS = 3000


class PlayStoreConnector(SourceConnector):
    source_name = "play_store"

    def __init__(
        self,
        package_name: str = SPOTIFY_PACKAGE,
        max_reviews: int = DEFAULT_MAX_REVIEWS,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> None:
        self._package_name = package_name
        self._max_reviews = max_reviews
        self._page_size = page_size

    def fetch(self, since: datetime, until: datetime) -> list[FetchedRecord]:
        raw_reviews = self._fetch_raw_reviews(since=since)
        return self.parse_payload(raw_reviews, since=since, until=until)

    def _fetch_raw_reviews(self, since: datetime) -> list[dict[str, Any]]:
        from google_play_scraper import Sort, reviews

        collected: list[dict[str, Any]] = []
        continuation_token = None

        while len(collected) < self._max_reviews:
            batch_size = min(self._page_size, self._max_reviews - len(collected))
            batch, continuation_token = reviews(
                self._package_name,
                lang="en",
                country="us",
                sort=Sort.NEWEST,
                count=batch_size,
                continuation_token=continuation_token,
            )
            if not batch:
                break

            collected.extend(batch)

            if self._batch_ends_before_window(batch, since):
                break

            if continuation_token is None:
                break

        return collected

    @staticmethod
    def _batch_ends_before_window(batch: list[dict[str, Any]], since: datetime) -> bool:
        dates: list[datetime] = []
        for review in batch:
            item_date = review.get("at")
            if not isinstance(item_date, datetime):
                continue
            if item_date.tzinfo is None:
                item_date = item_date.replace(tzinfo=UTC)
            dates.append(item_date)
        if not dates:
            return False
        return min(dates) < since

    def parse_payload(
        self,
        payload: list[dict[str, Any]],
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[FetchedRecord]:
        records: list[FetchedRecord] = []
        for review in payload:
            item_date = review.get("at")
            if not isinstance(item_date, datetime):
                continue
            if item_date.tzinfo is None:
                item_date = item_date.replace(tzinfo=UTC)
            if since and until and not (since <= item_date <= until):
                continue

            external_id = str(review.get("reviewId") or f"play_store-{len(records)}")
            records.append(
                FetchedRecord(
                    external_id=external_id,
                    payload=review,
                    item_date=item_date,
                )
            )
        return records

    def normalize(self, record: FetchedRecord) -> NormalizedItem | None:
        review = record.payload
        text = str(review.get("content") or "").strip()
        if not text:
            return None

        score = review.get("score")
        rating = int(score) if isinstance(score, (int, float)) else None

        return NormalizedItem(
            source=self.source_name,
            external_id=record.external_id,
            title=None,
            text=text,
            rating=rating,
            item_date=record.item_date,
            raw_payload=review,
        )

    @classmethod
    def from_fixture(cls, fixture_path: Path, since: datetime, until: datetime) -> list[FetchedRecord]:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        for review in payload:
            if isinstance(review.get("at"), str):
                review["at"] = datetime.fromisoformat(review["at"]).replace(tzinfo=UTC)
        return cls().parse_payload(payload, since=since, until=until)
