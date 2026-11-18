"""Depolama saklama kuralları: sahipsiz dosyaların temizliği (#25, ADR-11).

Kurallar (CONTRACTS.md §4.3):
- Yüklenen medya yalnızca onu okuyacak iş (transkripsiyon, kare çıkarma) bitene kadar saklanır.
- Dokümanın dosyası (`file_path`) ve kare görüntüleri dokümanla yaşar; doküman silinince silinir.
- İşler bu kuralları kendileri uygular. Süreç tam o anda öldüyse (çökme, disk hatası) kalan
  dosyaları çalıştırıcı düzenli aralıkla (`STORAGE_SWEEP_INTERVAL_S`) burada siler:
  silinmiş dokümanın dosyaları ve kare klasörleri, etkin işi olmayan geçici kare klasörü, hiçbir
  etkin işin girdisi olmayan ve dokümanın dosyası da olmayan `<doküman>.<uzantı>` dosyaları.
- `STORAGE_ORPHAN_GRACE_S`'ten yeni dosyaya dokunulmaz: yazılmakta olan yükleme (doküman henüz
  commit edilmemiş) silinmez.

Yalnızca `UPLOAD_DIR/<ders>/<doküman>[.frames].<uzantı>` ve
`UPLOAD_DIR/<ders>/frames/<doküman>[.partial|.previous]` biçimindeki yollar ele alınır; başka
dosyaya dokunulmaz. `.partial` (iş sürerken yazılan) ve `.previous` (#27: yeni kareler yazılırken
kenara alınan eski kareler) klasörleri yalnızca dokümanın kare işi sürüyorsa korunur.

Güvenlik:
- Sembolik bağlantı izlenmez (ders klasörü, `frames` klasörü ve aday yolların kendisi); silinecek
  her yolun gerçek konumu `UPLOAD_DIR`in altında olmalıdır.
- Karar tarama anında değil, silmeden hemen önce yeniden verilir: dokümanın satırı kilitlenir
  (`FOR UPDATE SKIP LOCKED`; kilitliyse bu turda atlanır), etkin işler ve dokümanın dosyası yeniden
  okunur ve yolun kimliği (inode, değişme zamanı) taramadakiyle aynı olmalıdır. Kilit tutulurken
  dokümana yeni iş eklenemez (iş satırının yabancı anahtarı dokümanın satırını paylaşımlı kilitler)
  ve kare videosu ekleme ucu (`POST /documents/{id}/frames`) aynı satırı kilitleyerek dosya yazar;
  böylece eski bir karar yeni bir işin ya da yüklemenin dosyasını silemez.
"""

import logging
import os
import re
import stat
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Document, ProcessingJob
from app.ingestion.documents import remove_paths
from app.jobs.queue import ACTIVE_STATUSES, FRAMES
from app.schemas.common import PG_INT_MAX

logger = logging.getLogger(__name__)

# `<doküman>.frames.<uzantı>`: altyazılı videoya kareler için sonradan eklenen medya (#27).
_DOCUMENT_FILE = re.compile(r"^(\d+)(?:\.frames)?\.[A-Za-z0-9]+$")
_FRAME_DIR = re.compile(r"^(\d+)(\.partial|\.previous)?$")


@dataclass(frozen=True)
class _Entry:
    course_id: int
    document_id: int
    path: Path
    # file: dokümanın dosyası ya da ara dosyası · frames: kare klasörü ·
    # staging: geçici (`.partial`) ya da kenara alınmış (`.previous`) kare klasörü
    kind: str
    # Taramadaki kimlik: (aygıt, inode, değişme zamanı ns, durum değişme zamanı ns).
    identity: tuple[int, int, int, int]


def sweep_storage(db: Session) -> int:
    """Sahipsiz dosya ve klasörleri siler; silinen yol sayısını döndürür. Birden çok çalıştırıcı
    aynı anda çağırabilir. İşlem kapatılarak döner."""
    root = _canonical_root()
    if root is None:
        return 0
    cutoff_ns = int((time.time() - settings.storage_orphan_grace_s) * 1e9)
    removed = 0
    for entry in _entries(root):
        if entry.identity[2] >= cutoff_ns:
            continue
        try:
            if _remove_if_orphan(db, entry, root, cutoff_ns):
                removed += 1
        finally:
            db.rollback()
    if removed:
        logger.warning("Depolama temizliği: %d sahipsiz dosya/klasör silindi", removed)
    return removed


