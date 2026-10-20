"""document status/error and transcript source (local transcription)

Revision ID: f2a9d6c1b8e4
Revises: e7b2c9d4f1a3
Create Date: 2026-10-22 10:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f2a9d6c1b8e4"
down_revision: Union[str, Sequence[str], None] = "e7b2c9d4f1a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Mevcut dokümanlar 'ready'; .vtt videoları transcript_source='vtt' olur."""
    op.add_column(
        "documents",
        sa.Column("status", sa.String(length=16), server_default="ready", nullable=False),
    )
    op.add_column("documents", sa.Column("error", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("transcript_source", sa.String(length=8), nullable=True))
    op.add_column("documents", sa.Column("transcript_model", sa.String(length=200), nullable=True))
    op.execute("UPDATE documents SET transcript_source = 'vtt' WHERE material_type = 'video'")


def downgrade() -> None:
    op.drop_column("documents", "transcript_model")
    op.drop_column("documents", "transcript_source")
    op.drop_column("documents", "error")
    op.drop_column("documents", "status")
