"""merge heads: course outline and users/enrollments

Revision ID: e7b2c9d4f1a3
Revises: c4f1d2a8e6b0, a3f1c7d92e58
Create Date: 2026-10-20 23:30:00

İki dal aynı anda a1c4e7d93b52'den ayrıldı (izlence/takvim ve kimlik/üyelik). Bu migration
yalnızca iki başı birleştirir; şema değişikliği yoktur.
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "e7b2c9d4f1a3"
down_revision: Union[str, Sequence[str], None] = ("c4f1d2a8e6b0", "a3f1c7d92e58")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
