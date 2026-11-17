"""Video kareleri: sahne takibi ve OCR durum kuralları (#24, ADR-10). Veritabanı ve video yok.

Parmak izleri yapay gri baytlardır (16x8); gerçek videoyla uçtan uca test `test_frames_real.py`.
"""

from pathlib import Path

import pytest

from app.core.config import settings
from app.ingestion.documents import document_files, frame_dir, remove_paths
from app.ingestion.frames import FrameParams, SceneTracker, _samples, changed_pixels, dilate
from app.ingestion.ocr import (
    MIN_SHORT_WORD_CONFIDENCE,
    MIN_WORD_CONFIDENCE,
    OcrError,
    Word,
    best_reading,
    classify,
    parse_tsv,
    read_image,
    tesseract_languages,
)

W, H = 16, 8
PARAMS = FrameParams(
    sample_interval_s=0.5,
    signature_size=(W, H),
    pixel_threshold=16,
    stable_ratio=0.03,  # 16x8'de 4 piksel
    min_stable_s=2.0,
    merge_gap_s=10.0,
    motion_margin=1,
)


def image(*rows_with_ink: int, shade: int = 0, extra: dict[int, int] | None = None) -> bytes:
    """Beyaz zemin; verilen satırlar koyu (bir "yazı satırı"). `extra`: piksel → gri ton."""
    pixels = bytearray([255] * (W * H))
    for row in rows_with_ink:
        for x in range(2, W - 2):
            pixels[row * W + x] = shade
    for index, value in (extra or {}).items():
        pixels[index] = value
    return bytes(pixels)


def feed(tracker: SceneTracker, timeline: list[tuple[float, bytes]], start: float = 0.0):
    """(süre, görüntü) listesini 0,5 sn örneklerle besler; kaydedilecek sahnelerin anları."""
    captured = []
    t = start
    for seconds, picture in timeline:
        for _ in range(round(seconds / PARAMS.sample_interval_s)):
            scene = tracker.feed(t, picture)
            if scene is not None:
                captured.append((scene.index, t))
            t += PARAMS.sample_interval_s
    return captured, t


def scenes(timeline, end: float | None = None, params: FrameParams = PARAMS):
    tracker = SceneTracker(params)
    captured, t = feed(tracker, timeline)
    result = tracker.finish(end if end is not None else t)
    return [(s.index, s.t_start, s.t_end, s.t_frame) for s in result], captured, tracker


def webcam(frame: int) -> dict[int, int]:
    """Sağ alt 3x3 köşede her örnekte değişen piksel deseni (konuşmacı kamerası)."""
    corner = [(y * W + x) for y in range(H - 3, H) for x in range(W - 3, W)]
    return {index: (frame * 70 + i * 40) % 256 for i, index in enumerate(corner)}


# --- sahne takibi -----------------------------------------------------------------------------


def test_slides_become_scenes_with_the_interval_they_were_on_screen() -> None:
    result, captured, _ = scenes([(4, image(1)), (5, image(4)), (3, image(6))])

    # Kare sabitlikten 2 sn sonra alınır; sahne değişikliğin ilk görüldüğü ana kadar sürer.
    assert result == [(0, 0.0, 4.0, 2.0), (1, 4.0, 9.0, 6.0), (2, 9.0, 12.0, 11.0)]
    assert captured == [(0, 2.0), (1, 6.0), (2, 11.0)]


def test_last_scene_lasts_until_the_end_of_the_video() -> None:
    result, _, _ = scenes([(4, image(1))], end=4.8)

    assert result == [(0, 0.0, 4.8, 2.0)]


def test_a_slide_shorter_than_the_stable_time_is_skipped() -> None:
    result, _, _ = scenes([(4, image(1)), (1.5, image(3)), (4, image(5))])

    assert [(s[1], s[2]) for s in result] == [(0.0, 4.0), (5.5, 9.5)]


def test_continuous_motion_produces_no_scene() -> None:
    moving = [(0.5, bytes((i * 37 + f * 101) % 256 for i in range(W * H))) for f in range(20)]

    result, captured, _ = scenes(moving)

    assert result == [] and captured == []


def test_a_slide_with_a_moving_webcam_corner_is_still_one_scene() -> None:
    timeline = [(0.5, image(1, extra=webcam(f))) for f in range(12)]
    timeline += [(0.5, image(4, extra=webcam(f))) for f in range(12, 24)]

    result, _, _ = scenes(timeline)

    # Kamera kutusu ilk saniyelerde hareketli bölge olarak öğrenilir; sonra slaytlar ayrılır.
    assert len(result) == 2
    assert result[0][2] == result[1][1] == 6.0
    assert result[1][2] == 12.0


