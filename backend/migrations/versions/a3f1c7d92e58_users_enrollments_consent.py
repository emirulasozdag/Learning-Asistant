"""users, sessions, enrollments, consent and approval fields

Revision ID: a3f1c7d92e58
Revises: a1c4e7d93b52
Create Date: 2026-10-20 21:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a3f1c7d92e58"
down_revision: Union[str, Sequence[str], None] = "a1c4e7d93b52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Kimlik, ders üyeliği, onay ve materyal onayı (DECISIONS.md ADR-1..4, issue #11).

    Var olan veriler:
    - Sohbetlerin sahibi bilinmez; `user_id` boş kalır ve bu sohbetlere kimse erişemez.
    - Dokümanlar hesaplardan önce ekip tarafından onaylı materyal olarak yüklendi: `approved_at`
      yükleme zamanıyla doldurulur, `approved_by` boş kalır.
    - Var olan derslere rastgele katılım kodu verilir (eğitmen yeniler).
    """
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=True),
        sa.Column("can_create_courses", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("policy_version", sa.String(length=32), nullable=True),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("research_logging", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)
    op.create_table(
        "enrollments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('student', 'instructor', 'ta')", name="ck_enrollments_role"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "course_id"),
    )
    op.create_index(op.f("ix_enrollments_course_id"), "enrollments", ["course_id"], unique=False)
    op.create_index(op.f("ix_enrollments_user_id"), "enrollments", ["user_id"], unique=False)

    op.add_column("courses", sa.Column("join_code", sa.String(length=32), nullable=True))
    op.add_column(
        "courses", sa.Column("join_code_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_unique_constraint("uq_courses_join_code", "courses", ["join_code"])
    op.execute(
        "UPDATE courses SET join_code = upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 10)), "
        "join_code_expires_at = now() + interval '120 days' WHERE join_code IS NULL"
    )

    op.add_column("documents", sa.Column("approved_by", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_documents_approved_by_users",
        "documents",
        "users",
        ["approved_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute("UPDATE documents SET approved_at = created_at WHERE approved_at IS NULL")

    op.add_column("conversations", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_conversations_user_id"), "conversations", ["user_id"], unique=False)
    op.create_foreign_key(
        "fk_conversations_user_id_users",
        "conversations",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_conversations_user_id_users", "conversations", type_="foreignkey")
    op.drop_index(op.f("ix_conversations_user_id"), table_name="conversations")
    op.drop_column("conversations", "user_id")
    op.drop_constraint("fk_documents_approved_by_users", "documents", type_="foreignkey")
    op.drop_column("documents", "approved_at")
    op.drop_column("documents", "approved_by")
    op.drop_constraint("uq_courses_join_code", "courses", type_="unique")
    op.drop_column("courses", "join_code_expires_at")
    op.drop_column("courses", "join_code")
    op.drop_index(op.f("ix_enrollments_user_id"), table_name="enrollments")
    op.drop_index(op.f("ix_enrollments_course_id"), table_name="enrollments")
    op.drop_table("enrollments")
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("users")