def _remove_if_orphan(db: Session, entry: _Entry, root: Path, cutoff_ns: int) -> bool:
    """Girdiyi yeniden denetler ve sahipsizse siler (dokümanın satır kilidi altında)."""
    document = None
    if entry.document_id <= PG_INT_MAX:  # Daha büyük sayı hiçbir dokümanın değildir.
        document = db.scalar(
            select(Document)
            .where(Document.id == entry.document_id)
            .with_for_update(skip_locked=True)
        )
        if document is None and db.get(Document, entry.document_id) is not None:
            return False  # Satır başka bir işlemde kilitli: bu turda dokunulmaz.
    if document is not None and document.course_id == entry.course_id:
        if not _orphan_of(db, entry, document):
            return False
    # Silmeden hemen önce: yol hâlâ aynı nesne mi, hâlâ eski mi, hâlâ kök altında mı?
    if _identity(entry.path) != entry.identity or entry.identity[2] >= cutoff_ns:
        return False
    if not _inside(entry.path, root):
        logger.warning("Depolama temizliği: kök dışına çıkan yol atlandı: %s", entry.path)
        return False
    remove_paths([entry.path])
    return True


def _orphan_of(db: Session, entry: _Entry, document: Document) -> bool:
    """Var olan dokümanın girdisi sahipsiz mi (etkin işler o an yeniden okunur)."""
    active = db.execute(
        select(ProcessingJob.kind, ProcessingJob.input_path).where(
            ProcessingJob.document_id == document.id,
            ProcessingJob.status.in_(ACTIVE_STATUSES),
        )
    ).all()
    if entry.kind == "frames":
        return False
    if entry.kind == "staging":
        return not any(kind == FRAMES for kind, _ in active)
    resolved = entry.path.resolve()
    if any(Path(input_path).resolve() == resolved for _, input_path in active):
        return False
    return not document.file_path or Path(document.file_path).resolve() != resolved


def _entries(root: Path) -> list[_Entry]:
    entries = []
    for course_dir in _children(root):
        if not course_dir.name.isdigit() or not _is_real_dir(course_dir):
            continue
        course_id = int(course_dir.name)
        for path in _children(course_dir):
            match = _DOCUMENT_FILE.match(path.name)
            if match and (identity := _identity(path, stat.S_ISREG)) is not None:
                entries.append(_Entry(course_id, int(match[1]), path, "file", identity))
        frames = course_dir / "frames"
        if not _is_real_dir(frames):
            continue
        for path in _children(frames):
            match = _FRAME_DIR.match(path.name)
            if match and (identity := _identity(path, stat.S_ISDIR)) is not None:
                kind = "staging" if match[2] else "frames"
                entries.append(_Entry(course_id, int(match[1]), path, kind, identity))
    return entries


def _canonical_root() -> Path | None:
    root = settings.upload_dir
    return root.resolve() if _is_real_dir(root) else None


def _children(directory: Path) -> list[Path]:
    try:
        return list(directory.iterdir())
    except OSError:
        return []


def _is_real_dir(path: Path) -> bool:
    """Gerçek klasör (sembolik bağlantı değil)."""
    return _identity(path, stat.S_ISDIR) is not None


def _identity(path: Path, kind=None) -> tuple[int, int, int, int] | None:
    """Bağlantı izlenmeden okunan kimlik; yol yoksa, sembolik bağlantıysa ya da beklenen türde
    değilse None."""
    try:
        info = os.lstat(path)
    except OSError:
        return None
    if stat.S_ISLNK(info.st_mode) or (kind is not None and not kind(info.st_mode)):
        return None
    return (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns)


def _inside(path: Path, root: Path) -> bool:
    try:
        return path.resolve(strict=True).is_relative_to(root)
    except OSError:
        return False
