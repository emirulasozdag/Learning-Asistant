"""practice questions, rubrics and attempts

Revision ID: f2a7c3e9b104
Revises: f2a9d6c1b8e4
Create Date: 2026-10-21 00:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f2a7c3e9b104"
down_revision: Union[str, Sequence[str], None] = "f2a9d6c1b8e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Pratik sorusu, rubrik ve deneme (#15, CONTRACTS.md §2). Var olan veri etkilenmez."""
    op.create_table(
        "practice_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("chunk_id", sa.Integer(), nullable=False),
        sa.Column("requested_by", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("topic", sa.String(length=300), nullable=True),
        sa.Column("difficulty", sa.String(length=10), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("answer_key", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("checks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("generator_model", sa.String(length=100), nullable=True),
        sa.Column("follow_up_of_attempt_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('released', 'rejected')", name="ck_practice_status"),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_practice_questions_course_id", "practice_questions", ["course_id"])
    op.create_index("ix_practice_questions_chunk_id", "practice_questions", ["chunk_id"])

    op.create_table(
        "practice_rubrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=True),
        sa.Column("concept", sa.String(length=300), nullable=False),
        sa.Column("reference_answer", sa.Text(), nullable=False),
        sa.Column("criteria", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "source_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("approved", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["practice_questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_id"),
    )
    op.create_index("ix_practice_rubrics_course_id", "practice_rubrics", ["course_id"])

    op.create_table(
        "practice_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("selected_option", sa.Integer(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("max_score", sa.Float(), nullable=False),
        sa.Column("feedback", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("grader_model", sa.String(length=100), nullable=True),
        sa.Column("research_logged", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["question_id"], ["practice_questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_practice_attempts_question_id", "practice_attempts", ["question_id"])
    op.create_index("ix_practice_attempts_user_id", "practice_attempts", ["user_id"])

    # Döngüsel ilişki: takip sorusu, eksiklerine yöneldiği denemeyi gösterir.
    op.create_foreign_key(
        "fk_practice_questions_follow_up_attempt",
        "practice_questions",
        "practice_attempts",
        ["follow_up_of_attempt_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_practice_questions_follow_up_attempt", "practice_questions", type_="foreignkey"
    )
    op.drop_index("ix_practice_attempts_user_id", table_name="practice_attempts")
    op.drop_index("ix_practice_attempts_question_id", table_name="practice_attempts")
    op.drop_table("practice_attempts")
    op.drop_index("ix_practice_rubrics_course_id", table_name="practice_rubrics")
    op.drop_table("practice_rubrics")
    op.drop_index("ix_practice_questions_chunk_id", table_name="practice_questions")
    op.drop_index("ix_practice_questions_course_id", table_name="practice_questions")
    op.drop_table("practice_questions")