def test_adding_one_line_to_a_slide_is_a_new_scene() -> None:
    result, _, _ = scenes([(4, image(1)), (4, image(1, 3)), (4, image(1, 3, 5))])

    assert [(s[1], s[2]) for s in result] == [(0.0, 4.0), (4.0, 8.0), (8.0, 12.0)]


def test_returning_to_the_same_slide_after_a_short_interruption_extends_the_scene() -> None:
    interruption = bytes((i * 53) % 256 for i in range(W * H))

    result, captured, _ = scenes([(4, image(1)), (1, interruption), (4, image(1))])

    assert result == [(0, 0.0, 9.0, 2.0)]
    assert captured == [(0, 2.0)]  # İkinci kez kaydedilmez.


def test_a_different_slide_in_between_keeps_both_occurrences() -> None:
    result, _, _ = scenes([(4, image(1)), (4, image(4)), (4, image(1))])

    assert [(s[1], s[2]) for s in result] == [(0.0, 4.0), (4.0, 8.0), (8.0, 12.0)]


def test_same_slide_after_a_long_gap_is_a_new_scene() -> None:
    noise = [(0.5, bytes((i * 37 + f * 101) % 256 for i in range(W * H))) for f in range(24)]

    result, _, _ = scenes([(4, image(1)), *noise, (4, image(1))])

    assert len(result) == 2


def test_frame_limit_stops_new_scenes_and_is_reported() -> None:
    params = FrameParams(**{**PARAMS.__dict__, "max_frames": 2})

    result, _, tracker = scenes([(3, image(1)), (3, image(3)), (3, image(5))], params=params)

    assert len(result) == 2 and tracker.limit_reached


def test_scene_times_are_ordered() -> None:
    result, _, _ = scenes([(2.5, image(r)) for r in range(H)] * 2)

    for _, t_start, t_end, t_frame in result:
        assert t_start <= t_frame <= t_end
    assert all(a[2] <= b[1] for a, b in zip(result, result[1:], strict=False))


def test_changed_pixels_counts_only_differences_above_the_threshold() -> None:
    a = bytes([0, 100, 200, 255])
    b = bytes([10, 140, 200, 0])

    assert changed_pixels(a, b, 16) == 0b1010
    with pytest.raises(ValueError):
        changed_pixels(a, b[:2], 16)


def test_dilate_grows_a_pixel_into_its_neighbourhood_without_wrapping_rows() -> None:
    width, height = 4, 3
    corner = 1 << (0 * width + 3)  # ilk satırın son pikseli

    grown = dilate(corner, width, height, 1)

    pixels = {i for i in range(width * height) if grown >> i & 1}
    assert pixels == {2, 3, 6, 7}  # sonraki satırın başına taşmaz
    assert dilate(0, width, height, 2) == 0


# --- OCR ------------------------------------------------------------------------------------


def words(*items: tuple[str, float], line: int = 1) -> list[Word]:
    return [Word(text, conf, (1, 1, line)) for text, conf in items]


def test_confident_words_become_text_in_line_order() -> None:
    result = classify(
        words(("mid", 95), ("=", 90), ("(lo", 92), ("+", 88), ("hi)", 93), line=2)
        + words(("İkili", 96), ("Arama", 97), line=1)
    )

    assert result.status == "readable"
    assert result.text == "İkili Arama\nmid = (lo + hi)"
    assert result.confidence == pytest.approx(0.946, abs=0.001)


def test_low_confidence_words_are_not_guessed() -> None:
    result = classify(words(("Dijkstra", 91), ("anak", 49), ("Çöl", 14)))

    assert result.status == "partial"
    assert result.text == "Dijkstra"
    assert "anak" not in result.text


def test_frame_with_only_unreadable_words_is_unreadable() -> None:
    result = classify(words(("aa", 20), ("bb", 30), ("cc", 40)))

    assert (result.status, result.text, result.confidence) == ("unreadable", None, None)


def test_frame_without_text_is_no_text() -> None:
    assert classify([]).status == "no_text"
    # Kutu kenarı ve çizgi gürültüsü yazı sayılmaz.
    noise = classify(words(("|", 46), ("—", 80), ("x", 10)))
    assert (noise.status, noise.text) == ("no_text", None)


def test_symbols_alone_do_not_make_a_frame_readable() -> None:
    assert classify(words(("——>", 95), ("|", 90))).status == "no_text"


