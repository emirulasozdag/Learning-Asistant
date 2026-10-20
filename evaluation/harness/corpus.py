"""İndeksteki ders materyalini envanterle karşılaştırır ve parçaları kaynak konumuna çevirir."""

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Course, Document
from harness.fingerprint import file_sha256
from harness.schemas import CorpusDocument, CorpusManifest, CorpusSnapshot, SourceLocator


class CorpusError(RuntimeError):
    """Koşu güvenilir olmaz: envanter dışı materyal indekste ya da ders yok."""


class Locator:
    """Chunk id → SourceLocator. Doküman parmak izleri bir kez hesaplanır."""

    def __init__(self, db: Session, files_root: Path) -> None:
        self._db = db
        self._files_root = files_root
        self._document_hashes: dict[int, str | None] = {}

    def document_sha256(self, document: Document) -> str | None:
        if document.id not in self._document_hashes:
            path = Path(document.file_path)
            if not path.is_absolute():
                path = self._files_root / path
            self._document_hashes[document.id] = file_sha256(path) if path.is_file() else None
        return self._document_hashes[document.id]

    def locate(self, source_id: str) -> SourceLocator | None:
        if not source_id.isdigit():
            return None
        chunk = self._db.get(Chunk, int(source_id))
        if chunk is None:
            return None
        sha = self.document_sha256(chunk.document)
        if sha is None:
            return None
        has_time = chunk.t_start is not None and chunk.t_end is not None
        return SourceLocator(
            document_sha256=sha,
            page=None if has_time else chunk.page,
            t_start=chunk.t_start if has_time else None,
            t_end=chunk.t_end if has_time else None,
        )


def find_course(db: Session, course_code: str) -> Course:
    course = db.scalar(select(Course).where(Course.code == course_code.upper()))
    if course is None:
        raise CorpusError(f"{course_code} kodlu ders veritabanında yok")
    return course


def snapshot(
    db: Session, course: Course, manifest: CorpusManifest, locator: Locator
) -> CorpusSnapshot:
    """İndeksteki dokümanlar + envanterle farklar.

    Envanterde onaylı olmayan (dışlanmış ya da hiç listelenmemiş) bir doküman indeksteyse
    `unapproved_indexed` dolar; koşu bunu hata sayar.
    """
    rows = db.execute(
        select(Document, func.count(Chunk.id))
        .outerjoin(Chunk, Chunk.document_id == Document.id)
        .where(Document.course_id == course.id)
        .group_by(Document.id)
        .order_by(Document.id)
    ).all()
    approved = manifest.approved_hashes()
    documents: list[CorpusDocument] = []
    unapproved: list[str] = []
    indexed: set[str] = set()
    for document, chunk_count in rows:
        sha = locator.document_sha256(document)
        documents.append(
            CorpusDocument(
                sha256=sha,
                title=document.title,
                material_type=document.material_type,
                chunk_count=chunk_count,
                file_missing=sha is None,
            )
        )
        if sha is None or sha not in approved:
            unapproved.append(document.title)
        elif chunk_count > 0:
            # Parçası olmayan doküman (başarısız yükleme) aranamaz; indekste sayılmaz.
            indexed.add(sha)
    return CorpusSnapshot(
        course_code=course.code,
        documents=documents,
        approved_not_indexed=sorted(approved - indexed),
        unapproved_indexed=unapproved,
    )
