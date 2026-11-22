"""İndeksteki ders materyalini envanterle karşılaştırır ve parçaları kaynak konumuna çevirir."""

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Course, Document, VideoFrame
from harness.fingerprint import file_sha256, text_sha256
from harness.schemas import CorpusDocument, CorpusManifest, CorpusSnapshot, SourceLocator


class CorpusError(RuntimeError):
    """Koşu güvenilir olmaz: envanter dışı materyal indekste ya da ders yok."""


FRAME_PREFIX = "frame:"


class Locator:
    """Chunk id ya da kare (`frame:<id>`, #30) → SourceLocator. Doküman parmak izleri bir kez
    hesaplanır. Kare, videonun içerik parmak izi ve ekranda kaldığı aralıkla gösterilir; böylece
    gold kanıtının video zamanıyla eşleşir."""

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
        if source_id.startswith(FRAME_PREFIX):
            return self._locate_frame(source_id.removeprefix(FRAME_PREFIX))
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

    def _locate_frame(self, frame_id: str) -> SourceLocator | None:
        if not frame_id.isdigit():
            return None
        frame = self._db.get(VideoFrame, int(frame_id))
        if frame is None:
            return None
        document = self._db.get(Document, frame.document_id)
        sha = self.document_sha256(document) if document is not None else None
        if sha is None:
            return None
        return SourceLocator(document_sha256=sha, t_start=frame.t_start, t_end=frame.t_end)


def corpus_fingerprint(corpus: CorpusSnapshot) -> str:
    """İndeksteki derlemin kimliği (#29): dokümanların içerik parmak izi, türü ve parça sayısı.

    Doküman kimliklerinden ve başlıklardan bağımsızdır; ders silinip aynı dosyalarla aynı
    parçalama ayarıyla yeniden yüklenirse değişmez. Dosyası bulunamayan doküman da girer
    (`missing`), böylece eksik dosya fark edilir.
    """
    entries = sorted(
        f"{d.sha256 or 'missing'}|{d.material_type}|{d.chunk_count}" for d in corpus.documents
    )
    return text_sha256("\n".join(entries))


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
