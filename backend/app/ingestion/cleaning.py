import re
from collections import Counter
from dataclasses import dataclass

from app.ingestion.types import RawSegment

# Bir satır, sayfaların en az bu oranında aynen geçiyorsa üst/alt bilgi sayılır
# (ders adı, hoca adı, "Gizli" ibaresi...). Yüksek tutuldu: slaytlarda birkaç sayfada
# tekrarlanan bölüm başlıkları içeriktir, silinmemeli.
REPEATED_LINE_RATIO = 0.8
# Üst/alt bilgi tespiti için en az bu kadar sayfa gerekir.
MIN_SEGMENTS_FOR_REPEAT_CHECK = 4
# Üst/alt bilgi satırları kısa olur; uzun satırlar içerik sayılır.
MAX_REPEATED_LINE_LENGTH = 80

_PAGE_NUMBER = re.compile(r"^(sayfa|page|s\.)?\s*\d{1,4}(\s*(/|of)\s*\d{1,4})?$", re.IGNORECASE)
_HYPHENATED_BREAK = re.compile(r"(\w)-\n(\w)")
# PDF'ler tire glifini sık sık "soft hyphen" (U+00AD) olarak verir.
_SOFT_HYPHEN_LINE_END = re.compile(r"\u00ad\n")
_SOFT_HYPHEN_STANDALONE = re.compile(r"(?<=\s)\u00ad(?=\s)")
_INLINE_SPACE = re.compile(r"[ \t\u00a0\u200b]+")
_BLANK_LINES = re.compile(r"\n{3,}")


@dataclass
class CleaningStats:
    """Temizleme adımının yaptıkları (yükleme raporunda gösterilir)."""

    repeated_lines_removed: int = 0
    page_numbers_removed: int = 0
    empty_segments_dropped: int = 0


def clean_segments(segments: list[RawSegment]) -> list[RawSegment]:
    """Metni normalize eder, üst/alt bilgileri ve sayfa numaralarını siler, boş segmentleri atar.

    Paragraf sınırları (boş satır) korunur; parçalama bunlara göre yapılır.
    """
    return clean_segments_with_stats(segments)[0]


def clean_segments_with_stats(
    segments: list[RawSegment],
) -> tuple[list[RawSegment], CleaningStats]:
    stats = CleaningStats()
    normalized = [_normalize(segment.text) for segment in segments]
    repeated = _repeated_lines(normalized)

    cleaned: list[RawSegment] = []
    for segment, text in zip(segments, normalized, strict=True):
        lines: list[str] = []
        for line in text.split("\n"):
            if line in repeated:
                stats.repeated_lines_removed += 1
            elif _PAGE_NUMBER.match(line):
                stats.page_numbers_removed += 1
            else:
                lines.append(line)
        text = _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()
        if text:
            cleaned.append(
                RawSegment(
                    text=text, page=segment.page, t_start=segment.t_start, t_end=segment.t_end
                )
            )
        else:
            stats.empty_segments_dropped += 1
    return cleaned, stats


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\v", "\n")
    text = _SOFT_HYPHEN_LINE_END.sub("", text)
    text = _SOFT_HYPHEN_STANDALONE.sub("-", text).replace("\u00ad", "")
    text = _HYPHENATED_BREAK.sub(r"\1\2", text)
    lines = [_INLINE_SPACE.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(lines)


def _repeated_lines(texts: list[str]) -> set[str]:
    non_empty = [text for text in texts if text.strip()]
    if len(non_empty) < MIN_SEGMENTS_FOR_REPEAT_CHECK:
        return set()
    counts = Counter(
        line
        for text in non_empty
        for line in {line for line in text.split("\n") if line}
        if len(line) <= MAX_REPEATED_LINE_LENGTH
    )
    threshold = len(non_empty) * REPEATED_LINE_RATIO
    return {line for line, count in counts.items() if count >= threshold}