def test_threshold_is_inclusive() -> None:
    assert classify(words(("tam", MIN_WORD_CONFIDENCE))).status == "readable"


def test_short_pieces_need_higher_confidence() -> None:
    """Gerçek derste Σ "2" (%64) okunmuştu: kısa parça orta güvenle metne girmez."""
    result = classify(
        words(("2", 64), ("deg(v)", 92), ("=", 87), ("2|E|", 87), ("x:", 95), ("—", 79))
    )

    assert result.text == "deg(v) = 2|E| x:"
    assert classify(words(("2", MIN_SHORT_WORD_CONFIDENCE))).text == "2"


def test_the_reading_with_more_confident_words_is_chosen() -> None:
    gray = words(("Dijkstra", 91))
    binary = words(("Dijkstra", 91), ("Kaynak", 95), ("Kuyruk", 95), ("Hedef", 89))
    noisy = words(("Dijkstra", 91), ("aa", 20), ("bb", 30), ("cc", 40), ("dd", 45))

    assert best_reading([gray, binary]) == binary
    assert best_reading([noisy, gray]) == noisy  # eşit sayıda okunan: güveni toplamı eşit, ilki
    assert best_reading([words(("x", 70)), words(("x", 90))]) == words(("x", 90))
    assert best_reading([]) == []


def test_parse_tsv_keeps_words_and_skips_layout_rows() -> None:
    header = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf"
        "\ttext"
    )
    tsv = "\n".join(
        [
            header,
            "1\t1\t0\t0\t0\t0\t0\t0\t1280\t720\t-1\t",
            "5\t1\t1\t1\t1\t1\t80\t70\t200\t44\t91.5\tDijkstra",
            "5\t1\t1\t1\t2\t1\t80\t170\t40\t30\t-1\t ",
            '5\t1\t2\t1\t1\t1\t80\t270\t40\t30\t88\t"x"',
        ]
    )

    assert parse_tsv(tsv) == [
        Word("Dijkstra", 91.5, (1, 1, 1)),
        Word('"x"', 88.0, (2, 1, 1)),
    ]


def test_parse_tsv_skips_malformed_rows() -> None:
    header = "level\tblock_num\tpar_num\tline_num\tconf\ttext"
    tsv = "\n".join([header, "5\tx\t1\t1\t90\tbozuk", "5\t1\t1\t1\t90\tsağlam", "5\t1\t1"])

    assert parse_tsv(tsv) == [Word("sağlam", 90.0, (1, 1, 1))]


def test_an_image_that_cannot_be_opened_is_an_ocr_error(tmp_path: Path) -> None:
    """Bozuk kare görüntüsü dokümanı başarısız yapmamalı: kare adımı `OcrError`u yakalar."""
    broken = tmp_path / "0.png"
    broken.write_bytes(b"png degil")

    with pytest.raises(OcrError):
        read_image(broken, "tur+eng")


class _Frame:
    def __init__(self, time: float | None) -> None:
        self.time = time


class _Container:
    def __init__(self, times: list[float | None]) -> None:
        self.frames = [_Frame(t) for t in times]

    def decode(self, stream):
        return iter(self.frames)


def test_samples_are_timed_from_the_start_of_the_media() -> None:
    # 10 fps; video 1,0 sn'de başlıyor; zamanı olmayan kare atlanır.
    times = [None] + [1.0 + i / 10 for i in range(21)]

    sampled = [t for t, _ in _samples(_Container(times), None, 0.5, start=1.0)]

    assert sampled == pytest.approx([0.0, 0.5, 1.0, 1.5, 2.0])


def test_course_language_selects_tesseract_languages() -> None:
    assert tesseract_languages("tr") == "tur+eng"
    assert tesseract_languages("en") == "eng"
    assert tesseract_languages("de") == "eng"


# --- disk düzeni -------------------------------------------------------------------------------


def test_document_files_include_frame_folders_and_remove_paths_deletes_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "upload_dir", tmp_path)
    ready, staging = frame_dir(3, 7), frame_dir(3, 7, staging=True)
    for folder in (ready, staging):
        folder.mkdir(parents=True)
        (folder / "0.png").write_bytes(b"png")
    transcript = tmp_path / "3" / "7.vtt"
    transcript.write_text("WEBVTT\n")
    other = frame_dir(3, 8)
    other.mkdir(parents=True)

    files = document_files(3, 7)
    remove_paths([*files, tmp_path / "yok.txt"])

    assert {ready, staging, transcript} <= set(files)
    assert not ready.exists() and not staging.exists() and not transcript.exists()
    assert other.exists()
