"""Bozuk PDF metin katmanı: ölçüt ve OCR'a düşme (veritabanı gerektirmez).

Örnek bozuk metinler MIT OCW 18.06 "Gram-Schmidt in 9 lines of MATLAB" ve "MATLAB Tutorial"
PDF'lerinin PyMuPDF çıktısından alındı (yazı tipi kodlaması bozuk; sayfa ekranda doğru görünür).
"""

import shutil
from pathlib import Path

import pymupdf
import pytest

from app.ingestion import text_layer
from app.ingestion.ocr import OcrError, OcrResult
from app.ingestion.parsers.pdf_parser import parse_pdf
from app.ingestion.text_layer import repair_pages, text_quality
from app.ingestion.types import RawSegment
from tests.conftest import make_pdf

# 18.06 Gram-Schmidt, sayfa 1 (font kodlaması bozuk).
GARBLED = (
    "!#\"   $&%'($*) n a1, . . . , an+-,/.1032547698;:=<>,?6A "
    "@BA?CD4FEHGJIJ2K@BCL,/6NMKC>4F2KC5MPOn "
    "@QC5, @HR?A/.q1, . ST.. . ,R/A?.qn RUCWV7. <XC5IJ2KM Q C5,?.Z< IJEH[?6 qjR/MI7\\ "
    "C`S/2LIaA/[/< M IJ2;C5,/I7R/IJ2L6 47EbV7. CLIJ2LM C5,/.c< IJEB[/6cR/Mq IF\\ +dIfegR/A aj"
)
# 18.06 MATLAB Tutorial, sayfa 1: kelimeler doğru, noktalama/sembol/rakamlar kaybolmuş.
SYMBOLLESS = (
    "MATLAB Tutorial\n\nYou need a small numb e r of basic commands to start using MATLAB This "
    "short tutorial\ndescrib es those fundamental commands You need to create vectors and "
    "matrices to change\nthem and to operate with them Those are all short high level commands "
    "b ecause MATLAB\nconstantly works with matrices  I b elieve t h a t you will like t h e "
    "p ower that this software gives\nto do linear algebra by a series of short instructions\n"
    "The word eye stands for the identity matrix The submatrix u E picks out column The "
    "instruction resets the entry to The command E u multiplies the matrices"
)
SYMBOLLESS_OCR = (
    "MATLAB Tutorial\nYou need a small number of basic commands to start using MATLAB. This "
    "short tutorial\ndescribes those fundamental commands. You need to create vectors and "
    "matrices, to change\nthem, and to operate with them. Those are all short high-level "
    "commands, because MATLAB\nconstantly works with matrices. I believe that you will like the "
    "power that this software gives,\nto do linear algebra by a series of short instructions:\n"
    "E = eye(3) u = E(:,1) E(3,1) = 5 v = E*u\nThe word eye stands for the identity matrix. "
    "The submatrix u = E(:,1) picks out column 1."
)
CLEAN_OCR = "Gram-Schmidt in 9 Lines of MATLAB\nThe Gram-Schmidt algorithm starts with n vectors."


@pytest.mark.parametrize(
    "text",
    [
        GARBLED,
        # 18.06 "symmbases" sayfa 1.
        "M$&%('*)+'-,/. 78)+9;: <#=?>@)+5A, :D78>C)E<+FG,/: $&%I'J<K2L5 5M'D78)K9N:O56, "
        "=?>C)+5 2@>CSU,/V(VW7YXZ>4<[2L5M5 5M,/78)K9N: >C)O5]SI.;789;F(.;2^132_)+' a b c",
        "��� �� " * 6,
    ],
)
def test_garbled_font_encoding_is_recognized(text: str) -> None:
    assert text_quality(text).garbled


