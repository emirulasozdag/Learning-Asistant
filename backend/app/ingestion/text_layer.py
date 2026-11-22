"""PDF metin katmanının sağlamlık denetimi ve bozuk sayfanın OCR ile okunması.

Bazı PDF'lerde (ör. eski LaTeX/dvips çıktıları, Type3 yazı tipleri) yazı tipinin karakter
kodlaması bozuktur: sayfa ekranda doğru görünür ama çıkarılan metin anlamsız işaretlere
(`@BA?CD4FEHGJIJ2K`) döner ya da noktalama, sembol ve rakamlar hiç çıkmaz. Böyle metin
olduğu gibi indekse girerse aranamaz, alıntılanamaz.

İki belirti ölçülür (`text_quality`):

- **Bozuk** (`garbled`): kelimelerin (karakter ağırlıklı) en az `MAX_GARBLED_SHARE` kadarı
  bozuk kodlama izi taşıyor. İz: kelimenin içinde `? @ $ & `` ` işareti, büyük harf öbeğine
  gömülü rakam (`IJ2K`, `C5IJ`) ya da `\\ufffd`. Gerçek metinde bunlar seyrektir: 18.06 ve
  6.006 paketlerindeki 2.925 sayfada temiz sayfaların payı en çok 0,03; bozuk üç sayfanınki
  0,46–0,57. Kod (`self.A[h]`), formül (`L1D1U1`), `R^n` ve adresler bu iz
  sayılmaz.
- **Sembolsüz** (`symbols_missing`): uzun metinde (`MIN_LETTERS_FOR_SYMBOL_CHECK` harf) neredeyse
  hiç noktalama yok (`MIN_PUNCTUATION_RATIO`). Düzyazıda her ~30 harfe bir nokta, virgül ya da
  parantez düşer; ölçülen en düşük temiz sayfa oranı 0,009, sembolleri kaybolmuş sayfalarınki
  0–0,001.

Bozuk ya da sembolsüz sayfa yüksek çözünürlükte görüntüye çevrilip Tesseract ile okunur
(`repair_pages`). OCR metni yalnızca daha iyiyse alınır:

- bozuk sayfada OCR metni bozuk olmamalı; olmazsa (ya da OCR çalışmazsa) sayfa **aramaya
  alınmaz** ve uyarı yazılır: anlamsız metin indekse girmez.
- sembolsüz sayfada OCR metni noktalama içermeli ve çıkarılan kelimelerin çoğunu
  (`MIN_WORD_RECALL`) bulmalı; olmazsa çıkarılan metin uyarıyla kalır (kelimeleri aranabilir).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import pymupdf

from app.ingestion.ocr import OcrError, OcrResult, read_png
from app.ingestion.types import RawSegment

# Karakter ağırlıklı bozuk kelime payı bu eşikten büyük ya da eşitse sayfa bozuk sayılır.
MAX_GARBLED_SHARE = 0.2
# Bundan az kelimeli sayfada oran güvenilmez (bir iki tuhaf kelime sayfayı bozuk göstermesin).
MIN_WORDS_FOR_CHECK = 10
# Noktalama denetimi yalnızca en az bu kadar harfli sayfada yapılır (kısa slaytta noktalama
# olmaması doğaldır).
MIN_LETTERS_FOR_SYMBOL_CHECK = 300
# Noktalama işaretlerinin harflere oranı bunun altındaysa semboller kaybolmuş sayılır.
MIN_PUNCTUATION_RATIO = 0.005
# Sembolsüz sayfanın OCR metni, çıkarılan kelimelerin en az bu payını içermeli.
MIN_WORD_RECALL = 0.6
# OCR çözünürlüğü (Tesseract ~300 dpi'da iyi okur; 18.06 sayfası ~1,5 sn).
OCR_DPI = 300
# Bir dokümanda OCR'a gönderilecek en çok sayfa: yükleme süresi sınırsız uzamasın.
MAX_OCR_PAGES = 30

_STRIP = "\"'“”‘’()[]{}.,;:!?…«»*•–—-"
_ODD_INSIDE = re.compile(r"(?<=.)[?@$&`](?=.)")
# Büyük harf öbeğine gömülü rakam (`IJ2K`, `C5IJ`); matris adları (`L1D1U1`, `Q1R1`) değil.
_UPPER_DIGIT_LETTER = re.compile(r"[A-Z]{2,}\d[^\W\d_]|[A-Z]\d[A-Z]{2,}")
_PUNCTUATION = set(".,;:!?()")
_LETTER_WORD = re.compile(r"[^\W\d_]{3,}")

PageReader = Callable[[bytes, str], OcrResult]


@dataclass(frozen=True)
class TextQuality:
    words: int
    garbled_share: float
    letters: int
    punctuation: int

    @property
    def garbled(self) -> bool:
        return self.words >= MIN_WORDS_FOR_CHECK and self.garbled_share >= MAX_GARBLED_SHARE

    @property
    def symbols_missing(self) -> bool:
        return (
            self.letters >= MIN_LETTERS_FOR_SYMBOL_CHECK
            and self.punctuation < self.letters * MIN_PUNCTUATION_RATIO
        )


def text_quality(text: str) -> TextQuality:
    """Çıkarılan sayfa metninin bozukluk ölçüleri (bkz. modül açıklaması)."""
    words = [
        token for token in text.split() if "�" in token or any(char.isalnum() for char in token)
    ]
    garbled = [token for token in words if _is_garbled(token)]
    total = sum(map(len, words))
    return TextQuality(
        words=len(words),
        garbled_share=sum(map(len, garbled)) / total if total else 0.0,
        letters=sum(char.isalpha() for char in text),
        punctuation=sum(char in _PUNCTUATION for char in text),
    )


def _is_garbled(token: str) -> bool:
    if "�" in token:
        return True
    if "://" in token or token.startswith("www."):
        return False  # Adresteki ? ve & bozukluk değil.
    core = token.strip(_STRIP)
    return bool(_ODD_INSIDE.search(core) or _UPPER_DIGIT_LETTER.search(core))


def repair_pages(
    path: Path, segments: list[RawSegment], languages: str, read: PageReader | None = None
) -> list[RawSegment]:
    """Metin katmanı bozuk ya da sembolsüz sayfaları OCR ile okur; bkz. modül açıklaması.

    `segments` `parse_pdf` çıktısıdır (sayfa başına bir segment). Sağlam sayfalar olduğu gibi
    döner; PDF yalnızca onarılacak sayfa varsa açılır. `read` testte sahte OCR içindir.
    """
    read = read or read_png
    suspects = {
        index: quality
        for index, segment in enumerate(segments)
        if segment.page is not None
        and ((quality := text_quality(segment.text)).garbled or quality.symbols_missing)
    }
    if not suspects:
        return segments
    repaired = list(segments)
    with pymupdf.open(path) as pdf:
        for count, (index, quality) in enumerate(suspects.items()):
            segment = segments[index]
            ocr, reason = None, " (sayfa sınırı aşıldı)"
            if count < MAX_OCR_PAGES:
                try:
                    pixmap = pdf[segment.page - 1].get_pixmap(
                        dpi=OCR_DPI, colorspace=pymupdf.csGRAY
                    )
                    ocr, reason = read(pixmap.tobytes("png"), languages), ""
                except OcrError:
                    reason = " (OCR çalışmadı)"
            repaired[index] = _decide(segment, quality, ocr, reason)
    return repaired


def _decide(
    segment: RawSegment, quality: TextQuality, ocr: OcrResult | None, reason: str
) -> RawSegment:
    page = segment.page
    text = ocr.text if ocr is not None and ocr.text else ""
    if quality.garbled:
        if text and not text_quality(text).garbled:
            return _with_ocr_text(
                segment,
                text,
                f"Sayfa {page}: PDF'in metin katmanı bozuk (yazı tipi kodlaması); sayfa metni "
                "görüntüden OCR ile okundu. Formül ve semboller eksik olabilir; kaynak "
                "sayfayla karşılaştırın.",
            )
        return replace(
            segment,
            text="",
            margin_lines={},
            warnings=[
                *segment.warnings,
                f"Sayfa {page}: PDF'in metin katmanı bozuk (yazı tipi kodlaması) ve OCR ile "
                f"okunamadı{reason}; sayfa aramaya alınmadı.",
            ],
        )
    if text:
        if not _has_punctuation(text):
            return segment  # Görüntüde de noktalama yok: sayfa gerçekten böyle.
        if _word_recall(segment.text, text) >= MIN_WORD_RECALL:
            return _with_ocr_text(
                segment,
                text,
                f"Sayfa {page}: PDF'in metin katmanında noktalama, sembol ve rakamlar eksikti "
                "(yazı tipi kodlaması); sayfa metni görüntüden OCR ile okundu. Formül ve kodu "
                "kaynak sayfayla karşılaştırın.",
            )
        reason = " (OCR metni sayfayla örtüşmedi)"
    return replace(
        segment,
        warnings=[
            *segment.warnings,
            f"Sayfa {page}: Metinde noktalama, sembol ve rakamlar eksik görünüyor (yazı tipi "
            f"kodlaması) ve OCR ile düzeltilemedi{reason}; bu sayfadaki formül ve kodu kaynak "
            "sayfayla karşılaştırın.",
        ],
    )


def _has_punctuation(text: str) -> bool:
    quality = text_quality(text)
    return quality.punctuation >= quality.letters * MIN_PUNCTUATION_RATIO


def _word_recall(extracted: str, ocr_text: str) -> float:
    """Çıkarılan metnin (3+ harfli) kelimelerinden OCR metninde de geçenlerin payı."""
    expected = {word.lower() for word in _LETTER_WORD.findall(extracted)}
    found = {word.lower() for word in _LETTER_WORD.findall(ocr_text)}
    return len(expected & found) / len(expected) if expected else 0.0


def _with_ocr_text(segment: RawSegment, text: str, warning: str) -> RawSegment:
    # OCR metninin satırları PDF satırlarıyla eşleşmez: kenar boşluğu kanıtı (margin_lines) atılır.
    return replace(segment, text=text, margin_lines={}, warnings=[*segment.warnings, warning])
