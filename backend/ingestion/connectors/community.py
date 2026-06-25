from datetime import UTC, datetime
from pathlib import Path

import feedparser
import httpx

from ingestion.connectors.base import SourceConnector
from ingestion.dates import parse_datetime
from ingestion.types import FetchedRecord, NormalizedItem

DEFAULT_COMMUNITY_FEED_URL = (
    "https://community.spotify.com/rss/message?board.id=iOS_iPhone_iPad"
)


class CommunityConnector(SourceConnector):
    source_name = "community"

    def __init__(
        self,
        feed_url: str = DEFAULT_COMMUNITY_FEED_URL,
        client: httpx.Client | None = None,
    ) -> None:
        self._feed_url = feed_url
        self._client = client or httpx.Client(timeout=30.0)

    def fetch(self, since: datetime, until: datetime) -> list[FetchedRecord]:
        response = self._client.get(self._feed_url)
        response.raise_for_status()
        return self.parse_feed(response.text, since=since, until=until)

    def parse_feed(
        self,
        feed_text: str,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[FetchedRecord]:
        parsed = feedparser.parse(feed_text)
        records: list[FetchedRecord] = []
        for entry in parsed.entries:
            published = entry.get("published") or entry.get("updated")
            if not published:
                continue
            item_date = parse_datetime(published)
            if since and until and not (since <= item_date <= until):
                continue

            external_id = str(entry.get("id") or entry.get("link") or f"community-{len(records)}")
            payload = {
                "id": external_id,
                "title": entry.get("title"),
                "summary": entry.get("summary"),
                "link": entry.get("link"),
                "published": published,
            }
            records.append(
                FetchedRecord(
                    external_id=external_id,
                    payload=payload,
                    item_date=item_date,
                )
            )
        return records

    def normalize(self, record: FetchedRecord) -> NormalizedItem | None:
        entry = record.payload
        title = str(entry.get("title") or "").strip()
        summary = str(entry.get("summary") or "").strip()
        text = summary or title
        if not text:
            return None

        return NormalizedItem(
            source=self.source_name,
            external_id=record.external_id,
            title=title or None,
            text=text,
            rating=None,
            item_date=record.item_date,
            raw_payload=entry,
        )

    @classmethod
    def from_fixture(cls, fixture_path: Path, since: datetime, until: datetime) -> list[FetchedRecord]:
        return cls().parse_feed(fixture_path.read_text(encoding="utf-8"), since=since, until=until)