@pytest.mark.parametrize(
    "text",
    [
        "The Gram-Schmidt algorithm starts with n independent vectors (the columns of A). "
        "It produces n orthonormal vectors, the columns of Q.",
        "İkili arama sıralı bir dizide hedef değeri arar. Her adımda ortadaki eleman hedefle "
        "karşılaştırılır; böylece arama alanı yarıya iner.",
        # Kod, formül ve adres bozukluk değildir (6.006 ve 18.06'dan).
        "def delete(self, k): return self.A[h].delete(k) if len(self.A) else None "
        "for i in range(len(Adj)): d[s] = float('inf') # O(1)",
        "L1D1U1 = L2D2U2 so D1U1U−1 = L1−1L2D2 and R^n R^3? R^2. T2(T1x) = (T2T1)x x^2 + y^2",
        "See https://www.youtube.com/watch?v=lEZPfmGCEk0&t=10 and mail@example.com for details "
        "about this lecture on the four fundamental subspaces of a matrix today.",
        "a1 a2",  # Çok kısa: ölçülmez.
    ],
)
def test_clean_text_code_and_math_are_not_garbled(text: str) -> None:
    assert not text_quality(text).garbled


def test_missing_punctuation_is_recognized_only_on_long_text() -> None:
    assert text_quality(SYMBOLLESS).symbols_missing
    assert not text_quality(SYMBOLLESS_OCR).symbols_missing
    # Kısa slayt maddelerinde noktalama olmaması doğaldır.
    assert not text_quality("Ikili Arama\nSirali dizi\nOrtadaki eleman\nLog n adim").symbols_missing


def ocr_returning(text: str | None, calls: list[int] | None = None):
    def read(png: bytes, languages: str) -> OcrResult:
        assert png.startswith(b"\x89PNG")
        if calls is not None:
            calls.append(len(png))
        if text is None:
            raise OcrError("Tesseract çalıştırılamadı.")
        return OcrResult(status="readable", text=text, confidence=0.95)

    return read


@pytest.fixture
def two_page_pdf(tmp_path: Path) -> Path:
    return make_pdf(tmp_path / "iki.pdf", [("Bir", "birinci sayfa"), ("Iki", "ikinci sayfa")])


def test_clean_pages_are_not_sent_to_ocr(two_page_pdf: Path) -> None:
    calls: list[int] = []
    segments = parse_pdf(two_page_pdf)

    assert repair_pages(two_page_pdf, segments, "eng", ocr_returning("x", calls)) is segments
    assert calls == []


def test_garbled_page_is_replaced_by_ocr_text(two_page_pdf: Path) -> None:
    segments = [
        RawSegment(text=GARBLED, page=1, margin_lines={0: (0.1, 0.0)}),
        RawSegment(text="ikinci sayfa", page=2),
    ]

    repaired = repair_pages(two_page_pdf, segments, "eng", ocr_returning(CLEAN_OCR))

    assert repaired[0].text == CLEAN_OCR
    assert repaired[0].margin_lines == {}
    assert "metin katmanı bozuk" in repaired[0].warnings[0]
    assert "OCR ile okundu" in repaired[0].warnings[0]
    assert repaired[1] is segments[1]


@pytest.mark.parametrize(
    ("ocr_text", "reason"), [(None, "OCR çalışmadı"), (GARBLED, "OCR ile okunamadı")]
)
def test_garbled_page_without_usable_ocr_is_not_indexed(
    two_page_pdf: Path, ocr_text: str | None, reason: str
) -> None:
    segments = [RawSegment(text=GARBLED, page=1), RawSegment(text="ikinci sayfa", page=2)]

    repaired = repair_pages(two_page_pdf, segments, "eng", ocr_returning(ocr_text))

    assert repaired[0].text == ""
    assert reason in repaired[0].warnings[0]
    assert "aramaya alınmadı" in repaired[0].warnings[0]


