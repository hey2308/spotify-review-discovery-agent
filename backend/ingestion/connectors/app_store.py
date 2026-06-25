import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from ingestion.connectors.base import SourceConnector
from ingestion.dates import parse_datetime
from ingestion.types import FetchedRecord, NormalizedItem

SPOTIFY_APP_ID = "324684580"
DEFAULT_FEED_URL = (
    f"https://itunes.apple.com/rss/customerreviews/id={SPOTIFY_APP_ID}/sortby=mostrecent/json"
)


def _label_value(value: Any) -> str | None:
    if isinstance(value, dict):
        return value.get("label")
    if isinstance(value, str):
        return value
    return None


class AppStoreConnector(SourceConnector):
    source_name = "app_store"

    def __init__(self, feed_url: str = DEFAULT_FEED_URL, client: httpx.Client | None = None) -> None:
        self._feed_url = feed_url
        self._client = client or httpx.Client(timeout=30.0)

    def fetch(self, since: datetime, until: datetime) -> list[FetchedRecord]:
        response = self._client.get(self._feed_url, params={"l": "en", "cc": "us"})
        response.raise_for_status()
        return self.parse_payload(response.json(), since=since, until=until)

    def parse_payload(
        self,
        payload: dict[str, Any],
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[FetchedRecord]:
        entries = payload.get("feed", {}).get("entry", [])
        if isinstance(entries, dict):
            entries = [entries]

        records: list[FetchedRecord] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if "im:rating" not in entry:
                continue

            updated = _label_value(entry.get("updated"))
            if not updated:
                continue
            item_date = parse_datetime(updated)

            if since and until and not (since <= item_date <= until):
                continue

            external_id = _label_value(entry.get("id")) or f"app_store-{len(records)}"
            records.append(
                FetchedRecord(
                    external_id=external_id,
                    payload=entry,
                    item_date=item_date,
                )
            )
        return records

    def normalize(self, record: FetchedRecord) -> NormalizedItem | None:
        entry = record.payload
        text = _label_value(entry.get("content")) or ""
        if not text.strip():
            return None

        rating_raw = _label_value(entry.get("im:rating"))
        rating = int(rating_raw) if rating_raw and rating_raw.isdigit() else None
        title = _label_value(entry.get("title"))

        return NormalizedItem(
            source=self.source_name,
            external_id=record.external_id,
            title=title,
            text=text,
            rating=rating,
            item_date=record.item_date,
            raw_payload=entry,
        )

    @classmethod
    def from_fixture(cls, fixture_path: Path, since: datetime, until: datetime) -> list[FetchedRecord]:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        return cls().parse_payload(payload, since=since, until=until)
