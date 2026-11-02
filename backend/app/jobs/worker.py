"""İş çalıştırıcısı (ADR-9): kuyruktan iş alır, çalıştırır, sonucu yazar.

Ayrı süreç olarak: `python -m app.jobs.worker` (docker-compose'ta `worker` servisi,
`JOB_WORKER=external`). `JOB_WORKER=inline` iken API süreci aynı döngüyü bir iş parçacığında
çalıştırır. Birden çok çalıştırıcı aynı veritabanında güvenle çalışabilir.
"""

import logging
import signal
import threading
from collections.abc import Callable
from types import TracebackType

from sqlalchemy.orm import Session

from app.core.config import settings
from app.embeddings.base import Embedder
from app.ingestion.media import transcription_job
from app.ingestion.transcribe import Transcriber, TranscriptionError, get_transcriber
from app.ingestion.types import IngestionError
from app.jobs.queue import (
    CANCELLED_MESSAGE,
    TRANSCRIPTION,
    ClaimedJob,
    JobCancelled,
    JobSuperseded,
    claim_next,
    discard,
    heartbeat,
    recover_stale,
    retry_later,
    settle,
)

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


class _Heartbeat:
    """İş sürerken ayrı bir iş parçacığında canlılık zamanını yeniler.

    İş iptal edilirse ya da silinirse `should_stop()` True olur; uzun adım bunu yoklar.
    """

    def __init__(self, session_factory: SessionFactory, job: ClaimedJob) -> None:
        self.session_factory = session_factory
        self.job = job
        self.stopped = threading.Event()
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._beat, daemon=True)

    def should_stop(self) -> bool:
        return self.stopped.is_set()

    def __enter__(self) -> "_Heartbeat":
        self.thread.start()
        return self

    def __exit__(
        self,
        _type: type[BaseException] | None,
        _value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.done.set()
        self.thread.join()

    def _beat(self) -> None:
        while not self.done.wait(settings.job_heartbeat_interval_s):
            try:
                with self.session_factory() as db:
                    if not heartbeat(db, self.job):
                        self.stopped.set()
                        return
            except Exception:
                logger.exception("İş %s için canlılık yazılamadı", self.job.id)


def run_next(
    session_factory: SessionFactory,
    transcriber: Transcriber | None = None,
    embedder: Embedder | None = None,
) -> bool:
    """Sıradaki bir işi çalıştırır; kuyruk boşsa False."""
    with session_factory() as db:
        job = claim_next(db)
    if job is None:
        return False
    logger.info("İş %s (%s, deneme %s) başladı", job.id, job.kind, job.attempts)
    with _Heartbeat(session_factory, job) as beat:
        outcome = _run(session_factory, job, beat.should_stop, transcriber, embedder)
    logger.info("İş %s bitti: %s", job.id, outcome)
    return True


def run_pending(
    session_factory: SessionFactory,
    transcriber: Transcriber | None = None,
    embedder: Embedder | None = None,
) -> int:
    """Kuyruk boşalana kadar işleri sırayla çalıştırır (testler ve tek seferlik kullanım)."""
    count = 0
    while run_next(session_factory, transcriber, embedder):
        count += 1
    return count


def _run(
    session_factory: SessionFactory,
    job: ClaimedJob,
    should_stop: Callable[[], bool],
    transcriber: Transcriber | None,
    embedder: Embedder | None,
) -> str:
    try:
        if job.kind != TRANSCRIPTION:
            raise IngestionError(f"Bilinmeyen iş türü: {job.kind}")
        transcription_job(
            session_factory, job, transcriber or get_transcriber(), should_stop, embedder
        )
        return "succeeded"
    except JobSuperseded:
        with session_factory() as db:
            discard(db, job)
        return "superseded"
    except JobCancelled:
        with session_factory() as db:
            settle(db, job, "cancelled", CANCELLED_MESSAGE)
        return "cancelled"
    except (TranscriptionError, IngestionError) as exc:
        with session_factory() as db:
            settle(db, job, "failed", str(exc))
        return "failed"
    except Exception:
        # Geçici olabilir (veritabanı bağlantısı koptu vb.): hakkı varsa yeniden denenir.
        logger.exception("İş %s beklenmeyen bir hatayla bitti", job.id)
        with session_factory() as db:
            retried = retry_later(db, job, "Beklenmeyen hata; yeniden denenecek.")
        return "requeued" if retried else "failed"


class Worker:
    """Kuyruğu yoklayan döngü; `stop()` ile süren iş bitince durur."""

    def __init__(
        self,
        session_factory: SessionFactory,
        transcriber: Transcriber | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.transcriber = transcriber
        self.embedder = embedder
        self.stopping = threading.Event()

    def stop(self) -> None:
        self.stopping.set()

    def run(self) -> None:
        logger.info("İş çalıştırıcısı başladı")
        while not self.stopping.is_set():
            try:
                with self.session_factory() as db:
                    recover_stale(db)
                ran = run_next(self.session_factory, self.transcriber, self.embedder)
            except Exception:
                # Veritabanı henüz hazır değil ya da bağlantı koptu: bekleyip yeniden dene.
                logger.exception("İş kuyruğu okunamadı")
                ran = False
            if not ran:
                self.stopping.wait(settings.job_poll_interval_s)
        logger.info("İş çalıştırıcısı durdu")


def start_inline(session_factory: SessionFactory) -> Worker:
    """API süreci içinde arka plan iş parçacığı olarak başlatır (`JOB_WORKER=inline`)."""
    worker = Worker(session_factory)
    threading.Thread(target=worker.run, name="job-worker", daemon=True).start()
    return worker


def main() -> None:
    from app.db.session import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    worker = Worker(SessionLocal)
    # docker stop SIGTERM gönderir: süren iş bitmeden durulmaz; yarıda kesilirse
    # iş canlılığı durunca yeniden kuyruğa alınır.
    signal.signal(signal.SIGTERM, lambda *_: worker.stop())
    signal.signal(signal.SIGINT, lambda *_: worker.stop())
    worker.run()


if __name__ == "__main__":
    main()
