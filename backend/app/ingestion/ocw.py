"""MIT OpenCourseWare "Download Course" paketini okur.

Paket yapısı: kökte `data.json` (ders bilgisi), `pages/<bölüm>/data.json` (bölüm sayfaları, HTML),
`resources/<ad>/data.json` (her dosyanın başlığı, türü, bölümü) ve `static_resources/` (dosyalar).

HTML içerik sayfaya basılmaz: izlence ve takvim düz metin bloklarına çevrilir (XSS riski yok).
"""

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from app.schemas.materials import MaterialType

# OCW bölüm adı → bizim materyal türümüz. Listede olmayan bölümler alınmaz.
SECTION_TYPES: dict[str, MaterialType] = {
    "Lecture Notes": MaterialType.NOTES,
    "Recitations": MaterialType.NOTES,
    "Lecture Slides": MaterialType.SLIDES,
    "Readings": MaterialType.TEXTBOOK,
    "Quizzes": MaterialType.PAST_EXAM,
    "Exams": MaterialType.PAST_EXAM,
    "Assignments": MaterialType.ASSIGNMENT,
    "Problem Sets": MaterialType.ASSIGNMENT,
    "Practice Problems": MaterialType.PRACTICE_PROBLEM,
}

# OCW bölüm numarası → bölüm adı (yalnızca bilinenler; yoksa boş kalır).
DEPARTMENTS = {
    "6": "Electrical Engineering and Computer Science",
    "18": "Mathematics",
    "8": "Physics",
}

# Takvim sütun başlıkları (OCW İngilizce) → arayüz dili.
CALENDAR_COLUMNS = {
    "week": "Hafta",
    "ses #": "Oturum",
    "lec #": "Ders",
    "lectures": "Dersler",
    "topics": "Konular",
    "recitations": "Recitation",
    "problem sessions": "Problem oturumları",
    "key dates": "Önemli tarihler",
}

LICENSE_NOTE = "Kaynak: MIT OpenCourseWare (ocw.mit.edu), CC BY-NC-SA 4.0."


@dataclass(frozen=True)
class OcwFile:
    title: str
    material_type: MaterialType
    path: Path
    filename: str


@dataclass(frozen=True)
class OcwCourse:
    code: str
    name: str
    instructor_name: str | None
    term: str | None
    level: str | None
    department: str | None
    description: str | None


def read_course(root: Path) -> OcwCourse:
    data = _load(root / "data.json")
    instructors = ", ".join(i["title"] for i in data.get("instructors") or [] if i.get("title"))
    level = next(iter(data.get("level") or []), "").lower()
    department = next(
        (DEPARTMENTS[n] for n in data.get("department_numbers") or [] if n in DEPARTMENTS), None
    )
    term = " ".join(part for part in (data.get("term"), data.get("year")) if part)
    description = (data.get("course_description") or "").strip()
    return OcwCourse(
        code=data["primary_course_number"],
        name=data["course_title"],
        instructor_name=instructors or None,
        term=term or None,
        level=level if level in {"undergraduate", "graduate"} else None,
        department=department,
        description=f"{description}\n\n{LICENSE_NOTE}" if description else LICENSE_NOTE,
    )


def list_files(root: Path) -> list[OcwFile]:
    """Paketteki PDF'ler, bölümüne göre türüyle; başlık sırası doğal (Lecture 2 < Lecture 10)."""
    files: dict[str, OcwFile] = {}
    for meta_path in sorted((root / "resources").glob("*/data.json")):
        meta = _load(meta_path)
        if meta.get("file_type") != "application/pdf":
            continue
        material_type = _material_type(meta)
        if material_type is None:
            continue
        stored = Path(meta["file"]).name
        path = root / "static_resources" / stored
        title = meta["title"].strip()
        if not path.is_file() or title in files:
            continue
        # "477c…_MIT6_006S20_lec1.pdf" → "MIT6_006S20_lec1.pdf"
        filename = re.sub(r"^[0-9a-f]{32}_", "", stored)
        files[title] = OcwFile(title, material_type, path, filename)
    return sorted(files.values(), key=lambda f: (f.material_type.value, natural_key(f.title)))


def _material_type(meta: dict[str, Any]) -> MaterialType | None:
    section = meta.get("parent_title")
    if section in SECTION_TYPES:
        return SECTION_TYPES[section]
    # Bölümsüz yüklenmiş sınav dosyaları (ör. Quiz 3) kaynak türünden tanınır.
    if not section and "Exams" in (meta.get("learning_resource_types") or []):
        return MaterialType.PAST_EXAM
    return None


