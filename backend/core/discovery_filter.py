"""Discovery / recommendation relevance helpers for quote filtering."""

from __future__ import annotations

import re

RECOMMENDATION_INTENTS = (
    "discover_new_music",
    "discovery_frustration",
    "fix_recommendation_frustration",
    "discovery/recommendation frustration",
    "discovery_mode_frustration",
    "discovery_request",
    "discovery_failure",
)

# Product/feature phrases that alone indicate recommendation feedback.
STRONG_RECOMMENDATION_TEXT_TERMS = (
    "discover weekly",
    "release radar",
    "daily mix",
    "spotify wrapped",
    "recommendation",
    "recommendations",
    "recommended",
    "algorithm",
    "new music",
    "new artist",
    "find music",
    "find new music",
)

RECOMMENDATION_TEXT_TERMS = (
    "recommend",
    "discover",
    "stale",
    "repetitive",
    "same artist",
    "same song",
    "autoplay",
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


def sql_strict_recommendation_clauses(*, text_column, intent_column, behavior_signals_column):
    """Quote must mention recommendations and be classified or explicitly feature-related."""
    from sqlalchemy import String, and_, cast, or_

    strong_text = or_(
        *[text_column.ilike(f"%{term}%") for term in STRONG_RECOMMENDATION_TEXT_TERMS]
    )
    general_text = or_(
        *[text_column.ilike(f"%{term}%") for term in RECOMMENDATION_TEXT_TERMS]
    )
    signals_text = cast(behavior_signals_column, String)
    classified = or_(
        intent_column.in_(RECOMMENDATION_INTENTS),
        intent_column.ilike("%discover%"),
        intent_column.ilike("%recommend%"),
        signals_text.ilike("%discovery%"),
        signals_text.ilike("%recommend%"),
    )

    return or_(strong_text, and_(classified, general_text))


def sql_recommendation_priority(*, intent_column, text_column):
    """Lower value = higher recommendation relevance (for ORDER BY)."""
    from sqlalchemy import case

    return case(
        (
            intent_column.in_(
                (
                    "fix_recommendation_frustration",
                    "discovery_frustration",
                    "discovery/recommendation frustration",
                    "discovery_mode_frustration",
                )
            ),
            0,
        ),
        (intent_column == "discover_new_music", 1),
        (intent_column.in_(("discovery_request", "discovery_failure")), 2),
        (intent_column.ilike("%recommend%"), 3),
        (intent_column.ilike("%discover%"), 4),
        (text_column.ilike("%discover weekly%"), 5),
        (text_column.ilike("%release radar%"), 6),
        (text_column.ilike("%algorithm%"), 7),
        else_=8,
    )
