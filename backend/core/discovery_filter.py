"""Discovery / recommendation relevance helpers for quote filtering."""

from __future__ import annotations

import re

DISCOVERY_TEXT_TERMS = (
    "discover",
    "recommend",
    "playlist",
    "algorithm",
    "shuffle",
    "radio",
    "autoplay",
    "stale",
    "repetitive",
    "repeat",
    "new music",
    "new artist",
    "find music",
    "discover weekly",
    "release radar",
    "daily mix",
    "spotify wrapped",
)

DISCOVERY_KEYWORD_PATTERN = re.compile(
    r"\b("
    r"discover\w*|recommend\w*|playlist|algorithm|radio|shuffle|"
    r"new music|new artists?|find music|stale|repetitive|repeat(?:ing|s)?|"
    r"discover weekly|release radar|daily mix|spotify wrapped|autoplay"
    r")\b",
    re.IGNORECASE,
)


def text_mentions_discovery(text: str) -> bool:
    return bool(DISCOVERY_KEYWORD_PATTERN.search(text))


def sql_discovery_inclusion_clauses(*, text_column, intent_column, behavior_signals_column):
    """SQLAlchemy OR clause: quote is discovery/recommendation related."""
    from sqlalchemy import String, cast, or_

    text_clauses = [text_column.ilike(f"%{term}%") for term in DISCOVERY_TEXT_TERMS]
    classification_clauses = [
        intent_column == "discover_new_music",
        intent_column.ilike("%discover%"),
        intent_column.ilike("%recommend%"),
    ]

    signals_text = cast(behavior_signals_column, String)
    classification_clauses.extend(
        [
            signals_text.ilike("%discovery%"),
            signals_text.ilike("%recommend%"),
        ]
    )

    return or_(*classification_clauses, *text_clauses)
