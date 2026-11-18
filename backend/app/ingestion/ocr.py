"""Kare görüntüsündeki yazının yerel OCR'ı: Tesseract (#24, ADR-10).

Tesseract komut satırından çağrılır (Python paketi yok); kelime başına güven puanı için TSV
çıktısı okunur. Metne yalnızca güveni eşiği geçen kelimeler girer: okunamayan kelime tahmin
edilmez. Karenin durumu buna göre açıkça işaretlenir (`classify`).

Görüntü üç biçimde okunur ve daha çok kelimeyi güvenle okuyan seçilir (`best_reading`):
gri ton; siyah-beyaz, koyu dolu kutuların içi ters çevrilmiş (diyagram kutusundaki açık renkli
yazı Tesseract'ın sayfa analizinde ancak böyle bulunur); yarı boyutta gri ton (Tesseract çok
büyük harfi, ör. 100 pikselden yüksek başlık, kaçırır; küçük görüntüde yapılmaz). Hepsinde
diyagramın ince çizgileri silinir.
"""

import csv
import io
import re
import subprocess
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from app.schemas.sources import FrameStatus

# Bu güvenin (0–100) altındaki kelime metne girmez.
MIN_WORD_CONFIDENCE = 60
# 1–2 karakterlik parçalar için güven eşiği. Tesseract'ın tanımadığı işaretler (Σ, ok ucu,
# derece) kısa parçalara orta güvenle dönüşür (ör. Σ → "2" %64); gerçek kısa parçalar (`+`, `==`,
# `x:`, "Ön") ölçümlerde %88'in üstünde okundu.
MIN_SHORT_WORD_CONFIDENCE = 80
# Okunan kelimelere göre okunamayanların payı bunun üstündeyse kare `partial` sayılır.
MAX_DOUBTFUL_SHARE = 0.25
# Hiç kelime okunamadıysa: en az bu kadar aday kelime varsa yazı var ama okunamadı
# (`unreadable`), yoksa karede yazı yok (`no_text`).
MIN_UNREADABLE_CANDIDATES = 3
# Küçük görüntü OCR için büyütülür (Tesseract ~30 piksel satır yüksekliğinde iyi okur).
MIN_OCR_HEIGHT = 1000
# Yarı boyutlu okuma bu yükseklikten küçük görüntüde yapılmaz (yazı fazla küçülür).
MIN_HALF_SOURCE_HEIGHT = 600
# Gri tonu bunun altındaki piksel koyu (mürekkep) sayılır.
DARK = 128
TIMEOUT_S = 120
# Dersin dili → Tesseract dil paketleri. Türkçe derslerin slaytlarında İngilizce terim sık geçer.
_LANGUAGES = {"tr": "tur+eng", "en": "eng"}


class OcrError(Exception):
    """Tesseract çalışmadı (kurulu değil, dil paketi yok, görüntü okunamadı)."""


@dataclass(frozen=True)
class Word:
    text: str
    confidence: float
    # Tesseract'ın blok / paragraf / satır numaraları: metin satır düzeniyle yeniden kurulur.
    line: tuple[int, int, int]


@dataclass(frozen=True)
class OcrResult:
    status: FrameStatus
    # Yalnızca okunan (güvenli) kelimeler, satır düzeniyle; `unreadable`/`no_text`te None.
    text: str | None
    # Okunan kelimelerin ortalama güveni (0–1).
    confidence: float | None


def tesseract_languages(course_language: str) -> str:
    return _LANGUAGES.get(course_language, "eng")


@cache
def tesseract_version() -> str:
    """Kurulu Tesseract'ın sürümü (ör. "5.5.0"); kurulu değilse `OcrError`."""
    try:
        output = subprocess.run(
            ["tesseract", "--version"], capture_output=True, text=True, timeout=30, check=True
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise OcrError("Tesseract çalıştırılamadı.") from exc
    match = re.search(r"tesseract\s+v?(\S+)", output)
    return match.group(1) if match else "unknown"


def extractor_identity(languages: str) -> str:
    """Kareye yazılan araç kimliği, ör. "tesseract/5.5.0/tur+eng"."""
    return f"tesseract/{tesseract_version()}/{languages}"


def read_image(image_path: Path, languages: str) -> OcrResult:
    """Görüntüdeki yazıyı okur ve karenin durumunu belirler. Görüntü açılamaz ya da Tesseract
    çalışmazsa `OcrError` (çağıran o kareyi `unreadable` sayar; transkript etkilenmez)."""
    try:
        variants = _variants(image_path)
    except Exception as exc:
        raise OcrError("Kare görüntüsü açılamadı.") from exc
    return classify(best_reading([_tesseract(png, languages) for png in variants]))


def best_reading(readings: list[list[Word]]) -> list[Word]:
    """Daha çok harf/rakam içeren kelimeyi güvenle okuyan okuma; eşitse güven toplamı yüksek
    olan, o da eşitse ilki."""

    def score(words: list[Word]) -> tuple[int, float]:
        read = [w for w in words if _has_alnum(w.text) and _is_read(w)]
        return len(read), sum(w.confidence for w in read)

    return max(readings, key=score, default=[])


def _tesseract(png: bytes, languages: str) -> list[Word]:
    try:
        tsv = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", languages, "--psm", "3", "tsv"],
            input=png,
            capture_output=True,
            timeout=TIMEOUT_S,
            check=True,
        ).stdout.decode("utf-8", errors="replace")
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip()
        raise OcrError(f"Tesseract hata verdi: {detail[:200]}") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise OcrError("Tesseract çalıştırılamadı.") from exc
    return parse_tsv(tsv)


