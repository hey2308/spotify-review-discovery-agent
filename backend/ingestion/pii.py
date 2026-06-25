import re
from datetime import datetime
from typing import Any

REDACTED = "[redacted]"

EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\d)"
)
HANDLE_PATTERN = re.compile(r"(?<!\w)@[A-Za-z0-9_]{1,30}\b")
DEVICE_ID_PATTERN = re.compile(
    r"\b(?:device[_\s-]?id|android[_\s-]?id|idfa|gaid)\s*[:=]\s*"
    r"[A-Za-z0-9._-]{6,}\b",
    re.IGNORECASE,
)
USERNAME_PATTERN = re.compile(
    r"\b(?:username|user name|posted by|reviewer)\s*[:=]\s*[@\w.-]{2,32}\b",
    re.IGNORECASE,
)

PII_PATTERNS = (
    EMAIL_PATTERN,
    PHONE_PATTERN,
    HANDLE_PATTERN,
    DEVICE_ID_PATTERN,
    USERNAME_PATTERN,
)


def scrub_text(text: str) -> str:
    cleaned = text
    for pattern in PII_PATTERNS:
        cleaned = pattern.sub(REDACTED, cleaned)
    return cleaned


def scrub_payload(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, list):
        return [scrub_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: scrub_payload(item) for key, item in value.items()}
    return value


def contains_pii(text: str) -> bool:
    return any(pattern.search(text) for pattern in PII_PATTERNS)


def audit_value(value: Any, hits: list[str], path: str = "") -> None:
    if isinstance(value, str):
        if contains_pii(value):
            hits.append(path or "root")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            audit_value(item, hits, f"{path}.{key}" if path else str(key))
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            audit_value(item, hits, f"{path}[{index}]")
