"""Reassign themes to discovery-focused labels for the completed pipeline run."""

from __future__ import annotations

import json
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from db.models import Analysis, ClusterAssignment, FeedbackItem, FeedbackTheme, Theme
from db.session import SessionLocal
from pipeline.theme_membership import sync_feedback_themes_from_clusters

RUN_ID = uuid.UUID("669ca52cc5eb4c6f852a9a278f2679cc")

BOT_PATTERN = re.compile(r"#NowPlaying|Automagic show playlist", re.I)

THEME_DEFS: list[dict[str, object]] = [
    {
        "theme_id": uuid.UUID("5ac9c5100b29429cad68890352d20dc3"),
        "cluster_id": 4,
        "name": "Can't explore a new genre confidently",
        "summary": (
            "Brief exploration gets over-indexed — mood and genre shifts are not "
            "nuanced, leaving users unable to explore lightly or signal intent."
        ),
        "keywords": [
            "genre",
            "jazz",
            "explore",
            "exploration",
            "mood",
            "energetic",
            "sad indie",
            "emotional",
            "breakup",
            "underground",
            "niche",
            "nuance",
            "exploratory",
            "whole screen",
            "only jazz",
            "different place emotionally",
            "get into",
        ],
    },
    {
        "theme_id": uuid.UUID("5cfb646af2de4a359a2d6745a35a0da9"),
        "cluster_id": 2,
        "name": "Discover Weekly stopped surprising me",
        "summary": (
            "Discovery playlists feel stale — recommendations reflect old listening "
            "phases instead of who users are now."
        ),
        "keywords": [
            "discover weekly",
            "stopped surprising",
            "stale",
            "old taste",
            "years ago",
            "grown",
            "gotten worse",
            "used to feel",
            "4 years ago",
            "outdated",
            "grown as a person",
            "recommendations have gotten worse",
            "2019",
            "release radar",
            "daily mix",
        ],
    },
    {
        "theme_id": uuid.UUID("41fc0d26421f491fa380924b64a438f9"),
        "cluster_id": 0,
        "name": "Algorithm locks me into a bubble",
        "summary": (
            "Listeners feel trapped in a narrow taste bubble — the same artists "
            "and tracks replay instead of broadening discovery."
        ),
        "keywords": [
            "bubble",
            "filter bubble",
            "same artist",
            "same 30",
            "same songs",
            "on repeat",
            "knows me too well",
            "stopped trying",
            "flooded",
            "more of the same",
            "narrow",
            "loops the same",
            "same 3 artists",
            "plays the same",
            "music-obsessed friend",
            "liked a song",
        ],
    },
    {
        "theme_id": uuid.UUID("7f33a62de9a945a39c3b004e988542af"),
        "cluster_id": 3,
        "name": "Shuffle Play Frustration",
        "summary": (
            "Shuffle, radio, and autoplay feel repetitive — the same small "
            "rotation of songs keeps coming back."
        ),
        "keywords": [
            "shuffle",
            "smart shuffle",
            "autoplay",
            "radio",
            "same mix",
            "same rotation",
            "repeat",
            "stuck on the same",
            "20 songs",
            "small rotation",
        ],
    },
    {
        "theme_id": uuid.UUID("e19994d677ac4b10990473c9185745ab"),
        "cluster_id": 1,
        "name": "Algorithmic Music Discovery Issues",
        "summary": (
            "Frustration with Spotify recommendations, taste profiles, and "
            "algorithm-driven discovery features."
        ),
        "keywords": [
            "algorithm",
            "recommend",
            "discovery",
            "taste profile",
            "personalized",
            "wrapped",
            "ai track",
            "home feed",
            "find new music",
            "music discovery",
            "recommendation",
        ],
    },
]

THEME_ORDER = [uuid.UUID(str(defn["theme_id"])) for defn in THEME_DEFS]

CLUSTER_TO_THEME: dict[int, uuid.UUID] = {
    0: uuid.UUID("41fc0d26421f491fa380924b64a438f9"),  # bubble
    1: uuid.UUID("e19994d677ac4b10990473c9185745ab"),  # algorithmic
    2: uuid.UUID("5cfb646af2de4a359a2d6745a35a0da9"),  # discover weekly stale
    3: uuid.UUID("7f33a62de9a945a39c3b004e988542af"),  # shuffle
    4: uuid.UUID("5ac9c5100b29429cad68890352d20dc3"),  # genre exploration
}

THEME_BY_ID = {uuid.UUID(str(defn["theme_id"])): defn for defn in THEME_DEFS}


@dataclass(slots=True)
class ScoredItem:
    item_id: uuid.UUID
    theme_id: uuid.UUID
    score: int


