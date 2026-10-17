"""ORM modelleri — WP3'te eklenecek.

Planlanan varlıklar (docs/ANALYSIS.md §8): Course, User, Enrollment, Document, Chunk
(embedding vector(768) + tsvector), Conversation, Message, PracticeItem, Rubric, Attempt,
Claim / ClaimCheck, InstructorReview, EvalRun.

Yeni bir model eklendiğinde bu modülde tanımlanır ve
`alembic revision --autogenerate -m "..."` ile migration üretilir.
"""

from app.db.base import Base

__all__ = ["Base"]
