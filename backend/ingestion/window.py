from datetime import UTC, datetime, timedelta


def lookback_window(months: int = 6) -> tuple[datetime, datetime]:
    until = datetime.now(UTC)
    since = until - timedelta(days=months * 30)
    return since, until


def within_window(item_date: datetime, since: datetime, until: datetime) -> bool:
    if item_date.tzinfo is None:
        item_date = item_date.replace(tzinfo=UTC)
    return since <= item_date <= until
