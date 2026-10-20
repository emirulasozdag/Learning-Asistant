"""ORM modelleri.

Sprint 1: Course, Document, Chunk, Conversation, Message. Kalan varlıklar (PracticeItem,
Rubric, Attempt, ClaimCheck, ...) ilgili özelliklerle eklenecek — docs/ANALYSIS.md §8.

Model değişince: `alembic revision --autogenerate -m "açıklama"`.
"""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# multilingual-e5-base çıktı boyutu.
EMBEDDING_DIM = 768


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    # "tr" | "en" — full-text aramada kullanılacak dil.
    language: Mapped[str] = mapped_column(String(2), default="tr")
    # Ders bilgisi (eğitmen girer; boş olabilir).
    instructor_name: Mapped[str | None] = mapped_column(String(200))
    term: Mapped[str | None] = mapped_column(String(64))
    # "undergraduate" | "graduate"
    level: Mapped[str | None] = mapped_column(String(16))
    department: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    # Ders izlencesi ve takvimi (OCW "Syllabus" / "Calendar"): HTML değil, yapılandırılmış veri.
    # Biçim: app.schemas.courses.SyllabusBlock listesi ve CourseCalendar.
    syllabus: Mapped[list | None] = mapped_column(JSONB)
    calendar: Mapped[dict | None] = mapped_column(JSONB)

    documents: Mapped[list["Document"]] = relationship(back_populates="course")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300))
    material_type: Mapped[str] = mapped_column(String(32))
    filename: Mapped[str] = mapped_column(String(300))
    file_path: Mapped[str] = mapped_column(String(500))
    page_count: Mapped[int] = mapped_column(default=0)
    # Yalnızca video: süre (saniye) ve harici, opak oynatma URL'si (yalnızca https kabul edilir).
    duration_s: Mapped[float | None]
    media_url: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    course: Mapped[Course] = relationship(back_populates="documents")
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="Chunk.ordinal"
    )


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_chunks_course_id", "course_id"),
        Index("ix_chunks_document_id_t_start", "document_id", "t_start"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    # Ders izolasyonu için tekrar tutulur: arama bu sütunla filtrelenir.
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    ordinal: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None]
    t_start: Mapped[float | None]
    t_end: Mapped[float | None]
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR)
    # multilingual-e5 vektörü (birim uzunlukta); anlamsal arama kosinüs mesafesiyle yapılır.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    # Vektörü üreten embedder'ın kimliği (`Embedder.identity`). Arama yalnızca etkin
    # embedder'la aynı kimlikteki vektörleri kullanır; None = kimliği bilinmeyen eski vektör.
    embedding_model: Mapped[str | None] = mapped_column(String(200))

    document: Mapped[Document] = relationship(back_populates="chunks")


class Conversation(Base):
    """Bir öğrencinin bir dersteki sohbeti; takip soruları için geçmiş tutulur."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.id"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    # "user" | "assistant"
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    # Asistan mesajı: alıntılanan chunk id'leri, ret durumu (değerlendirme ve hata analizi için).
    meta: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
