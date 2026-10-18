from pathlib import Path

from pptx import Presentation
from pptx.shapes.base import BaseShape
from pptx.shapes.group import GroupShape

from app.ingestion.types import RawSegment


def parse_pptx(path: Path) -> list[RawSegment]:
    """PPTX → slayt başına bir segment; slayt numarası `page` olarak tutulur.

    Başlık, metin kutuları, tablolar, gruplar ve konuşmacı notları okunur.
    """
    presentation = Presentation(str(path))
    segments: list[RawSegment] = []
    for number, slide in enumerate(presentation.slides, start=1):
        lines: list[str] = []
        for shape in slide.shapes:
            lines.extend(_shape_lines(shape))
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                lines.append(notes)
        segments.append(RawSegment(text="\n".join(lines), page=number))
    return segments


def _shape_lines(shape: BaseShape) -> list[str]:
    if isinstance(shape, GroupShape):
        return [line for child in shape.shapes for line in _shape_lines(child)]
    if shape.has_text_frame:
        return [shape.text_frame.text]
    if getattr(shape, "has_table", False):
        return [" | ".join(cell.text.strip() for cell in row.cells) for row in shape.table.rows]
    return []
