"""video documents: duration, media url, chunk time index

Revision ID: a1c4e7d93b52
Revises: 5d2e8f1a9c37
Create Date: 2026-10-21 10:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1c4e7d93b52"
down_revision: Union[str, Sequence[str], None] = "5d2e8f1a9c37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Video dokümanı: süre ve harici oynatma URL'si (ikisi de boş olabilir); parça zaman indeksi."""
    op.add_column("documents", sa.Column("duration_s", sa.Float(), nullable=True))
    op.add_column("documents", sa.Column("media_url", sa.String(length=1000), nullable=True))
    op.create_index("ix_chunks_document_id_t_start", "chunks", ["document_id", "t_start"])


def downgrade() -> None:
    op.drop_index("ix_chunks_document_id_t_start", table_name="chunks")
    op.drop_column("documents", "media_url")
    op.drop_column("documents", "duration_s")
