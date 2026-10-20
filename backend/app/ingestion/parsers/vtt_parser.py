import re
from dataclasses import dataclass
from pathlib import Path

from app.ingestion.types import IngestionError, RawSegment

# Geçersiz cue'ların oranı bunu aşarsa dosya bozuk sayılır ve reddedilir.
MAX_SKIPPED_RATIO = 0.5

_TIMING = re.compile(r"^(\S+?)\s*-->\s*(\S+)(?:\s.*)?$")
_TIMESTAMP = re.compile(r"^(?:(\d+):)?([0-5]\d):([0-5]\d)\.(\d{3})$")
# Yalnızca VTT'nin tanımladığı satır içi etiketler; "a < b" gibi metin silinmesin.
# <v Ad> / <v.sınıf Ad> etiketi konuşmacı adını da taşır: ad metne girmez (ADR-5).
_TAG = re.compile(
    r"</?(?:c|i|b|u|v|ruby|rt|rp|lang)(?:[.\s][^>]*)?>|<(?:\d+:)?[0-5]\d:[0-5]\d\.\d{3}>"
)
_ENTITY = re.compile(r"&(amp|lt|gt|nbsp|lrm|rlm);")
_ENTITIES = {"amp": "&", "lt": "<", "gt": ">", "nbsp": " ", "lrm": "", "rlm": ""}
_NON_CUE_BLOCKS = ("NOTE", "STYLE", "REGION")


@dataclass
class ParsedVtt:
    segments: list[RawSegment]
    cues_read: int
    cues_skipped: int
    # Geçerli cue'ların en geç bitişi (saniye).
    duration_s: float


def parse_vtt(path: Path) -> ParsedVtt:
    """VTT altyazı → her geçerli cue için t_start / t_end zaman damgalı ham metin.

    Kendi ayrıştırıcımız (yalnızca stdlib). Bozuk cue atlanır ve sayılır; dosya bütünüyle
    bozuksa ya da cue'ların yarısından fazlası atlandıysa `IngestionError` fırlatılır.
    """
    return parse_vtt_bytes(path.read_bytes())


def parse_vtt_bytes(content: bytes) -> ParsedVtt:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestionError("Altyazı dosyası UTF-8 olarak okunamadı.") from exc
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n[ \t]*\n+", text.strip("\n"))
    header = blocks[0].split("\n", 1)[0]
    if not (header == "WEBVTT" or re.match(r"WEBVTT[ \t]", header)):
        raise IngestionError("Geçerli bir altyazı dosyası değil: 'WEBVTT' başlığı bulunamadı.")

    segments: list[RawSegment] = []
    skipped = 0
    duration = 0.0
    previous_last_line: str | None = None
    for block in blocks[1:]:
        lines = block.split("\n")
        if re.match(rf"({'|'.join(_NON_CUE_BLOCKS)})([ \t]|$)", lines[0]):
            continue
        timing_index = next((i for i, line in enumerate(lines[:2]) if "-->" in line), None)
        times = _parse_timing(lines[timing_index]) if timing_index is not None else None
        if timing_index is None or times is None:
            skipped += 1
            continue
        start, end = times
        duration = max(duration, end)
        cue_lines = [
            cleaned
            for cleaned in (_clean_line(line) for line in lines[timing_index + 1 :])
            if cleaned
        ]
        # YouTube otomatik altyazısı: kayan satır, önceki cue'nun son satırını tekrar eder.
        kept = cue_lines
        if kept and previous_last_line is not None and kept[0] == previous_last_line:
            kept = kept[1:]
        if cue_lines:
            previous_last_line = cue_lines[-1]
        if kept:
            segments.append(RawSegment(text=" ".join(kept), t_start=start, t_end=end))

    total = len(segments) + skipped
    if not segments:
        raise IngestionError(
            "Altyazıda okunabilir metin bulunamadı: geçerli zaman aralığı ve metni olan cue yok."
        )
    if skipped / total > MAX_SKIPPED_RATIO:
        raise IngestionError(
            f"Altyazı dosyası bozuk: {total} cue'dan {skipped} tanesi okunamadı. "
            "Dosyayı kontrol edip yeniden yükleyin."
        )
    return ParsedVtt(
        segments=segments, cues_read=len(segments), cues_skipped=skipped, duration_s=duration
    )


def _parse_timing(line: str) -> tuple[float, float] | None:
    match = _TIMING.match(line.strip())
    if match is None:
        return None
    start, end = _timestamp(match.group(1)), _timestamp(match.group(2))
    if start is None or end is None or end < start:
        return None
    return start, end


def _timestamp(value: str) -> float | None:
    match = _TIMESTAMP.match(value)
    if match is None:
        return None
    hours, minutes, seconds, millis = match.groups()
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def _clean_line(line: str) -> str:
    line = _TAG.sub("", line)
    line = _ENTITY.sub(lambda m: _ENTITIES[m.group(1)], line)
    return " ".join(line.split())


def write_vtt(path: Path, segments: list[RawSegment]) -> None:
    """Zamanlı segmentleri WebVTT dosyası olarak yazar (`parse_vtt` ile geri okunabilir)."""
    blocks = [
        f"{_format_timestamp(segment.t_start or 0.0)} --> "
        f"{_format_timestamp(segment.t_end or 0.0)}\n{_cue_text(segment.text)}"
        for segment in segments
    ]
    path.write_text("WEBVTT\n\n" + "\n\n".join(blocks) + "\n", encoding="utf-8")


def _format_timestamp(seconds: float) -> str:
    total_ms = round(seconds * 1000)
    hours, rest = divmod(total_ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    return f"{hours:02}:{minutes:02}:{rest // 1000:02}.{rest % 1000:03}"


def _cue_text(text: str) -> str:
    # Boş satır cue'yu bitirir, "-->" zaman satırı sayılır: ikisi de cue metninde olamaz.
    return " ".join(text.split()).replace("-->", "->")
