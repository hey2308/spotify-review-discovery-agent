import html
import json
import logging
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from ingestion.connectors.base import SourceConnector
from ingestion.types import FetchedRecord, NormalizedItem

logger = logging.getLogger(__name__)

BLUESKY_SEARCH_URL = "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts"
DEFAULT_BLUESKY_QUERIES = (
    "spotify discovery",
    "spotify recommendations",
    "spotify algorithm",
    "spotify discover weekly",
    "spotify playlist",
    "spotify shuffle",
    "spotify radio",
    "spotify repeat",
    "spotify stale",
    "spotify wrapped",
    "spotify release radar",
    "spotify daily mix",
    "spotify autoplay",
    "spotify home feed",
    "spotify bad recommendations",
    "spotify find new music",
    "spotify music discovery",
)
DEFAULT_MASTODON_INSTANCES = (
    "https://mastodon.social",
    "https://mastodon.online",
    "https://fosstodon.org",
    "https://mas.to",
    "https://hachyderm.io",
    "https://techhub.social",
)
DEFAULT_MASTODON_TAGS = (
    "spotifydiscovery",
    "discoverweekly",
    "spotify",
)
DEFAULT_SOCIAL_MAX_ITEMS = 3000
DEFAULT_BLUESKY_PAGE_SIZE = 100
DEFAULT_MASTODON_PAGE_SIZE = 40
DEFAULT_BLUESKY_SLICE_DAYS = 14
DEFAULT_MASTODON_MAX_PAGES = 50
BROAD_MASTODON_TAGS = {"spotify"}
DISCOVERY_KEYWORDS = re.compile(
    r"\b("
    r"discover\w*|recommend\w*|playlist|algorithm|radio|shuffle|"
    r"new music|find music|stale|repetitive|repeat(?:ing|s)?|"
    r"discover weekly|release radar|daily mix|spotify wrapped"
    r")\b",
    re.IGNORECASE,
)


def strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def time_slices(since: datetime, until: datetime, *, days: int) -> list[tuple[datetime, datetime]]:
    slices: list[tuple[datetime, datetime]] = []
    cursor = since
    while cursor < until:
        slice_end = min(cursor + timedelta(days=days), until)
        slices.append((cursor, slice_end))
        cursor = slice_end
    return slices


