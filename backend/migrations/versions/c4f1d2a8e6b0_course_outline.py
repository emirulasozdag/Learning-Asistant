"""course outline: syllabus and calendar

Revision ID: c4f1d2a8e6b0
Revises: a1c4e7d93b52
Create Date: 2026-10-20 22:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c4f1d2a8e6b0"
down_revision: Union[str, Sequence[str], None] = "a1c4e7d93b52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ders izlencesi ve takvimi (yapılandırılmış JSON; boş olabilir)."""
    op.add_column("courses", sa.Column("syllabus", postgresql.JSONB(), nullable=True))
    op.add_column("courses", sa.Column("calendar", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("courses", "calendar")
    op.drop_column("courses", "syllabus")
