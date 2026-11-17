"""video frames and their derived (OCR) text

Revision ID: d6e2a9c4b1f8
Revises: b3d8e1f4a2c7
Create Date: 2026-11-17 21:00:00

"""

from typing import Sequence, Union

from alembic import op
import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d6e2a9c4b1f8"
down_revision: Union[str, Sequence[str], None] = "b3d8e1f4a2c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Yeni tablo; mevcut dokümanlara kare eklenmez (kareler yeni medya yüklemesinde çıkarılır)."""
    op.create_table(
        "video_frames",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("t_start", sa.Float(), nullable=False),
        sa.Column("t_end", sa.Float(), nullable=False),
        sa.Column("t_frame", sa.Float(), nullable=False),
        sa.Column("image_path", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("extractor", sa.String(length=200), nullable=False),
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=768), nullable=True),
        sa.Column("embedding_model", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('readable', 'partial', 'unreadable', 'no_text')",
            name="ck_video_frames_status",
        ),
        sa.CheckConstraint(
            "t_start <= t_frame AND t_frame <= t_end", name="ck_video_frames_time_order"
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "ordinal", name="uq_video_frames_document_ordinal"),
    )
    op.create_index("ix_video_frames_course_id", "video_frames", ["course_id"], unique=False)
    op.create_index(
        "ix_video_frames_document_id_t_start",
        "video_frames",
        ["document_id", "t_start"],
        unique=False,
    )
    op.create_index(
        "ix_video_frames_search_vector",
        "video_frames",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_video_frames_embedding_hnsw",
        "video_frames",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index(
        "ix_video_frames_embedding_hnsw",
        table_name="video_frames",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_index(
        "ix_video_frames_search_vector", table_name="video_frames", postgresql_using="gin"
    )
    op.drop_index("ix_video_frames_document_id_t_start", table_name="video_frames")
    op.drop_index("ix_video_frames_course_id", table_name="video_frames")
    op.drop_table("video_frames")
