import hashlib
import re

from ingestion.filters import strip_emojis
from ingestion.pii import scrub_payload, scrub_text
from ingestion.types import NormalizedItem


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def content_hash(source: str, text: str) -> str:
    digest_input = f"{source}:{normalize_text(text)}"
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()


def prepare_item(item: NormalizedItem) -> NormalizedItem:
    scrubbed_payload = scrub_payload(item.raw_payload)
    title = strip_emojis(scrub_text(item.title)) if item.title else None
    text = strip_emojis(scrub_text(item.text))
    return NormalizedItem(
        source=item.source,
        external_id=item.external_id,
        title=title,
        text=text,
        rating=item.rating,
        item_date=item.item_date,
        raw_payload=scrubbed_payload if isinstance(scrubbed_payload, dict) else item.raw_payload,
    )
