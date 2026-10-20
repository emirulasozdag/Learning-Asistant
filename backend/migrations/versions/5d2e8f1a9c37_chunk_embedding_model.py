"""chunk embedding model identity

Revision ID: 5d2e8f1a9c37
Revises: b7d21c9e4a10
Create Date: 2026-10-20 19:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "5d2e8f1a9c37"
down_revision: Union[str, Sequence[str], None] = "b7d21c9e4a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Her vektörün hangi embedder'la üretildiği.

    Var olan vektörlerin kimliği bilinmez (e5 de olabilir, testlerin sahte vektörü de) ve
    boş kalır; anlamsal arama bunları kullanmaz. `python -m app.scripts.reembed` ile
    etkin embedder'la yeniden üretilir.
    """
    op.add_column("chunks", sa.Column("embedding_model", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("chunks", "embedding_model")
