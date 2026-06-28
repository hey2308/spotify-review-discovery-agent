"""Discovery / recommendation relevance helpers for quote filtering."""

from __future__ import annotations

import re

# Intents produced by the classifier that are explicitly about discovery/recommendations.
DISCOVERY_INTENTS = (
    "discover_new_music",
    "discovery_frustration",
    "fix_recommendation_frustration",
    "discovery/recommendation frustration",
    "discovery_mode_frustration",
    "discovery",
    "avoid_discovery",
)

# Text fallbacks when classification is missing — avoid generic terms like "playlist"
# or "radio" that appear in most music-app reviews.
DISCOVERY_TEXT_TERMS = (
    "discover",
    "recommend",
    "algorithm",
    "autoplay",
    "stale",
    "repetitive",
    "same artist",
    "same song",
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
    r"discover\w*|recommend\w*|algorithm|autoplay|"
    r"new music|new artists?|find music|stale|repetitive|"
    r"same artists?|same songs?|"
    r"discover weekly|release radar|daily mix|spotify wrapped"
    r")\b",
    re.IGNORECASE,
)


def text_mentions_discovery(text: str) -> bool:
    return bool(DISCOVERY_KEYWORD_PATTERN.search(text))


def sql_discovery_inclusion_clauses(*, text_column, intent_column, behavior_signals_column):
    """SQLAlchemy OR clause: quote is discovery/recommendation related."""
    from sqlalchemy import String, cast, or_

    text_clauses = [text_column.ilike(f"%{term}%") for term in DISCOVERY_TEXT_TERMS]
    signals_text = cast(behavior_signals_column, String)

    classification_clauses = [
        intent_column.in_(DISCOVERY_INTENTS),
        intent_column.ilike("%discover%"),
        intent_column.ilike("%recommend%"),
        signals_text.ilike("%discovery%"),
        signals_text.ilike("%recommend%"),
    ]

    return or_(*classification_clauses, *text_clauses)


def sql_discovery_priority(*, intent_column):
    """Lower value = higher discovery relevance (for ORDER BY)."""
    from sqlalchemy import case

    return case(
        (intent_column == "discover_new_music", 0),
        (intent_column.in_(DISCOVERY_INTENTS), 1),
        (intent_column.ilike("%discover%"), 2),
        (intent_column.ilike("%recommend%"), 3),
        else_=4,
    )