def _iso_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class SocialConnector(SourceConnector):
    source_name = "social"

    def __init__(
        self,
        bluesky_queries: tuple[str, ...] | list[str] = DEFAULT_BLUESKY_QUERIES,
        mastodon_instances: tuple[str, ...] | list[str] = DEFAULT_MASTODON_INSTANCES,
        mastodon_tags: tuple[str, ...] | list[str] = DEFAULT_MASTODON_TAGS,
        max_items: int = DEFAULT_SOCIAL_MAX_ITEMS,
        bluesky_page_size: int = DEFAULT_BLUESKY_PAGE_SIZE,
        mastodon_page_size: int = DEFAULT_MASTODON_PAGE_SIZE,
        bluesky_slice_days: int = DEFAULT_BLUESKY_SLICE_DAYS,
        mastodon_max_pages: int = DEFAULT_MASTODON_MAX_PAGES,
        throttle_seconds: float = 0.0,
        user_agent: str = "spotify-discovery-agent/0.1",
        client: httpx.Client | None = None,
    ) -> None:
        self._bluesky_queries = tuple(bluesky_queries)
        self._mastodon_instances = tuple(
            instance.rstrip("/") for instance in mastodon_instances
        )
        self._mastodon_tags = tuple(mastodon_tags)
        self._max_items = max_items
        self._bluesky_page_size = bluesky_page_size
        self._mastodon_page_size = mastodon_page_size
        self._bluesky_slice_days = bluesky_slice_days
        self._mastodon_max_pages = mastodon_max_pages
        self._throttle_seconds = throttle_seconds
        self._user_agent = user_agent
        self._client = client or httpx.Client(
            timeout=30.0,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
        )

    def fetch(self, since: datetime, until: datetime) -> list[FetchedRecord]:
        records: list[FetchedRecord] = []
        seen_ids: set[str] = set()

        try:
            self._fetch_bluesky(since, until, records, seen_ids)
        except Exception:
            logger.exception("Bluesky fetch failed")

        try:
            self._fetch_mastodon(since, until, records, seen_ids)
        except Exception:
            logger.exception("Mastodon fetch failed")

        return records

    def _maybe_throttle(self) -> None:
        if self._throttle_seconds:
            time.sleep(self._throttle_seconds)

    def _fetch_bluesky(
        self,
        since: datetime,
        until: datetime,
        records: list[FetchedRecord],
        seen_ids: set[str],
    ) -> None:
        slices = time_slices(since, until, days=self._bluesky_slice_days)

        for query in self._bluesky_queries:
            if len(seen_ids) >= self._max_items:
                return

            for slice_since, slice_until in slices:
                if len(seen_ids) >= self._max_items:
                    return

                self._maybe_throttle()
                response = self._client.get(
                    BLUESKY_SEARCH_URL,
                    params={
                        "q": query,
                        "limit": self._bluesky_page_size,
                        "sort": "latest",
                        "since": _iso_datetime(slice_since),
                        "until": _iso_datetime(slice_until),
                    },
                )
                if response.status_code != 200:
                    logger.warning(
                        "Bluesky search failed for query=%r slice=%s..%s: %s",
                        query,
                        slice_since.date(),
                        slice_until.date(),
                        response.status_code,
                    )
                    continue

                for record in self.parse_bluesky_payload(
                    response.json(),
                    since=since,
                    until=until,
                ):
                    if record.external_id in seen_ids:
                        continue
                    seen_ids.add(record.external_id)
                    records.append(record)
                    if len(seen_ids) >= self._max_items:
                        return

    def _fetch_mastodon(
        self,
        since: datetime,
        until: datetime,
        records: list[FetchedRecord],
        seen_ids: set[str],
    ) -> None:
        for instance in self._mastodon_instances:
            if len(seen_ids) >= self._max_items:
                return

            host = urlparse(instance).netloc or instance.removeprefix("https://")
            for tag in self._mastodon_tags:
                if len(seen_ids) >= self._max_items:
                    return

                max_id: str | None = None
                for _page in range(self._mastodon_max_pages):
                    if len(seen_ids) >= self._max_items:
                        return

                    self._maybe_throttle()
                    params: dict[str, Any] = {"limit": self._mastodon_page_size}
                    if max_id is not None:
                        params["max_id"] = max_id

                    response = self._client.get(
                        f"{instance}/api/v1/timelines/tag/{tag}",
                        params=params,
                    )
                    if response.status_code != 200:
                        logger.warning(
                            "Mastodon tag fetch failed for %s #%s: %s",
                            host,
                            tag,
                            response.status_code,
                        )
                        break

                    statuses = response.json()
                    if not isinstance(statuses, list) or not statuses:
                        break

                    batch_records = self.parse_mastodon_tag_payload(
                        statuses,
                        instance=host,
                        tag=tag,
                        since=since,
                        until=until,
                    )
                    for record in batch_records:
                        if record.external_id in seen_ids:
                            continue
                        seen_ids.add(record.external_id)
                        records.append(record)
                        if len(seen_ids) >= self._max_items:
                            return

                    oldest_date = datetime.fromisoformat(
                        statuses[-1]["created_at"].replace("Z", "+00:00")
                    )
                    if oldest_date < since:
                        break

                    max_id = str(statuses[-1]["id"])
                    if len(statuses) < self._mastodon_page_size:
                        break

    def parse_bluesky_payload(
        self,
        payload: dict[str, Any],
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[FetchedRecord]:
        records: list[FetchedRecord] = []
        for post in payload.get("posts", []):
            record = post.get("record", {})
            created_raw = record.get("createdAt")
            if not created_raw:
                continue
            item_date = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
            if since and until and not (since <= item_date <= until):
                continue

            external_id = str(post.get("uri") or f"bluesky-{len(records)}")
            records.append(
                FetchedRecord(
                    external_id=external_id,
                    payload={
                        "platform": "bluesky",
                        "uri": external_id,
                        "text": record.get("text"),
                        "createdAt": created_raw,
                    },
                    item_date=item_date,
                )
            )
        return records

    def parse_mastodon_tag_payload(
        self,
        payload: list[dict[str, Any]] | dict[str, Any],
        *,
        instance: str,
        tag: str,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[FetchedRecord]:
        if isinstance(payload, dict):
            statuses = payload.get("statuses", [])
        else:
            statuses = payload

        records: list[FetchedRecord] = []
        for status in statuses:
            created_raw = status.get("created_at")
            if not created_raw:
                continue
            item_date = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
            if since and until and not (since <= item_date <= until):
                continue

            text = strip_html(str(status.get("content") or status.get("text") or ""))
            if tag in BROAD_MASTODON_TAGS and not DISCOVERY_KEYWORDS.search(text):
                continue
            if not text:
                continue

            status_id = str(status.get("id") or f"mastodon-{len(records)}")
            external_id = f"{instance}:{status_id}"
            records.append(
                FetchedRecord(
                    external_id=external_id,
                    payload={
                        "platform": "mastodon",
                        "instance": instance,
                        "tag": tag,
                        "id": status_id,
                        "text": text,
                        "created_at": created_raw,
                        "url": status.get("url"),
                    },
                    item_date=item_date,
                )
            )
        return records

    def parse_mastodon_payload(
        self,
        payload: dict[str, Any],
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[FetchedRecord]:
        return self.parse_mastodon_tag_payload(
            payload.get("statuses", []),
            instance="search",
            tag="search",
            since=since,
            until=until,
        )

    def parse_payload(
        self,
        payload: dict[str, Any],
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[FetchedRecord]:
        records: list[FetchedRecord] = []
        if "posts" in payload:
            records.extend(self.parse_bluesky_payload(payload, since=since, until=until))
        if "statuses" in payload:
            records.extend(
                self.parse_mastodon_payload(payload, since=since, until=until)
            )
        return records

    def normalize(self, record: FetchedRecord) -> NormalizedItem | None:
        payload = record.payload
        text = strip_html(str(payload.get("text") or ""))
        if not text:
            return None

        platform = str(payload.get("platform") or "social")
        return NormalizedItem(
            source=self.source_name,
            external_id=f"{platform}:{record.external_id}",
            title=None,
            text=text,
            rating=None,
            item_date=record.item_date,
            raw_payload=payload,
        )

    @classmethod
    def from_fixture(cls, fixture_path: Path, since: datetime, until: datetime) -> list[FetchedRecord]:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        return cls().parse_payload(payload, since=since, until=until)
