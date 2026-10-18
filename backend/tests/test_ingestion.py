"""Materyal yükleme modülü: parser'lar, temizleme, parçalama (veritabanı gerektirmez)."""

from pathlib import Path

from app.ingestion.chunking import chunk_segments, estimate_tokens
from app.ingestion.cleaning import clean_segments
from app.ingestion.parsers.pdf_parser import parse_pdf
from app.ingestion.parsers.pptx_parser import parse_pptx
from app.ingestion.types import RawSegment
from tests.conftest import SAMPLE_PAGES, make_pdf, make_pptx


def test_parse_pdf_returns_one_segment_per_page_with_page_numbers(sample_pdf: Path) -> None:
    segments = parse_pdf(sample_pdf)

    assert [s.page for s in segments] == [1, 2, 3]
    assert "Ikili arama sirali" in segments[0].text
    assert "sag yari elenir" in segments[1].text


def test_parse_pdf_keeps_empty_pages_so_page_count_is_correct(tmp_path: Path) -> None:
    path = make_pdf(tmp_path / "bos.pdf", [("", ""), ("Baslik", "Icerik")])

    segments = parse_pdf(path)

    assert [s.page for s in segments] == [1, 2]
    assert segments[0].text.strip() == "1"


def test_parse_pptx_reads_title_body_and_notes_with_slide_numbers(sample_pptx: Path) -> None:
    segments = parse_pptx(sample_pptx)

    assert [s.page for s in segments] == [1, 2, 3]
    assert segments[1].text.startswith("Neden yariyi atabiliriz")
    assert "sag yari elenir" in segments[1].text
    assert "Not: Neden yariyi atabiliriz" in segments[1].text


def test_parse_pptx_handles_turkish_characters(tmp_path: Path) -> None:
    path = make_pptx(tmp_path / "tr.pptx", [("İkili Arama", "Sıralı dizide ağaç, şu, ğ")])

    assert "İkili Arama\nSıralı dizide ağaç, şu, ğ" in parse_pptx(path)[0].text


def test_cleaning_removes_repeated_header_and_page_numbers(sample_pdf: Path) -> None:
    segments = parse_pdf(sample_pdf) + parse_pdf(sample_pdf)  # 6 sayfa, her birinde aynı üst bilgi

    cleaned = clean_segments(segments)

    assert len(cleaned) == 6
    for segment in cleaned:
        assert "BLM2512" not in segment.text
        assert not any(line.strip().isdigit() for line in segment.text.split("\n"))


def test_cleaning_keeps_section_title_repeated_on_some_pages() -> None:
    segments = [RawSegment(text=f"Ikili Arama\nicerik {i}", page=i) for i in range(1, 4)]
    segments += [RawSegment(text=f"Siralama\nicerik {i}", page=i) for i in range(4, 7)]

    cleaned = clean_segments(segments)

    assert all(s.text.split("\n")[0] in {"Ikili Arama", "Siralama"} for s in cleaned)


def test_cleaning_drops_empty_pages_and_fixes_pdf_hyphens() -> None:
    segments = [
        RawSegment(text="   \n\n", page=1),
        RawSegment(text="hi = n ­ 1\nalgo-\nritma  ve   kelime", page=2),
    ]

    cleaned = clean_segments(segments)

    assert len(cleaned) == 1
    assert cleaned[0].page == 2
    assert cleaned[0].text == "hi = n - 1\nalgoritma ve kelime"


def test_short_page_becomes_single_chunk_with_its_page() -> None:
    chunks = chunk_segments([RawSegment(text="Kisa bir sayfa.", page=7)])

    assert len(chunks) == 1
    assert chunks[0].page == 7
    assert chunks[0].text == "Kisa bir sayfa."


def test_long_page_is_split_under_token_limit_without_crossing_pages() -> None:
    sentence = "Ikili arama her adimda arama araligini yariya indirir. "
    long_page = RawSegment(text=(sentence * 120).strip(), page=3)
    next_page = RawSegment(text="Sonraki sayfa.", page=4)

    chunks = chunk_segments([long_page, next_page], max_tokens=100, overlap_tokens=20)

    page3 = [c for c in chunks if c.page == 3]
    assert len(page3) > 1
    assert all(estimate_tokens(c.text) <= 100 for c in page3)
    assert chunks[-1].page == 4 and chunks[-1].text == "Sonraki sayfa."


def test_consecutive_chunks_overlap() -> None:
    sentences = [f"Cumle numarasi {i} burada biter." for i in range(60)]
    chunks = chunk_segments(
        [RawSegment(text=" ".join(sentences), page=1)], max_tokens=60, overlap_tokens=20
    )

    assert len(chunks) > 2
    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert previous.text.split("\n")[-1] in current.text


def test_sample_material_end_to_end_produces_one_chunk_per_page(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "a.pdf", SAMPLE_PAGES * 2, header="Ders Notlari")

    chunks = chunk_segments(clean_segments(parse_pdf(pdf)))

    assert [c.page for c in chunks] == [1, 2, 3, 4, 5, 6]
    assert all("Ders Notlari" not in c.text for c in chunks)
