"""Deterministic API integration-test snapshot."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import insert
from sqlalchemy.orm import Session

from db.models import (
    Analysis,
    Answer,
    FeedbackItem,
    FeedbackTheme,
    PipelineRun,
    Segment,
    Theme,
    UnmetNeed,
)

SEED_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def seed_id(label: str) -> uuid.UUID:
    return uuid.uuid5(SEED_NS, label)


RUN_ID = seed_id("pipeline-run")
THEME_STALE_ID = seed_id("theme:stale")
THEME_DISCOVERY_ID = seed_id("theme:discovery")
THEME_UI_ID = seed_id("theme:ui")

ITEM_KEYS = (
    "stale_1",
    "stale_2",
    "stale_3",
    "disc_1",
    "disc_2",
    "disc_3",
    "disc_4",
    "ui_1",
    "ui_2",
    "mixed_1",
    "mixed_2",
    "mixed_3",
)
ITEM_IDS = {key: seed_id(f"item:{key}") for key in ITEM_KEYS}

SEGMENT_IDS = {
    "power": seed_id("segment:power"),
    "casual": seed_id("segment:casual"),
    "new_user": seed_id("segment:new_user"),
}

NEED_IDS = {
    "fresh": seed_id("need:fresh"),
    "genre": seed_id("need:genre"),
    "offline": seed_id("need:offline"),
    "controls": seed_id("need:controls"),
}


def seed_api_snapshot(session: Session) -> PipelineRun:
    """Populate a DB with a complete analysis snapshot for API dev/tests."""
    completed_at = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    started_at = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)

    run = PipelineRun(
        id=RUN_ID,
        started_at=started_at,
        completed_at=completed_at,
        status="completed",
        config_snapshot={"type": "analysis", "stages": ["classify", "embed", "cluster"]},
        item_counts={"classify": {"status": "completed", "processed": 12}},
    )
    session.add(run)

    items = [
        FeedbackItem(
            id=ITEM_IDS["stale_1"],
            source="play_store",
            text="Discover Weekly keeps repeating the same artists every week.",
            rating=2,
            item_date=datetime(2026, 5, 10, tzinfo=UTC),
            content_hash="hash-stale-1",
        ),
        FeedbackItem(
            id=ITEM_IDS["stale_2"],
            source="play_store",
            text="Radio and autoplay feel stale after a few songs.",
            rating=2,
            item_date=datetime(2026, 5, 12, tzinfo=UTC),
            content_hash="hash-stale-2",
        ),
        FeedbackItem(
            id=ITEM_IDS["stale_3"],
            source="social",
            text="My home feed recommendations never surface anything new.",
            rating=None,
            item_date=datetime(2026, 5, 15, tzinfo=UTC),
            content_hash="hash-stale-3",
        ),
        FeedbackItem(
            id=ITEM_IDS["disc_1"],
            source="app_store",
            text="I want better ways to discover underground artists in my city.",
            rating=3,
            item_date=datetime(2026, 4, 20, tzinfo=UTC),
            content_hash="hash-disc-1",
        ),
        FeedbackItem(
            id=ITEM_IDS["disc_2"],
            source="reddit",
            text="Spotify shuffle hides new music and loops the same playlists.",
            rating=None,
            item_date=datetime(2026, 4, 22, tzinfo=UTC),
            content_hash="hash-disc-2",
        ),
        FeedbackItem(
            id=ITEM_IDS["disc_3"],
            source="play_store",
            text="Release Radar is useful but discovery still feels narrow.",
            rating=4,
            item_date=datetime(2026, 4, 25, tzinfo=UTC),
            content_hash="hash-disc-3",
        ),
        FeedbackItem(
            id=ITEM_IDS["disc_4"],
            source="social",
            text="I use external blogs because Spotify rarely surprises me.",
            rating=None,
            item_date=datetime(2026, 4, 28, tzinfo=UTC),
            content_hash="hash-disc-4",
        ),
        FeedbackItem(
            id=ITEM_IDS["ui_1"],
            source="app_store",
            text="The home screen is cluttered and hard to find fresh playlists.",
            rating=2,
            item_date=datetime(2026, 3, 5, tzinfo=UTC),
            content_hash="hash-ui-1",
        ),
        FeedbackItem(
            id=ITEM_IDS["ui_2"],
            source="play_store",
            text="Navigation to discovery features is buried behind too many taps.",
            rating=3,
            item_date=datetime(2026, 3, 8, tzinfo=UTC),
            content_hash="hash-ui-2",
        ),
        FeedbackItem(
            id=ITEM_IDS["mixed_1"],
            source="reddit",
            text="Great sound quality but recommendations ignore my eclectic taste.",
            rating=None,
            item_date=datetime(2026, 2, 1, tzinfo=UTC),
            content_hash="hash-mixed-1",
        ),
        FeedbackItem(
            id=ITEM_IDS["mixed_2"],
            source="social",
            text="Love the app overall yet discovery feels worse than last year.",
            rating=None,
            item_date=datetime(2026, 2, 10, tzinfo=UTC),
            content_hash="hash-mixed-2",
        ),
        FeedbackItem(
            id=ITEM_IDS["mixed_3"],
            source="play_store",
            text="Daily Mix is comforting but I rarely hear new artists.",
            rating=3,
            item_date=datetime(2026, 2, 15, tzinfo=UTC),
            content_hash="hash-mixed-3",
        ),
    ]
    session.add_all(items)

    analyses = [
        Analysis(
            feedback_item_id=ITEM_IDS["stale_1"],
            sentiment_label="negative",
            sentiment_score=0.15,
            intent="complaint",
            behavior_signals={"signals": ["repeat_listening"]},
            segment_hint="power_user",
            pipeline_run_id=RUN_ID,
        ),
        Analysis(
            feedback_item_id=ITEM_IDS["stale_2"],
            sentiment_label="negative",
            sentiment_score=0.2,
            intent="complaint",
            behavior_signals={"signals": ["autoplay"]},
            segment_hint="casual_listener",
            pipeline_run_id=RUN_ID,
        ),
        Analysis(
            feedback_item_id=ITEM_IDS["stale_3"],
            sentiment_label="negative",
            sentiment_score=0.25,
            intent="discovery_failure",
            behavior_signals={"signals": ["feed_browsing"]},
            segment_hint="casual_listener",
            pipeline_run_id=RUN_ID,
        ),
        Analysis(
            feedback_item_id=ITEM_IDS["disc_1"],
            sentiment_label="neutral",
            sentiment_score=0.5,
            intent="discovery_request",
            behavior_signals={"signals": ["local_discovery"]},
            segment_hint="power_user",
            pipeline_run_id=RUN_ID,
        ),
        Analysis(
            feedback_item_id=ITEM_IDS["disc_2"],
            sentiment_label="negative",
            sentiment_score=0.3,
            intent="discovery_failure",
            behavior_signals={"signals": ["shuffle"]},
            segment_hint="power_user",
            pipeline_run_id=RUN_ID,
        ),
        Analysis(
            feedback_item_id=ITEM_IDS["disc_3"],
            sentiment_label="positive",
            sentiment_score=0.7,
            intent="mixed_feedback",
            behavior_signals={"signals": ["release_radar"]},
            segment_hint="casual_listener",
            pipeline_run_id=RUN_ID,
        ),
        Analysis(
            feedback_item_id=ITEM_IDS["disc_4"],
            sentiment_label="negative",
            sentiment_score=0.35,
            intent="workaround",
            behavior_signals={"signals": ["external_discovery"]},
            segment_hint="power_user",
            pipeline_run_id=RUN_ID,
        ),
        Analysis(
            feedback_item_id=ITEM_IDS["ui_1"],
            sentiment_label="negative",
            sentiment_score=0.2,
            intent="ui_complaint",
            behavior_signals={"signals": ["home_screen"]},
            segment_hint="new_user",
            pipeline_run_id=RUN_ID,
        ),
        Analysis(
            feedback_item_id=ITEM_IDS["ui_2"],
            sentiment_label="neutral",
            sentiment_score=0.45,
            intent="ui_complaint",
            behavior_signals={"signals": ["navigation"]},
            segment_hint="new_user",
            pipeline_run_id=RUN_ID,
        ),
        Analysis(
            feedback_item_id=ITEM_IDS["mixed_1"],
            sentiment_label="neutral",
            sentiment_score=0.55,
            intent="mixed_feedback",
            behavior_signals={"signals": ["eclectic_taste"]},
            segment_hint="power_user",
            pipeline_run_id=RUN_ID,
        ),
        Analysis(
            feedback_item_id=ITEM_IDS["mixed_2"],
            sentiment_label="neutral",
            sentiment_score=0.5,
            intent="mixed_feedback",
            behavior_signals={"signals": ["year_over_year"]},
            segment_hint="casual_listener",
            pipeline_run_id=RUN_ID,
        ),
        Analysis(
            feedback_item_id=ITEM_IDS["mixed_3"],
            sentiment_label="neutral",
            sentiment_score=0.6,
            intent="comfort_listening",
            behavior_signals={"signals": ["daily_mix"]},
            segment_hint="casual_listener",
            pipeline_run_id=RUN_ID,
        ),
    ]
    session.add_all(analyses)
    session.flush()

    themes = [
        Theme(
            id=THEME_STALE_ID,
            name="Stale Recommendations",
            summary="Users report repetitive playlists and autoplay loops.",
            mention_volume=5,
            sentiment_score=0.28,
            cluster_id=0,
            representative_quote_ids=[
                str(ITEM_IDS["stale_1"]),
                str(ITEM_IDS["stale_2"]),
            ],
            source_breakdown={"play_store": 2, "social": 1, "reddit": 1, "app_store": 1},
            pipeline_run_id=RUN_ID,
        ),
        Theme(
            id=THEME_DISCOVERY_ID,
            name="Discovery Gaps",
            summary="Listeners want broader discovery beyond familiar artists.",
            mention_volume=4,
            sentiment_score=0.42,
            cluster_id=1,
            representative_quote_ids=[
                str(ITEM_IDS["disc_1"]),
                str(ITEM_IDS["disc_4"]),
            ],
            source_breakdown={"app_store": 1, "reddit": 1, "play_store": 1, "social": 1},
            pipeline_run_id=RUN_ID,
        ),
        Theme(
            id=THEME_UI_ID,
            name="Discovery UI Friction",
            summary="Discovery features are hard to find in the product UI.",
            mention_volume=2,
            sentiment_score=0.32,
            cluster_id=2,
            representative_quote_ids=[str(ITEM_IDS["ui_1"])],
            source_breakdown={"app_store": 1, "play_store": 1},
            pipeline_run_id=RUN_ID,
        ),
    ]
    session.add_all(themes)
    session.flush()

    theme_links = [
        (ITEM_IDS["stale_1"], THEME_STALE_ID),
        (ITEM_IDS["stale_2"], THEME_STALE_ID),
        (ITEM_IDS["stale_3"], THEME_STALE_ID),
        (ITEM_IDS["disc_2"], THEME_STALE_ID),
        (ITEM_IDS["mixed_3"], THEME_STALE_ID),
        (ITEM_IDS["disc_1"], THEME_DISCOVERY_ID),
        (ITEM_IDS["disc_2"], THEME_DISCOVERY_ID),
        (ITEM_IDS["disc_3"], THEME_DISCOVERY_ID),
        (ITEM_IDS["disc_4"], THEME_DISCOVERY_ID),
        (ITEM_IDS["ui_1"], THEME_UI_ID),
        (ITEM_IDS["ui_2"], THEME_UI_ID),
        (ITEM_IDS["mixed_1"], THEME_DISCOVERY_ID),
        (ITEM_IDS["mixed_2"], THEME_STALE_ID),
    ]
    session.execute(
        insert(FeedbackTheme),
        [
            {"feedback_item_id": item_id, "theme_id": theme_id}
            for item_id, theme_id in theme_links
        ],
    )

    answers = [
        Answer(
            question_id="Q1",
            answer_text=(
                "Users struggle because recommendations repeat and "
                "discovery surfaces are hard to find."
            ),
            evidence_ids=[str(ITEM_IDS["stale_1"]), str(ITEM_IDS["disc_1"])],
            confidence="high",
            source_breakdown={"play_store": 1, "app_store": 1},
            pipeline_run_id=RUN_ID,
        ),
        Answer(
            question_id="Q2",
            answer_text="The most common frustration is stale playlists and autoplay loops.",
            evidence_ids=[str(ITEM_IDS["stale_2"]), str(ITEM_IDS["stale_3"])],
            confidence="high",
            source_breakdown={"play_store": 1, "social": 1},
            pipeline_run_id=RUN_ID,
        ),
        Answer(
            question_id="Q3",
            answer_text=(
                "Listeners want exploration, local discovery, and "
                "comfort listening in the same sessions."
            ),
            evidence_ids=[str(ITEM_IDS["disc_1"]), str(ITEM_IDS["mixed_3"])],
            confidence="medium",
            source_breakdown={"app_store": 1, "play_store": 1},
            pipeline_run_id=RUN_ID,
        ),
        Answer(
            question_id="Q4",
            answer_text=(
                "Daily Mix and autoplay encourage repeat listening "
                "even when users want novelty."
            ),
            evidence_ids=[str(ITEM_IDS["mixed_3"]), str(ITEM_IDS["stale_2"])],
            confidence="medium",
            source_breakdown={"play_store": 2},
            pipeline_run_id=RUN_ID,
        ),
        Answer(
            question_id="Q5",
            answer_text=(
                "Power users report narrower discovery while "
                "new users struggle with navigation."
            ),
            evidence_ids=[str(ITEM_IDS["mixed_1"]), str(ITEM_IDS["ui_2"])],
            confidence="medium",
            source_breakdown={"reddit": 1, "play_store": 1},
            pipeline_run_id=RUN_ID,
        ),
        Answer(
            question_id="Q6",
            answer_text=(
                "Users want fresher recommendations, better genre breadth, "
                "and clearer discovery controls."
            ),
            evidence_ids=[str(ITEM_IDS["disc_4"]), str(ITEM_IDS["ui_1"])],
            confidence="high",
            source_breakdown={"social": 1, "app_store": 1},
            pipeline_run_id=RUN_ID,
        ),
    ]
    session.add_all(answers)

    segments = [
        Segment(
            id=SEGMENT_IDS["power"],
            label="Power listeners",
            top_frustration="Recommendations ignore eclectic taste",
            top_unmet_need="Broader underground discovery",
            top_behavior="Uses external blogs for new music",
            pipeline_run_id=RUN_ID,
        ),
        Segment(
            id=SEGMENT_IDS["casual"],
            label="Casual listeners",
            top_frustration="Autoplay feels repetitive",
            top_unmet_need="Easier surprise picks",
            top_behavior="Relies on Daily Mix for comfort",
            pipeline_run_id=RUN_ID,
        ),
        Segment(
            id=SEGMENT_IDS["new_user"],
            label="New subscribers",
            top_frustration="Discovery features are buried",
            top_unmet_need="Clearer onboarding to playlists",
            top_behavior="Browses home screen first",
            pipeline_run_id=RUN_ID,
        ),
    ]
    session.add_all(segments)

    needs = [
        UnmetNeed(
            id=NEED_IDS["fresh"],
            description="Fresher weekly recommendations",
            frequency=18,
            urgency_score=0.82,
            source_attribution={"play_store": 8, "social": 6, "reddit": 4},
            pipeline_run_id=RUN_ID,
        ),
        UnmetNeed(
            id=NEED_IDS["genre"],
            description="Better genre diversity in mixes",
            frequency=12,
            urgency_score=0.71,
            source_attribution={"reddit": 5, "app_store": 4, "social": 3},
            pipeline_run_id=RUN_ID,
        ),
        UnmetNeed(
            id=NEED_IDS["offline"],
            description="Offline discovery playlists",
            frequency=7,
            urgency_score=0.55,
            source_attribution={"play_store": 4, "app_store": 3},
            pipeline_run_id=RUN_ID,
        ),
        UnmetNeed(
            id=NEED_IDS["controls"],
            description="Explicit controls to reset recommendation taste",
            frequency=5,
            urgency_score=0.63,
            source_attribution={"social": 3, "reddit": 2},
            pipeline_run_id=RUN_ID,
        ),
    ]
    session.add_all(needs)

    session.commit()
    return run