def test_symbolless_page_takes_ocr_text_when_it_restores_symbols(two_page_pdf: Path) -> None:
    segments = [RawSegment(text=SYMBOLLESS, page=1)]

    repaired = repair_pages(two_page_pdf, segments, "eng", ocr_returning(SYMBOLLESS_OCR))

    assert repaired[0].text == SYMBOLLESS_OCR
    assert "noktalama, sembol ve rakamlar eksikti" in repaired[0].warnings[0]


def test_symbolless_page_keeps_its_words_when_ocr_fails_or_does_not_match(
    two_page_pdf: Path,
) -> None:
    segments = [RawSegment(text=SYMBOLLESS, page=1)]
    unrelated = "Completely different page. Nothing in common, at all; (really)."

    for read in (ocr_returning(None), ocr_returning(unrelated)):
        repaired = repair_pages(two_page_pdf, segments, "eng", read)

        assert repaired[0].text == SYMBOLLESS
        assert "OCR ile düzeltilemedi" in repaired[0].warnings[0]


def test_page_without_punctuation_in_the_image_too_is_left_alone(two_page_pdf: Path) -> None:
    segments = [RawSegment(text=SYMBOLLESS, page=1)]
    same_without_punctuation = SYMBOLLESS.replace("numb e r", "number")

    repaired = repair_pages(two_page_pdf, segments, "eng", ocr_returning(same_without_punctuation))

    assert repaired[0] is segments[0]


def test_ocr_page_limit_bounds_upload_time(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(text_layer, "MAX_OCR_PAGES", 2)
    path = make_pdf(tmp_path / "uc.pdf", [("A", "a"), ("B", "b"), ("C", "c")])
    segments = [RawSegment(text=GARBLED, page=page) for page in (1, 2, 3)]
    calls: list[int] = []

    repaired = repair_pages(path, segments, "eng", ocr_returning(CLEAN_OCR, calls))

    assert len(calls) == 2
    assert [segment.text for segment in repaired] == [CLEAN_OCR, CLEAN_OCR, ""]
    assert "sayfa sınırı aşıldı" in repaired[2].warnings[0]


def make_garbled_pdf(path: Path, visible: list[str], hidden: str) -> Path:
    """Görünen yazısı resim, metin katmanı görünmez bozuk metin olan sayfa + temiz bir sayfa:
    bozuk yazı tipi kodlamalı PDF'in davranışı (ekranda doğru, çıkarımda anlamsız)."""
    source = pymupdf.open()
    drawn = source.new_page()
    drawn.insert_textbox(pymupdf.Rect(50, 60, 545, 400), "\n".join(visible), fontsize=14)
    image = drawn.get_pixmap(dpi=200)
    document = pymupdf.open()
    page = document.new_page()
    page.insert_image(page.rect, pixmap=image)
    words = hidden.split()
    lines = [" ".join(words[i : i + 6]) for i in range(0, len(words), 6)]
    page.insert_text((50, 500), lines, fontsize=9, render_mode=3)  # görünmez metin
    clean = document.new_page()
    clean.insert_textbox(
        pymupdf.Rect(50, 60, 545, 400), "Orthogonal matrices keep lengths.", fontsize=12
    )
    document.save(path)
    return path


VISIBLE = [
    "Gram-Schmidt in nine lines of MATLAB",
    "The algorithm starts with independent vectors",
    "and produces orthonormal vectors.",
]


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract yalnızca Docker imajında")
def test_real_tesseract_reads_page_whose_text_layer_is_garbled(tmp_path: Path) -> None:
    path = make_garbled_pdf(tmp_path / "bozuk.pdf", VISIBLE, GARBLED)
    segments = parse_pdf(path)
    assert text_quality(segments[0].text).garbled

    repaired = repair_pages(path, segments, "eng")

    # Tesseract tek tük harf karıştırabilir ("Schmict"); kelimelerin çoğu doğru okunmalı.
    for word in ("MATLAB", "algorithm", "independent", "orthonormal", "vectors"):
        assert word in repaired[0].text
    assert not text_quality(repaired[0].text).garbled
    assert repaired[1] is segments[1]
