"""practice rubric revisions: earlier versions of replaced rubrics (#15)

Revision ID: e4b7c2d9a1f6
Revises: c8e5a1f7d3b9
Create Date: 2026-11-18 12:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e4b7c2d9a1f6"
down_revision: Union[str, Sequence[str], None] = "c8e5a1f7d3b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "practice_rubric_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rubric_id", sa.Integer(), nullable=False),
        sa.Column("concept", sa.String(length=300), nullable=False),
        sa.Column("reference_answer", sa.Text(), nullable=False),
        sa.Column("criteria", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("replaced_by", sa.Integer(), nullable=True),
        sa.Column(
            "replaced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["rubric_id"], ["practice_rubrics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["replaced_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_practice_rubric_revisions_rubric_id", "practice_rubric_revisions", ["rubric_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_practice_rubric_revisions_rubric_id", table_name="practice_rubric_revisions")
    op.drop_table("practice_rubric_revisions")
