"""Normalize DATABASE_URL values for SQLAlchemy + psycopg across environments."""

from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


def normalize_database_url(url: str) -> str:
    """Convert provider URLs (e.g. Render) to SQLAlchemy psycopg v3 form."""
    normalized = url.strip()
    if normalized.startswith("postgres://"):
        normalized = f"postgresql+psycopg://{normalized[len('postgres://'):]}"
    elif normalized.startswith("postgresql://"):
        normalized = f"postgresql+psycopg://{normalized[len('postgresql://'):]}"

    parsed = urlparse(normalized)
    if parsed.scheme.startswith("postgresql") and parsed.hostname and parsed.hostname.endswith(
        ".render.com"
    ):
        query = parse_qs(parsed.query)
        if "sslmode" not in query:
            query["sslmode"] = ["require"]
            normalized = urlunparse(parsed._replace(query=urlencode(query, doseq=True)))

    return normalized
