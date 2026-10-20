import re
from pathlib import Path

import pymupdf

from app.ingestion.types import RawSegment


def parse_pdf(path: Path) -> list[RawSegment]:
    """PDF (ders kitabı, not, geçmiş sınav) → sayfa başına bir segment, sayfa numarası 1'den.

    Boş sayfalar da döner; temizleme adımında atılır. Böylece sayfa sayısı doğru kalır.
    """
    with pymupdf.open(path) as document:
        return [_parse_page(page) for page in document]


def _parse_page(page: pymupdf.Page) -> RawSegment:
    text = page.get_text("text", sort=True)
    layout = page.get_text("dict", flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)
    layout_lines = [
        line for block in layout["blocks"] if block["type"] == 0 for line in block["lines"]
    ]
    protected = [
        pymupdf.Rect(line["bbox"])
        for line in layout_lines
        if any(span["flags"] & (1 | 8) for span in line["spans"])
    ]
    line_boxes: dict[str, list[pymupdf.Rect]] = {}
    for line in layout_lines:
        key = " ".join("".join(span["text"] for span in line["spans"]).split())
        line_boxes.setdefault(key, []).append(pymupdf.Rect(line["bbox"]))
    words = page.get_text("words")
    margins = {}
    for index, line in enumerate(text.split("\n")):
        query = " ".join(line.split())
        if not query or len(query) > 80:
            continue
        # Ambiguous matches (including a copy in the body) are retained.
        boxes = (
            [pymupdf.Rect(word[:4]) for word in words if word[4] == query]
            if query.isdecimal()
            else line_boxes.get(query, [])
        )
        if len(boxes) != 1:
            continue
        box = boxes[0]
        if any(box.intersects(code_or_math) for code_or_math in protected):
            continue
        if box.y1 <= page.rect.height * 0.1 or box.y0 >= page.rect.height * 0.9:
            margins[index] = (box.x0 / page.rect.width, box.y0 / page.rect.height)
    warnings = []
    if any(re.search(r"\S {3,}\S", line) for line in text.split("\n")) or any(
        span["flags"] & 1 for line in layout_lines for span in line["spans"]
    ):
        warnings.append(
            f"Sayfa {page.number + 1}: Sütun, tablo ve formüllerin yerleşimi metinde tam "
            "temsil edilemeyebilir; bu öğeleri kaynak sayfayla karşılaştırın."
        )
    if page.get_images() or page.get_drawings():
        warnings.append(
            f"Sayfa {page.number + 1}: Şekil ve görsellerin içeriği metne dönüştürülmedi."
        )
    if not text.strip():
        warnings.append(
            f"Sayfa {page.number + 1}: Metin okunamadı; görüntüdeki yazılar için OCR gerekir."
        )
    if "\ufffd" in text:
        warnings.append(
            f"Sayfa {page.number + 1}: Bazı karakterler okunamadı; kaynak sayfayı kontrol edin."
        )
    return RawSegment(text=text, page=page.number + 1, margin_lines=margins, warnings=warnings)
