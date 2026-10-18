"""Kaynak görüntüleyici: PDF sayfasını görüntüye çevirir, alıntılanan satırları sayfada bulur."""

from pathlib import Path

import pymupdf

from app.core.config import settings
from app.db.models import Document
from app.schemas.sources import Highlight

# 2x ≈ 144 dpi: ekranda net, dosya küçük.
RENDER_ZOOM = 2.0
# Satırın tamamı bulunamazsa aranacak baş kısmı (PDF'te satır farklı bölünmüş olabilir).
SEARCH_CHARS = 60
MIN_LINE_CHARS = 4


def is_pdf(document: Document) -> bool:
    return document.filename.lower().endswith(".pdf")


def page_image_path(document: Document, page: int) -> Path | None:
    """Sayfanın PNG'sini (önbellekten ya da yeni oluşturarak) döner; sayfa yoksa None."""
    if not is_pdf(document) or page < 1:
        return None
    target = settings.cache_dir / "pages" / str(document.id) / f"{page}.png"
    if target.is_file():
        return target
    with pymupdf.open(document.file_path) as pdf:
        if page > pdf.page_count:
            return None
        pixmap = pdf[page - 1].get_pixmap(matrix=pymupdf.Matrix(RENDER_ZOOM, RENDER_ZOOM))
        target.parent.mkdir(parents=True, exist_ok=True)
        pixmap.save(target)
    return target


def find_highlights(document: Document, page: int, text: str) -> list[Highlight]:
    """Parçanın satırlarını PDF sayfasında arar; bulunan dikdörtgenleri sayfaya oranla döner."""
    if not is_pdf(document) or page < 1:
        return []
    highlights: list[Highlight] = []
    seen: set[tuple[int, int, int, int]] = set()
    with pymupdf.open(document.file_path) as pdf:
        if page > pdf.page_count:
            return []
        pdf_page = pdf[page - 1]
        width, height = pdf_page.rect.width, pdf_page.rect.height
        for line in text.split("\n"):
            line = line.strip()
            if len(line) < MIN_LINE_CHARS:
                continue
            # Önce satırın tamamı; PDF'te farklı bölünmüşse baş kısmı.
            rects = pdf_page.search_for(line) or pdf_page.search_for(line[:SEARCH_CHARS])
            for rect in rects:
                key = (round(rect.x0), round(rect.y0), round(rect.x1), round(rect.y1))
                if key in seen:
                    continue
                seen.add(key)
                highlights.append(
                    Highlight(
                        x=rect.x0 / width,
                        y=rect.y0 / height,
                        width=rect.width / width,
                        height=rect.height / height,
                    )
                )
    return highlights


def remove_cached_pages(document_id: int) -> None:
    folder = settings.cache_dir / "pages" / str(document_id)
    if folder.is_dir():
        for file in folder.iterdir():
            file.unlink(missing_ok=True)
        folder.rmdir()