def parse_tsv(tsv: str) -> list[Word]:
    """Tesseract TSV çıktısındaki kelimeler (level 5); boş ve güvensiz (-1) satırlar atılır."""
    words = []
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        if row.get("level") != "5":
            continue
        text = (row.get("text") or "").strip()
        try:
            confidence = float(row.get("conf") or -1)
            line = (int(row["block_num"]), int(row["par_num"]), int(row["line_num"]))
        except (KeyError, TypeError, ValueError):
            continue  # Beklenmeyen biçimdeki satır okunmamış sayılır.
        if not text or confidence < 0:
            continue
        words.append(Word(text=text, confidence=confidence, line=line))
    return words


def classify(words: Iterable[Word]) -> OcrResult:
    """Okunan kelimelerden metni ve karenin durumunu çıkarır.

    Güveni `MIN_WORD_CONFIDENCE` (1–2 karakterlik parçada `MIN_SHORT_WORD_CONFIDENCE`) altındaki
    parçalar metne girmez. Formül ve kod işaretleri (`=`, `+`, `//`) güvenliyse metne girer, ama
    durum yalnızca harf ya da rakam içeren kelimelerle ölçülür (çizgi ve kutu kenarı gürültüsü
    durumu bozmasın). Okunamayan kelimelerin payı yüksekse kare `partial`; hiç kelime
    okunamadıysa `unreadable` ya da `no_text` olur.
    """
    words = list(words)
    candidates = [word for word in words if _has_alnum(word.text)]
    read = [word for word in candidates if _is_read(word)]
    if not read:
        status: FrameStatus = (
            "unreadable" if len(candidates) >= MIN_UNREADABLE_CANDIDATES else "no_text"
        )
        return OcrResult(status=status, text=None, confidence=None)
    lines: dict[tuple[int, int, int], list[str]] = {}
    for word in words:
        if _is_read(word):
            lines.setdefault(word.line, []).append(word.text)
    text = "\n".join(" ".join(line) for _, line in sorted(lines.items()))
    confidence = sum(word.confidence for word in read) / len(read) / 100
    partial = (len(candidates) - len(read)) / len(candidates) > MAX_DOUBTFUL_SHARE
    return OcrResult(
        status="partial" if partial else "readable", text=text, confidence=round(confidence, 3)
    )


def _has_alnum(text: str) -> bool:
    return any(char.isalnum() for char in text)


def _is_read(word: Word) -> bool:
    """Parça güvenle okundu mu: kısa parçalar daha yüksek güven ister."""
    threshold = MIN_SHORT_WORD_CONFIDENCE if len(word.text) <= 2 else MIN_WORD_CONFIDENCE
    return word.confidence >= threshold


def _variants(image_path: Path) -> list[bytes]:
    """OCR'a verilecek üç görüntü (PNG baytları), bkz. modül açıklaması. `numpy`/`PIL` yalnızca
    Docker imajındadır; burada içe aktarılır."""
    import numpy as np
    from PIL import Image

    with Image.open(image_path) as image:
        original = image.convert("L")
    gray = original
    if gray.height < MIN_OCR_HEIGHT:
        scale = MIN_OCR_HEIGHT / gray.height
        gray = gray.resize((round(gray.width * scale), MIN_OCR_HEIGHT), Image.Resampling.LANCZOS)
    pixels = np.asarray(gray)
    inverted = pixels.copy()
    for top, bottom, left, right in _filled_boxes(pixels < DARK):
        inverted[top:bottom, left:right] = 255 - inverted[top:bottom, left:right]
    binary = np.where(inverted < DARK, 0, 255).astype(np.uint8)
    variants = [_png(_without_thin_lines(pixels)), _png(_without_thin_lines(binary))]
    if original.height >= MIN_HALF_SOURCE_HEIGHT:
        half = original.resize(
            (original.width // 2, original.height // 2), Image.Resampling.LANCZOS
        )
        variants.append(_png(_without_thin_lines(np.asarray(half))))
    return variants


def _png(pixels) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format="PNG")
    return buffer.getvalue()


