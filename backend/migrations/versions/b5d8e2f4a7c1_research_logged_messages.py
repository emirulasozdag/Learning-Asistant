"""research_logged on messages and practice questions (#104)

Revision ID: b5d8e2f4a7c1
Revises: e4b7c2d9a1f6
Create Date: 2026-11-18 20:00:00

Var olan satırlar araştırma kaydı dışı sayılır (false): onayın o anda verildiği bilinemez.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b5d8e2f4a7c1"
down_revision: Union[str, Sequence[str], None] = "e4b7c2d9a1f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("research_logged", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "practice_questions",
        sa.Column("research_logged", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("practice_questions", "research_logged")
    op.drop_column("messages", "research_logged")
