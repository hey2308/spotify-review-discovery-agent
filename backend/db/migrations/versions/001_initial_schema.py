"""Initial schema v1 — all core tables per architecture.md §3.2."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("config_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("item_counts", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "raw_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("payload", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_raw_documents_source", "raw_documents", ["source"], unique=False)

    op.create_table(
        "feedback_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("item_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["raw_document_id"], ["raw_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "content_hash", name="uq_feedback_source_hash"),
    )
    op.create_index("ix_feedback_items_source", "feedback_items", ["source"], unique=False)
    op.create_index("ix_feedback_items_item_date", "feedback_items", ["item_date"], unique=False)
    op.create_index(
        "ix_feedback_items_content_hash", "feedback_items", ["content_hash"], unique=False
    )

    op.create_table(
        "themes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("mention_volume", sa.Integer(), nullable=False),
        sa.Column("sentiment_score", sa.Float(), nullable=True),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_themes_pipeline_run_id", "themes", ["pipeline_run_id"], unique=False)

    op.create_table(
        "feedback_themes",
        sa.Column("feedback_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("theme_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["feedback_item_id"], ["feedback_items.id"]),
        sa.ForeignKeyConstraint(["theme_id"], ["themes.id"]),
        sa.PrimaryKeyConstraint("feedback_item_id", "theme_id"),
    )

    op.create_table(
        "segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("top_frustration", sa.Text(), nullable=True),
        sa.Column("top_unmet_need", sa.Text(), nullable=True),
        sa.Column("top_behavior", sa.Text(), nullable=True),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_segments_pipeline_run_id", "segments", ["pipeline_run_id"], unique=False)

    op.create_table(
        "analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feedback_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sentiment_label", sa.String(length=16), nullable=True),
        sa.Column("sentiment_score", sa.Float(), nullable=True),
        sa.Column("intent", sa.String(length=128), nullable=True),
        sa.Column("behavior_signals", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("segment_hint", sa.String(length=128), nullable=True),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["feedback_item_id"], ["feedback_items.id"]),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feedback_item_id"),
    )
    op.create_index("ix_analyses_feedback_item_id", "analyses", ["feedback_item_id"], unique=False)
    op.create_index("ix_analyses_pipeline_run_id", "analyses", ["pipeline_run_id"], unique=False)

    op.create_table(
        "answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", sa.String(length=8), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("evidence_ids", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.String(length=32), nullable=True),
        sa.Column("source_breakdown", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_id", "pipeline_run_id", name="uq_answer_question_run"),
    )
    op.create_index("ix_answers_question_id", "answers", ["question_id"], unique=False)
    op.create_index("ix_answers_pipeline_run_id", "answers", ["pipeline_run_id"], unique=False)

    op.create_table(
        "unmet_needs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("frequency", sa.Integer(), nullable=False),
        sa.Column("urgency_score", sa.Float(), nullable=True),
        sa.Column("source_attribution", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_unmet_needs_pipeline_run_id", "unmet_needs", ["pipeline_run_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_unmet_needs_pipeline_run_id", table_name="unmet_needs")
    op.drop_table("unmet_needs")
    op.drop_index("ix_answers_pipeline_run_id", table_name="answers")
    op.drop_index("ix_answers_question_id", table_name="answers")
    op.drop_table("answers")
    op.drop_index("ix_analyses_pipeline_run_id", table_name="analyses")
    op.drop_index("ix_analyses_feedback_item_id", table_name="analyses")
    op.drop_table("analyses")
    op.drop_index("ix_segments_pipeline_run_id", table_name="segments")
    op.drop_table("segments")
    op.drop_table("feedback_themes")
    op.drop_index("ix_themes_pipeline_run_id", table_name="themes")
    op.drop_table("themes")
    op.drop_index("ix_feedback_items_content_hash", table_name="feedback_items")
    op.drop_index("ix_feedback_items_item_date", table_name="feedback_items")
    op.drop_index("ix_feedback_items_source", table_name="feedback_items")
    op.drop_table("feedback_items")
    op.drop_index("ix_raw_documents_source", table_name="raw_documents")
    op.drop_table("raw_documents")
    op.drop_table("pipeline_runs")
