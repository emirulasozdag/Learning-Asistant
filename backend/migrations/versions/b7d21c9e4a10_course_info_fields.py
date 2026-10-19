"""course info fields

Revision ID: b7d21c9e4a10
Revises: 4c9b7447c92d
Create Date: 2026-10-20 12:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b7d21c9e4a10"
down_revision: Union[str, Sequence[str], None] = "4c9b7447c92d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ders bilgisi: eğitmen, dönem, seviye, bölüm, açıklama (hepsi boş olabilir)."""
    op.add_column("courses", sa.Column("instructor_name", sa.String(length=200), nullable=True))
    op.add_column("courses", sa.Column("term", sa.String(length=64), nullable=True))
    op.add_column("courses", sa.Column("level", sa.String(length=16), nullable=True))
    op.add_column("courses", sa.Column("department", sa.String(length=200), nullable=True))
    op.add_column("courses", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    for column in ("description", "department", "level", "term", "instructor_name"):
        op.drop_column("courses", column)