def natural_key(text: str) -> list[Any]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def read_syllabus(root: Path) -> list[dict[str, Any]] | None:
    html = _page_html(root, "syllabus")
    if html is None:
        return None
    return _HtmlBlocks.parse(html) or None


def read_calendar(root: Path) -> dict[str, Any] | None:
    """İlk tablo takvimdir: ilk satır sütun başlıkları, sonrakiler haftalar."""
    html = _page_html(root, "calendar")
    if html is None:
        return None
    blocks = _HtmlBlocks.parse(html, keep_cell_lines=True)
    table = next((b for b in blocks if b["type"] == "table"), None)
    if table is None or len(table["cells"]) < 2:
        return None
    header, *body = table["cells"]
    intro = " ".join(b["text"] for b in blocks if b["type"] == "paragraph") or None
    return {
        "intro": intro,
        "columns": [
            CALENDAR_COLUMNS.get(" ".join(c["lines"]).lower(), " ".join(c["lines"])) for c in header
        ],
        "rows": body,
    }


def _page_html(root: Path, name: str) -> str | None:
    path = root / "pages" / name / "data.json"
    if not path.is_file():
        return None
    return _load(path).get("content") or None


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


class _HtmlBlocks(HTMLParser):
    """OCW sayfa HTML'ini düz metin bloklarına çevirir: heading, paragraph, list, table.

    OCW tablolarında `<p>` etiketleri hücre sınırlarını aşar (geçersiz HTML); tablo içinde
    `<p>` yalnızca hücre içindeyse satır sonu sayılır, gerisi yok sayılır.
    """

    _HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self, keep_cell_lines: bool) -> None:
        super().__init__(convert_charrefs=True)
        self.keep_cell_lines = keep_cell_lines
        self.blocks: list[dict[str, Any]] = []
        self._text: list[str] | None = None
        self._kind: str | None = None
        self._list: list[str] | None = None
        self._table: list[list[dict[str, Any]]] | None = None
        self._row: list[dict[str, Any]] | None = None
        self._cell: dict[str, Any] | None = None

    @classmethod
    def parse(cls, html: str, keep_cell_lines: bool = False) -> list[dict[str, Any]]:
        parser = cls(keep_cell_lines)
        parser.feed(html)
        parser.close()
        parser._flush_text()
        return parser.blocks

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._flush_text()
            self._table = []
        elif self._table is not None:
            if tag == "tr":
                self._row = []
            elif tag in {"td", "th"} and self._row is not None:
                span = dict(attrs).get("colspan") or "1"
                self._cell = {"lines": [""], "span": int(span) if span.isdigit() else 1}
            elif tag in {"p", "br"} and self._cell is not None:
                self._cell["lines"].append("")
        elif tag in self._HEADINGS or tag == "p":
            self._flush_text()
            self._kind = "heading" if tag in self._HEADINGS else "paragraph"
            self._text = []
        elif tag in {"ul", "ol"}:
            self._flush_text()
            self._list = []
        elif tag == "li" and self._list is not None:
            self._kind = "item"
            self._text = []
        elif tag == "br" and self._text is not None:
            self._text.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if self._table is not None:
            if tag in {"td", "th"} and self._cell is not None and self._row is not None:
                lines = [_clean(line) for line in self._cell["lines"]]
                self._row.append(
                    {"lines": [line for line in lines if line], "span": self._cell["span"]}
                )
                self._cell = None
            elif tag == "tr" and self._row is not None:
                if self._row:
                    self._table.append(self._row)
                self._row = None
            elif tag == "table":
                self._add_table(self._table)
                self._table = None
        elif tag in self._HEADINGS or tag == "p" or tag == "li":
            self._flush_text()
        elif tag in {"ul", "ol"} and self._list is not None:
            self._flush_text()
            if self._list:
                self.blocks.append({"type": "list", "items": self._list})
            self._list = None

    def handle_data(self, data: str) -> None:
        if self._table is not None:
            if self._cell is not None:
                self._cell["lines"][-1] += data
        elif self._text is not None:
            self._text.append(data)

    def _flush_text(self) -> None:
        if self._text is None:
            return
        text = _clean("".join(self._text))
        if text:
            if self._kind == "item" and self._list is not None:
                self._list.append(text)
            elif self._kind in {"heading", "paragraph"}:
                self.blocks.append({"type": self._kind, "text": text})
        self._text = None
        self._kind = None

    def _add_table(self, rows: list[list[dict[str, Any]]]) -> None:
        if not rows:
            return
        if self.keep_cell_lines:
            self.blocks.append({"type": "table", "cells": rows})
        else:
            self.blocks.append(
                {"type": "table", "rows": [[" ".join(c["lines"]) for c in row] for row in rows]}
            )


def _clean(text: str) -> str:
    return " ".join(text.split())
