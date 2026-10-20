"""ORM modelleri.

Sprint 1: Course, Document, Chunk, Conversation, Message. #11: User, AuthSession, Enrollment
(DECISIONS.md ADR-1, 2, 4). #15: PracticeQuestion, PracticeRubric, PracticeAttempt. Kalan
varlıklar (ClaimCheck, InstructorReview, ...) ilgili özelliklerle eklenecek — docs/ANALYSIS.md §8.

Model değişince: `alembic revision --autogenerate -m "açıklama"`.
"""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# multilingual-e5-base çıktı boyutu.
EMBEDDING_DIM = 768


class User(Base):
    """Hesap (ADR-1). Rol kullanıcıda değil, ders üyeliğindedir (`Enrollment`)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    # Küçük harfe çevrilmiş olarak saklanır.
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(100))
    # Ders açabilir mi (açınca o dersin eğitmeni olur). Kayıtla alınamaz: seed ya da
    # `python -m app.scripts.create_instructor` ile verilir (ADR-1).
    can_create_courses: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Aydınlatma metni (ADR-4): kabul edilen sürüm ve zamanı; None = henüz kabul edilmedi.
    policy_version: Mapped[str | None] = mapped_column(String(32))
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Araştırma/analiz kaydı için ayrı opt-in; varsayılan kapalı.
    research_logging: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthSession(Base):
    """Sunucu tarafı oturum. Çerezde rastgele belirteç durur, burada yalnızca SHA-256 özeti."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Enrollment(Base):
    """Ders üyeliği (ADR-2). Yetki yalnızca buradan gelir; satır silinince erişim biter."""

    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id"),
        CheckConstraint("role IN ('student', 'instructor', 'ta')", name="ck_enrollments_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    # "student" | "instructor" | "ta"
    role: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
    # Katılım kodu (ADR-2); eğitmen yeniler. Süresi dolmuşsa ya da yoksa kodla katılınamaz.
    join_code: Mapped[str | None] = mapped_column(String(32), unique=True)
    join_code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    # ADR-3: yükleyen eğitmen ve beyan zamanı. Arama yalnızca onaylı dokümanlarda yapılır.
    # Hesaplardan önce yüklenenler için approved_by boştur.
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # İşlem durumu: processing (transkripsiyon sürüyor) | ready | failed. Yalnızca ready
    # dokümanlar öğrencilere görünür ve aramaya girer. `error`: failed için Türkçe kısa neden.
    status: Mapped[str] = mapped_column(String(16), server_default="ready")
    error: Mapped[str | None] = mapped_column(Text)
    # Video transkriptinin kaynağı: "vtt" (yüklenen altyazı) | "asr" (yerel transkripsiyon) ve
    # asr için model kimliği (ör. faster-whisper/large-v3-turbo/int8). Diğer dokümanlarda boş.
    transcript_source: Mapped[str | None] = mapped_column(String(8))
    transcript_model: Mapped[str | None] = mapped_column(String(200))

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
    """Bir kullanıcının bir dersteki sohbeti; takip soruları için geçmiş tutulur.

    Yalnızca sahibi devam ettirebilir. Hesaplardan önceki sohbetlerde user_id boştur ve
    kimse erişemez.
    """

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
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


class PracticeQuestion(Base):
    """Kaynak pasaja bağlı pratik sorusu (#15, #16; CONTRACTS.md §2).

    Kontrolden geçmeyen sorular da `status="rejected"` olarak saklanır (kabul oranı ölçümü);
    öğrenciye yalnızca `released` sorular gösterilir. `answer_key` ve `explanation` öğrenci
    cevap vermeden hiçbir yanıtta dönmez.
    """

    __tablename__ = "practice_questions"
    __table_args__ = (
        CheckConstraint("status IN ('released', 'rejected')", name="ck_practice_status"),
        Index("ix_practice_questions_course_id", "course_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    # Sorunun dayandığı ders parçası; doküman silinirse soru da silinir.
    chunk_id: Mapped[int] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"), index=True)
    # İsteyen kullanıcı (tutor sohbetinden ya da pratik ekranından); hesap silinirse boşalır.
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # "mcq" | "short_answer" | "code_tracing"
    type: Mapped[str] = mapped_column(String(20))
    topic: Mapped[str | None] = mapped_column(String(300))
    # "easy" | "medium" | "hard"
    difficulty: Mapped[str] = mapped_column(String(10))
    prompt: Mapped[str] = mapped_column(Text)
    options: Mapped[list | None] = mapped_column(JSONB)
    # Gizli: {"correct_option": int} (mcq) ya da {"reference_answer": str}.
    answer_key: Mapped[dict] = mapped_column(JSONB)
    explanation: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    # Otomatik kontrollerin sonuçları: [{"name", "passed", "detail"}].
    checks: Mapped[list] = mapped_column(JSONB)
    generator_model: Mapped[str | None] = mapped_column(String(100))
    # Bu soru bir denemenin eksiklerine yönelik takip sorusuysa o deneme.
    follow_up_of_attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "practice_attempts.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_practice_questions_follow_up_attempt",
        )
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chunk: Mapped[Chunk] = relationship()
    rubric: Mapped["PracticeRubric | None"] = relationship(
        back_populates="question", cascade="all, delete-orphan", uselist=False
    )


class PracticeRubric(Base):
    """Bir sorunun (ya da kavramın) referans cevabı ve rubriği (#15; CONTRACTS.md §2).

    Üretilen soruların rubriği soruyla birlikte üretilir (`origin="generated"`, onaysız);
    eğitmen girdiği ya da onayladığı rubrik `approved=True` taşır. Öğrenciye gösterilmez.
    """

    __tablename__ = "practice_rubrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int | None] = mapped_column(
        ForeignKey("practice_questions.id", ondelete="CASCADE"), unique=True
    )
    concept: Mapped[str] = mapped_column(String(300))
    reference_answer: Mapped[str] = mapped_column(Text)
    # [{"description": str, "points": float}]
    criteria: Mapped[list] = mapped_column(JSONB)
    source_ids: Mapped[list] = mapped_column(JSONB, server_default="[]")
    # "generated" | "instructor"
    origin: Mapped[str] = mapped_column(String(16))
    approved: Mapped[bool] = mapped_column(Boolean, server_default="false")
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    question: Mapped[PracticeQuestion | None] = relationship(back_populates="rubric")


class PracticeAttempt(Base):
    """Öğrencinin bir soruya cevabı ve aldığı formatif geri bildirim (resmî not değildir).

    Öğrencinin kendi pratiği için saklanır (geri bildirim, takip sorusu). Öğrenme kaydına ve
    eğitmen analitiğine yalnızca `research_logged` olanlar girer (ADR-4: cevap anındaki onay).
    """

    __tablename__ = "practice_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("practice_questions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    answer_text: Mapped[str | None] = mapped_column(Text)
    selected_option: Mapped[int | None]
    score: Mapped[float]
    max_score: Mapped[float]
    # {"understood", "missing_concepts", "explanation", "criteria": [...], "citations": [...]}
    feedback: Mapped[dict] = mapped_column(JSONB)
    grader_model: Mapped[str | None] = mapped_column(String(100))
    research_logged: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    question: Mapped[PracticeQuestion] = relationship(foreign_keys=[question_id])