def _without_thin_lines(pixels):
    """Diyagramın ince kenar ve ok çizgilerini (uzun, ince, koyu) beyaza boyar.

    Tesseract, çizgiye değen ya da kutu içindeki yazıyı çizgiyle birlikte okumaya çalışıp
    kaçırır. Silinen piksel: bir yönde en az `height // 6` uzunlukta koyu çizginin parçası ve
    öbür yönde `height // 80`den ince. Büyük başlıktaki harf gövdeleri bundan kısadır (daha kısa
    eşikte "Graph" → "Grad" olmuştu); dolu alanlar kalındır, silinmez.
    """
    height = pixels.shape[0]
    ink = pixels < DARK
    length, thick = max(40, height // 6), max(8, height // 80)
    lines = (_long_runs(ink, length, axis=1) & ~_long_runs(ink, thick, axis=0)) | (
        _long_runs(ink, length, axis=0) & ~_long_runs(ink, thick, axis=1)
    )
    if not lines.any():
        return pixels
    cleaned = pixels.copy()
    cleaned[lines] = 255
    return cleaned


def _filled_boxes(ink, cell: int = 8, min_share: float = 0.004, min_solidity: float = 0.7):
    """Koyu dolu dikdörtgenler (diyagram kutusu, renkli şerit): (üst, alt, sol, sağ) pikselleri.

    Görüntü `cell` piksellik hücrelere bölünür; çoğu koyu olan hücrelerin bağlı bileşenlerinden
    yeterince büyük (`min_share`) ve sınır kutusunu dolduranlar (`min_solidity`; yazı satırları
    seyrektir, elenir) seçilir. Sınırlar sonra piksel düzeyinde daraltılır: kutuya değen ok
    ucu kutuya katılmaz.
    """
    import numpy as np

    height, width = ink.shape
    rows, cols = height // cell, width // cell
    grid = (
        ink[: rows * cell, : cols * cell].reshape(rows, cell, cols, cell).mean(axis=(1, 3)) >= 0.5
    )
    seen = np.zeros_like(grid)
    boxes = []
    for start in zip(*np.nonzero(grid), strict=True):
        if seen[start]:
            continue
        seen[start] = True
        queue, cells = deque([start]), 0
        top, left = bottom, right = start
        while queue:
            y, x = queue.popleft()
            cells += 1
            top, bottom, left, right = min(top, y), max(bottom, y), min(left, x), max(right, x)
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < rows and 0 <= nx < cols and grid[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    queue.append((ny, nx))
        area = (bottom - top + 1) * (right - left + 1)
        if cells >= min_share * rows * cols and cells / area >= min_solidity:
            box = _tightened(ink, top * cell, (bottom + 1) * cell, left * cell, (right + 1) * cell)
            if box is not None:
                boxes.append(box)
    return boxes


def _tightened(ink, top: int, bottom: int, left: int, right: int):
    """Kenarlardan, çoğu koyu olmayan satır ve sütunları atar; kutu kalmazsa None."""
    region = ink[top:bottom, left:right]
    solid_rows = (region.mean(axis=1) >= 0.5).nonzero()[0]
    solid_cols = (region.mean(axis=0) >= 0.5).nonzero()[0]
    if not len(solid_rows) or not len(solid_cols):
        return None
    return (
        top + int(solid_rows[0]),
        top + int(solid_rows[-1]) + 1,
        left + int(solid_cols[0]),
        left + int(solid_cols[-1]) + 1,
    )


def _long_runs(mask, length: int, axis: int):
    """`mask`te `axis` yönünde en az `length` uzunluğunda kesintisiz True olan pikseller."""
    import numpy as np

    values = mask.astype(np.int32)
    if axis == 0:
        values = values.T
    width = values.shape[1]
    if width < length:
        covered = np.zeros(values.shape, dtype=bool)
        return covered.T if axis == 0 else covered
    sums = np.cumsum(np.pad(values, ((0, 0), (1, 0))), axis=1)
    # full[:, i]: [i, i + length) penceresinin tamamı mürekkep.
    full = ((sums[:, length:] - sums[:, :-length]) == length).astype(np.int32)
    # Piksel p, başlangıcı [p - length + 1, p] aralığında olan bir dolu pencerenin içindeyse
    # çizginin parçasıdır: sayım, sola `length` sağa `length - 1` dolgulu birikimli toplamla.
    counts = np.cumsum(np.pad(full, ((0, 0), (length, length - 1))), axis=1)
    covered = (counts[:, length : length + width] - counts[:, :width]) > 0
    return covered.T if axis == 0 else covered
