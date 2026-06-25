from datetime import UTC, datetime
from email.utils import parsedate_to_datetime


def parse_datetime(value: str) -> datetime:
    """Parse RFC 2822 or ISO 8601 date strings from feeds and APIs."""
    try:
        item_date = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        item_date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if item_date.tzinfo is None:
        item_date = item_date.replace(tzinfo=UTC)
    return item_date
