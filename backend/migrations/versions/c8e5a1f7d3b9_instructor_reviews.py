"""instructor reviews and withdrawn practice questions (#20)

Revision ID: c8e5a1f7d3b9
Revises: b3d8e1f4a2c7
Create Date: 2026-11-17 23:30:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c8e5a1f7d3b9"
down_revision: Union[str, Sequence[str], None] = "b3d8e1f4a2c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_practice_status", "practice_questions", type_="check")
    op.create_check_constraint(
        "ck_practice_status",
        "practice_questions",
        "status IN ('released', 'rejected', 'withdrawn')",
    )
    op.create_table(
        "instructor_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(length=16), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("question_id", sa.Integer(), nullable=True),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("correction", sa.Text(), nullable=True),
        sa.Column("reviewer_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "target_type IN ('message', 'practice_item')",
            name="ck_instructor_reviews_target_type",
        ),
        sa.CheckConstraint(
            "decision IN ('approve', 'correct')", name="ck_instructor_reviews_decision"
        ),
        sa.CheckConstraint(
            "(target_type = 'message' AND message_id IS NOT NULL AND question_id IS NULL)"
            " OR (target_type = 'practice_item' AND question_id IS NOT NULL"
            " AND message_id IS NULL)",
            name="ck_instructor_reviews_one_target",
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["practice_questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_instructor_reviews_course_id", "instructor_reviews", ["course_id"])
    op.create_index("ix_instructor_reviews_message_id", "instructor_reviews", ["message_id"])
    op.create_index("ix_instructor_reviews_question_id", "instructor_reviews", ["question_id"])


def downgrade() -> None:
    op.drop_index("ix_instructor_reviews_question_id", table_name="instructor_reviews")
    op.drop_index("ix_instructor_reviews_message_id", table_name="instructor_reviews")
    op.drop_index("ix_instructor_reviews_course_id", table_name="instructor_reviews")
    op.drop_table("instructor_reviews")
    op.execute("UPDATE practice_questions SET status = 'rejected' WHERE status = 'withdrawn'")
    op.drop_constraint("ck_practice_status", "practice_questions", type_="check")
    op.create_check_constraint(
        "ck_practice_status", "practice_questions", "status IN ('released', 'rejected')"
    )
