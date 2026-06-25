from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class FetchedRecord:
    external_id: str
    payload: dict[str, Any]
    item_date: datetime


@dataclass(slots=True)
class NormalizedItem:
    source: str
    external_id: str | None
    title: str | None
    text: str
    rating: int | None
    item_date: datetime
    raw_payload: dict[str, Any] = field(repr=False)
