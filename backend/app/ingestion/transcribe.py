"""Altyazısı olmayan ders videosu/sesi → zaman damgalı transkript (yerel faster-whisper, ADR-6).

`faster_whisper` yalnızca transkripsiyon çağrılınca içe aktarılır: CI ve testler (`.[dev]`)
bu bağımlılığı kurmaz, sahte `Transcriber` enjekte eder.
"""

import logging
from functools import cache
from pathlib import Path
from typing import Protocol

from app.core.config import settings
from app.ingestion.types import RawSegment

logger = logging.getLogger(__name__)

COMPUTE_TYPE = "int8"
# Bu eşiklerin dışındaki segmentler güvenilmez sayılır (uydurma / belirsiz metin olasılığı).
MAX_NO_SPEECH_PROB = 0.6
MIN_AVG_LOGPROB = -1.0


class TranscriptionError(Exception):
    """Kullanıcıya gösterilecek kısa Türkçe neden taşıyan transkripsiyon hatası."""


class Transcriber(Protocol):
    # Dokümana yazılan model kimliği (ör. faster-whisper/large-v3-turbo/int8).
    identity: str

    def transcribe(self, path: Path, language: str) -> tuple[list[RawSegment], float, list[str]]:
        """(zamanlı segmentler, medya süresi sn, uyarılar). Konuşma yoksa segment listesi boş."""
        ...


@cache
def load_model(name: str):
    from faster_whisper import WhisperModel

    return WhisperModel(name, device="cpu", compute_type=COMPUTE_TYPE)


class FasterWhisperTranscriber:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.identity = f"faster-whisper/{model_name}/{COMPUTE_TYPE}"

    def transcribe(self, path: Path, language: str) -> tuple[list[RawSegment], float, list[str]]:
        try:
            model = load_model(self.model_name)
        except Exception as exc:
            logger.exception("Transkripsiyon modeli yüklenemedi: %s", self.model_name)
            raise TranscriptionError("Transkripsiyon modeli yüklenemedi.") from exc
        try:
            # Ses çözme bu çağrıda yapılır; bozuk/desteklenmeyen medya burada hata verir.
            raw_segments, info = model.transcribe(
                str(path),
                language=language,
                vad_filter=True,
                condition_on_previous_text=False,
            )
        except Exception as exc:
            logger.exception("Medya çözülemedi: %s", path.name)
            raise TranscriptionError("Medya dosyası çözülemedi.") from exc

        segments: list[RawSegment] = []
        doubtful = 0
        for raw in raw_segments:
            segments.append(RawSegment(text=raw.text, t_start=raw.start, t_end=raw.end))
            if raw.no_speech_prob > MAX_NO_SPEECH_PROB or raw.avg_logprob < MIN_AVG_LOGPROB:
                doubtful += 1
        warnings = []
        if doubtful:
            warnings.append(
                f"{doubtful} bölümün sesi belirsiz; transkript bu aralıklarda hatalı olabilir."
            )
        return segments, float(info.duration), warnings


def get_transcriber() -> Transcriber:
    return FasterWhisperTranscriber(settings.transcription_model)
