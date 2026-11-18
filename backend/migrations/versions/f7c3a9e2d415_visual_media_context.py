"""visual media context: media identity, frame descriptions and frame job kinds (#25)

Revision ID: f7c3a9e2d415
Revises: b5d8e2f4a7c1
Create Date: 2026-11-18 23:00:00

Var olan satırlar değişmez: eski medya yüklemelerinin özeti bilinmez (boş kalır), kareler
yorumlanmamış sayılır. Var olan işler `transcription` ya da `frames` (#27) türündedir; kısıt
ikisini de kabul eder.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f7c3a9e2d415"
down_revision: Union[str, Sequence[str], None] = "b5d8e2f4a7c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("media_sha256", sa.String(length=64), nullable=True))
    op.add_column("video_frames", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "video_frames", sa.Column("description_model", sa.String(length=200), nullable=True)
    )
    op.create_check_constraint(
        "ck_processing_jobs_kind",
        "processing_jobs",
        "kind IN ('transcription', 'frames', 'frame_interpretation')",
    )


def downgrade() -> None:
    # Yalnızca bu sürümün getirdiği tür eski kodda çalıştırılamaz; `transcription` ve `frames` (#27)
    # işleri korunur. Önceki şemada tür kısıtı yoktu: kısıt kaldırılınca önceki hâle döner.
    op.execute("DELETE FROM processing_jobs WHERE kind = 'frame_interpretation'")
    op.drop_constraint("ck_processing_jobs_kind", "processing_jobs", type_="check")
    op.drop_column("video_frames", "description_model")
    op.drop_column("video_frames", "description")
    op.drop_column("documents", "media_sha256")