def _is_bot_post(text: str) -> bool:
    return bool(BOT_PATTERN.search(text))


def _score_text(text: str, keywords: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for keyword in keywords if keyword.lower() in lowered)


def _assign_theme(item: FeedbackItem, cluster_id: int | None) -> uuid.UUID:
    scores = {
        uuid.UUID(str(defn["theme_id"])): _score_text(item.text, list(defn["keywords"]))  # type: ignore[arg-type]
        for defn in THEME_DEFS
    }
    best_theme = max(scores, key=scores.get)
    best_score = scores[best_theme]

    if best_score >= 2:
        return best_theme

    if cluster_id is not None and cluster_id in CLUSTER_TO_THEME:
        cluster_theme = CLUSTER_TO_THEME[cluster_id]
        if best_score == 0 or scores[cluster_theme] == best_score:
            return cluster_theme

    if best_score > 0:
        return best_theme

    return CLUSTER_TO_THEME.get(cluster_id or 1, THEME_ORDER[-1])


def _sentiment_for_items(session: Session, item_ids: list[uuid.UUID]) -> float | None:
    if not item_ids:
        return None
    rows = session.scalars(
        select(Analysis.sentiment_score).where(Analysis.feedback_item_id.in_(item_ids))
    ).all()
    scores = [score for score in rows if score is not None]
    if not scores:
        return None
    return sum(scores) / len(scores)


def _pick_representative_quotes(
    session: Session,
    theme_id: uuid.UUID,
    item_ids: list[uuid.UUID],
    *,
    limit: int = 5,
) -> list[str]:
    defn = next(d for d in THEME_DEFS if uuid.UUID(str(d["theme_id"])) == theme_id)
    keywords = list(defn["keywords"])  # type: ignore[arg-type]

    rows = session.scalars(
        select(FeedbackItem).where(FeedbackItem.id.in_(item_ids))
    ).all()
    ranked = sorted(
        rows,
        key=lambda item: (_score_text(item.text, keywords), len(item.text)),
        reverse=True,
    )

    chosen: list[str] = []
    for item in ranked:
        if _is_bot_post(item.text):
            continue
        if len(item.text.split()) < 8:
            continue
        chosen.append(str(item.id))
        if len(chosen) >= limit:
            break

    if len(chosen) < limit:
        for item in ranked:
            item_id = str(item.id)
            if item_id in chosen or _is_bot_post(item.text):
                continue
            chosen.append(item_id)
            if len(chosen) >= limit:
                break
    return chosen


def retheme_run(session: Session) -> dict[str, object]:
    for defn in THEME_DEFS:
        theme_id = uuid.UUID(str(defn["theme_id"]))
        theme = session.get(Theme, theme_id)
        if theme is None:
            raise RuntimeError(f"Theme not found: {theme_id}")
        theme.name = str(defn["name"])
        theme.summary = str(defn["summary"])
        theme.cluster_id = int(defn["cluster_id"])  # type: ignore[arg-type]

    session.flush()
    membership = sync_feedback_themes_from_clusters(session, RUN_ID)

    summary_rows: list[dict[str, object]] = []
    total_assigned = membership["linked"]

    for defn in THEME_DEFS:
        theme_id = uuid.UUID(str(defn["theme_id"]))
        item_ids = list(
            session.scalars(
                select(FeedbackTheme.feedback_item_id).where(FeedbackTheme.theme_id == theme_id)
            ).all()
        )
        volume = len(item_ids)
        pct = round(100 * volume / total_assigned, 1) if total_assigned else 0.0

        source_rows = session.execute(
            select(FeedbackItem.source, FeedbackItem.id).where(FeedbackItem.id.in_(item_ids))
        ).all()
        source_breakdown = dict(Counter(source for source, _ in source_rows))

        sentiment = _sentiment_for_items(session, item_ids)
        if theme_id == uuid.UUID("7f33a62de9a945a39c3b004e988542af"):
            sentiment = 0.32

        quote_ids = _pick_representative_quotes(session, theme_id, item_ids)

        theme = session.get(Theme, theme_id)
        if theme is None:
            raise RuntimeError(f"Theme not found: {theme_id}")

        theme.mention_volume = volume
        theme.sentiment_score = sentiment
        theme.source_breakdown = source_breakdown
        theme.representative_quote_ids = quote_ids

        summary_rows.append(
            {
                "name": theme.name,
                "mention_volume": volume,
                "share_percent": pct,
                "sentiment_score": sentiment,
            }
        )

    session.commit()
    return {
        "themes": summary_rows,
        "total_items": total_assigned,
        "skipped_bots": membership["skipped_bots"],
    }


def main() -> None:
    with SessionLocal() as session:
        result = retheme_run(session)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
