"""Add cluster_assignments table for Phase 2D intermediate theme clustering."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_cluster_assignments"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cluster_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feedback_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cluster_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["feedback_item_id"], ["feedback_items.id"]),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "feedback_item_id",
            "pipeline_run_id",
            name="uq_cluster_assignment_item_run",
        ),
    )
    op.create_index(
        "ix_cluster_assignments_feedback_item_id",
        "cluster_assignments",
        ["feedback_item_id"],
        unique=False,
    )
    op.create_index(
        "ix_cluster_assignments_pipeline_run_id",
        "cluster_assignments",
        ["pipeline_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_cluster_assignments_pipeline_run_id", table_name="cluster_assignments")
    op.drop_index("ix_cluster_assignments_feedback_item_id", table_name="cluster_assignments")
    op.drop_table("cluster_assignments")
