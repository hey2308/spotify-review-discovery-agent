"""Add theme evidence and cluster metadata columns for Phase 2E/2F."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_theme_evidence"
down_revision: str | None = "002_cluster_assignments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("themes") as batch_op:
        batch_op.add_column(sa.Column("cluster_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "representative_quote_ids",
                postgresql.JSON(astext_type=sa.Text()),
                nullable=False,
                server_default="[]",
            )
        )
        batch_op.add_column(
            sa.Column("source_breakdown", postgresql.JSON(astext_type=sa.Text()), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("themes") as batch_op:
        batch_op.drop_column("source_breakdown")
        batch_op.drop_column("representative_quote_ids")
        batch_op.drop_column("cluster_id")
