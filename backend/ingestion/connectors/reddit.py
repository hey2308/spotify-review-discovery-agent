import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ingestion.connectors.base import SourceConnector
from ingestion.types import FetchedRecord, NormalizedItem

DEFAULT_SUBREDDITS = ("spotify", "Music", "ifyoulikeblank")


class RedditConnector(SourceConnector):
    source_name = "reddit"

    def __init__(
        self,
        subreddits: tuple[str, ...] = DEFAULT_SUBREDDITS,
        client_id: str | None = None,
        client_secret: str | None = None,
        user_agent: str = "spotify-discovery-agent/0.1",
    ) -> None:
        self._subreddits = subreddits
        self._client_id = client_id
        self._client_secret = client_secret
        self._user_agent = user_agent

    def fetch(self, since: datetime, until: datetime) -> list[FetchedRecord]:
        if not self._client_id or not self._client_secret:
            raise RuntimeError("Reddit live fetch requires REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET")

        import praw

        reddit = praw.Reddit(
            client_id=self._client_id,
            client_secret=self._client_secret,
            user_agent=self._user_agent,
        )

        records: list[FetchedRecord] = []
        for subreddit_name in self._subreddits:
            subreddit = reddit.subreddit(subreddit_name)
            for submission in subreddit.search("spotify discovery OR recommendations", time_filter="year", limit=100):
                created = datetime.fromtimestamp(submission.created_utc, tz=UTC)
                if not (since <= created <= until):
                    continue

                post_payload = {
                    "id": submission.id,
                    "title": submission.title,
                    "selftext": submission.selftext,
                    "created_utc": submission.created_utc,
                    "comments": [],
                }
                submission.comments.replace_more(limit=0)
                for comment in list(submission.comments)[:5]:  # type: ignore[call-overload]
                    post_payload["comments"].append(
                        {
                            "id": comment.id,
                            "body": comment.body,
                            "created_utc": comment.created_utc,
                        }
                    )

                records.append(
                    FetchedRecord(
                        external_id=f"post-{submission.id}",
                        payload=post_payload,
                        item_date=created,
                    )
                )
        return records

    def parse_payload(
        self,
        payload: list[dict[str, Any]],
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[FetchedRecord]:
        records: list[FetchedRecord] = []
        for post in payload:
            created = datetime.fromtimestamp(post["created_utc"], tz=UTC)
            if since and until and not (since <= created <= until):
                continue
            records.append(
                FetchedRecord(
                    external_id=f"post-{post['id']}",
                    payload=post,
                    item_date=created,
                )
            )
        return records

    def normalize(self, record: FetchedRecord) -> NormalizedItem | None:
        post = record.payload
        title = str(post.get("title") or "").strip()
        body = str(post.get("selftext") or "").strip()
        text = f"{title}\n\n{body}".strip() if body else title
        if not text:
            return None

        return NormalizedItem(
            source=self.source_name,
            external_id=record.external_id,
            title=title or None,
            text=text,
            rating=None,
            item_date=record.item_date,
            raw_payload=post,
        )

    def normalize_comment(self, post: dict[str, Any], comment: dict[str, Any]) -> NormalizedItem | None:
        body = str(comment.get("body") or "").strip()
        if not body:
            return None
        created = datetime.fromtimestamp(comment["created_utc"], tz=UTC)
        return NormalizedItem(
            source=self.source_name,
            external_id=f"comment-{comment['id']}",
            title=str(post.get("title") or None),
            text=body,
            rating=None,
            item_date=created,
            raw_payload={"post_id": post.get("id"), "comment": comment},
        )

    def expand_records(self, records: list[FetchedRecord]) -> list[NormalizedItem]:
        items: list[NormalizedItem] = []
        for record in records:
            post_item = self.normalize(record)
            if post_item:
                items.append(post_item)
            for comment in record.payload.get("comments", []):
                comment_item = self.normalize_comment(record.payload, comment)
                if comment_item:
                    items.append(comment_item)
        return items

    @classmethod
    def from_fixture(cls, fixture_path: Path, since: datetime, until: datetime) -> list[FetchedRecord]:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        return cls().parse_payload(payload, since=since, until=until)
