"""VTT ayrıştırıcı ve zamanlı parçalayıcı (veritabanı gerekmez)."""

import pytest

from app.embeddings.fake import FakeEmbedder
from app.ingestion.chunking import MAX_CHUNK_SECONDS, chunk_timed_segments
from app.ingestion.cleaning import clean_segments, normalize_timed_segments
from app.ingestion.parsers import vtt_parser
from app.ingestion.parsers.vtt_parser import ParsedVtt, parse_vtt_bytes
from app.ingestion.types import IngestionError, RawSegment
from tests.conftest import vtt_text


def parse(text: str) -> ParsedVtt:
    return parse_vtt_bytes(text.encode("utf-8"))


def spans(parsed: ParsedVtt) -> list[tuple[float | None, float | None, str]]:
    return [(s.t_start, s.t_end, s.text) for s in parsed.segments]


def test_valid_file_gives_one_segment_per_cue_with_time_ranges() -> None:
    parsed = parse(vtt_text([(1, 4.5, "Ikili arama"), (4.5, 9, "Dizi sirali olmali")]))

    assert spans(parsed) == [(1, 4.5, "Ikili arama"), (4.5, 9, "Dizi sirali olmali")]
    assert all(s.page is None for s in parsed.segments)
    assert (parsed.cues_read, parsed.cues_skipped, parsed.duration_s) == (2, 0, 9)


def test_bom_and_crlf_are_handled() -> None:
    content = "﻿WEBVTT\r\n\r\n00:00:01.000 --> 00:00:02.000\r\nMerhaba\r\ndunya\r\n".encode()

    parsed = parse_vtt_bytes(content)

    assert spans(parsed) == [(1, 2, "Merhaba dunya")]


def test_note_style_and_region_blocks_are_skipped() -> None:
    text = (
        "WEBVTT - baslik\n\nNOTE bu bir not\n--> degil\n\n"
        "STYLE\n::cue { color: red }\n\nREGION\nid:r1\n\n"
        "00:01.000 --> 00:02.000\nMetin\n"
    )

    parsed = parse(text)

    assert spans(parsed) == [(1, 2, "Metin")]
    assert parsed.cues_skipped == 0


def test_short_and_long_timestamps_and_hours() -> None:
    parsed = parse("WEBVTT\n\n01:02.500 --> 01:03.000\nkisa\n\n1:00:00.250 --> 1:00:01.000\nuzun\n")

    assert spans(parsed) == [(62.5, 63, "kisa"), (3600.25, 3601, "uzun")]
    assert parsed.duration_s == 3601


def test_cue_identifier_and_cue_settings_are_ignored() -> None:
    parsed = parse(
        "WEBVTT\n\ncue-1\n00:00:01.000 --> 00:00:02.000 align:start position:10%\nMetin\n\n"
        "2\n00:00:02.000 --> 00:00:03.000 line:0\nIkinci\n"
    )

    assert spans(parsed) == [(1, 2, "Metin"), (2, 3, "Ikinci")]


def test_inline_tags_are_removed_and_speaker_name_never_reaches_the_text() -> None:
    parsed = parse(
        "WEBVTT\n\n00:00:01.000 --> 00:00:05.000\n"
        "<v Prof. Ayse Yilmaz>Ikili <i>arama</i> <b>hizlidir</b></v>\n"
        "<c.vurgu>ve</c> <u>basittir</u> <00:00:03.000><c>cok</c> <lang tr>iyi</lang> "
        "<ruby>kanji<rt>yomi</rt></ruby>\n\n"
        "00:00:06.000 --> 00:00:07.000\n<v.yuksek Ali Veli>Tamam</v>\n"
    )

    first, second = (s.text for s in parsed.segments)
    assert first == "Ikili arama hizlidir ve basittir cok iyi kanjiyomi"
    assert second == "Tamam"
    assert "Ayse" not in first and "Ali" not in second


def test_math_with_angle_brackets_is_kept() -> None:
    parsed = parse("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\neger a < b ve b > c ise\n")

    assert parsed.segments[0].text == "eger a < b ve b > c ise"


def test_entities_are_decoded_and_whitespace_normalized() -> None:
    parsed = parse(
        "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n"
        "A &amp; B &lt;tag&gt;&nbsp;  x&lrm;&rlm;  \t y &amp;lt;\n"
    )

    # &amp;lt; iki kez çözülmez.
    assert parsed.segments[0].text == "A & B <tag> x y &lt;"


def test_youtube_rolling_lines_are_deduplicated() -> None:
    parsed = parse(
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:03.000\nbirinci satir\n\n"
        "00:00:03.000 --> 00:00:03.010\nbirinci satir\n\n"
        "00:00:03.010 --> 00:00:05.000\nbirinci satir\nikinci satir\n\n"
        "00:00:05.000 --> 00:00:07.000\nikinci satir\nuncu satir\n"
    )

    assert [s.text for s in parsed.segments] == ["birinci satir", "ikinci satir", "uncu satir"]
    # Metni boş kalan cue bozuk sayılmaz.
    assert parsed.cues_skipped == 0 and parsed.cues_read == 3


def test_one_malformed_cue_is_skipped_and_counted() -> None:
    parsed = parse(
        "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\niyi\n\n"
        "00:00:xx.000 --> 00:00:04.000\nbozuk zaman\n\n"
        "00:00:05.000 --> 00:00:06.000\niyi iki\n\n"
        "00:00:07.000 --> 00:00:08.000\niyi uc\n"
    )

    assert [s.text for s in parsed.segments] == ["iyi", "iyi iki", "iyi uc"]
    assert (parsed.cues_read, parsed.cues_skipped) == (3, 1)


def test_end_before_start_is_skipped_but_end_equal_to_start_is_accepted() -> None:
    parsed = parse(
        "WEBVTT\n\n00:00:05.000 --> 00:00:03.000\nters\n\n"
        "00:00:05.000 --> 00:00:05.000\nanlik\n\n"
        "00:00:06.000 --> 00:00:07.000\nnormal\n\n"
        "-00:00:06.000 --> 00:00:07.000\nnegatif\n"
    )

    assert [s.text for s in parsed.segments] == ["anlik", "normal"]
    assert parsed.cues_skipped == 2


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"   \n\n",
        b"00:00:01.000 --> 00:00:02.000\nbaslik yok\n",
        b"WEBVTTX\n\n00:00:01.000 --> 00:00:02.000\nmetin\n",
        b"WEBVTT\n\n",
        b"WEBVTT\n\nNOTE sadece not\n",
        b"WEBVTT\n\nbu bir cue degil\n\nbu da degil\n",
        b"WEBVTT\n\n00:00:09.000 --> 00:00:02.000\nters\n\n00:xx --> 00:01\nbozuk\n",
        b"WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n\n",
    ],
)
def test_unusable_files_are_rejected_with_a_readable_message(content: bytes) -> None:
    with pytest.raises(IngestionError) as error:
        parse_vtt_bytes(content)

    assert str(error.value)


def test_non_utf8_file_is_rejected() -> None:
    with pytest.raises(IngestionError, match="UTF-8"):
        parse_vtt_bytes("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nçğ\n".encode("cp1254"))


def test_skipped_ratio_threshold_is_exactly_half() -> None:
    good = "00:00:01.000 --> 00:00:02.000\niyi\n\n"
    bad = "bozuk --> 00:00:02.000\nkotu\n\n"

    assert vtt_parser.MAX_SKIPPED_RATIO == 0.5
    # 1 bozuk / 2 cue = %50: kabul. 2 bozuk / 3 cue > %50: red.
    assert parse("WEBVTT\n\n" + good + bad).cues_skipped == 1
    with pytest.raises(IngestionError, match="bozuk"):
        parse("WEBVTT\n\n" + good + bad + bad)


def cue(start: float, end: float, text: str) -> RawSegment:
    return RawSegment(text=text, t_start=start, t_end=end)


def test_timed_chunker_merges_consecutive_cues() -> None:
    cues = [cue(0, 5, "bir iki"), cue(5, 10, "uc dort"), cue(10, 15, "bes alti")]

    chunks = chunk_timed_segments(cues, FakeEmbedder())

    assert len(chunks) == 1
    assert chunks[0].text == "bir iki uc dort bes alti"
    assert (chunks[0].t_start, chunks[0].t_end, chunks[0].page) == (0, 15, None)


def test_timed_chunker_breaks_at_the_duration_ceiling() -> None:
    cues = [cue(i * 20, i * 20 + 20, f"cue{i}") for i in range(6)]  # 20 sn'lik 6 cue

    chunks = chunk_timed_segments(cues, FakeEmbedder(), overlap_tokens=0)

    assert MAX_CHUNK_SECONDS == 60
    assert [(c.t_start, c.t_end) for c in chunks] == [(0, 60), (60, 120)]
    # Sınır dahil: tam 60 sn sığar, 60,001 sığmaz.
    edge = chunk_timed_segments(
        [cue(0, 30, "a"), cue(30, 60.001, "b")], FakeEmbedder(), overlap_tokens=0
    )
    assert len(edge) == 2


def test_timed_chunker_breaks_at_the_token_ceiling_and_never_splits_a_cue() -> None:
    words = " ".join(f"w{i}" for i in range(10))  # 10 test tokens
    cues = [cue(i, i + 1, words) for i in range(4)]

    chunks = chunk_timed_segments(cues, FakeEmbedder(), max_tokens=20, overlap_tokens=0)

    assert [c.text for c in chunks] == [f"{words} {words}", f"{words} {words}"]
    assert all(FakeEmbedder().count_passage_tokens(c.text) <= 20 for c in chunks)


def test_a_single_oversized_cue_is_split_with_its_original_interval() -> None:
    huge = " ".join(f"k{i}" for i in range(100))
    cues = [cue(0, 5, "kisa bir"), cue(5, 200, huge), cue(200, 205, "kisa iki")]

    chunks = chunk_timed_segments(cues, FakeEmbedder(), max_tokens=20, overlap_tokens=0)

    assert all(FakeEmbedder().count_passage_tokens(c.text) <= 20 for c in chunks)
    assert huge == "".join(c.text for c in chunks[1:-1])
    assert (chunks[0].t_start, chunks[0].t_end) == (0, 5)
    assert (chunks[-1].t_start, chunks[-1].t_end) == (200, 205)
    assert all((c.t_start, c.t_end) == (5, 200) for c in chunks[1:-1])


def test_timed_chunks_overlap_by_whole_cues() -> None:
    cues = [cue(i * 30, i * 30 + 30, f"c{i} x") for i in range(5)]  # 2 test tokens per cue

    chunks = chunk_timed_segments(cues, FakeEmbedder(), max_seconds=60, overlap_tokens=3)

    assert [c.text for c in chunks] == ["c0 x c1 x", "c1 x c2 x", "c2 x c3 x", "c3 x c4 x"]
    assert [(c.t_start, c.t_end) for c in chunks] == [(0, 60), (30, 90), (60, 120), (90, 150)]


def test_overlap_never_pushes_a_chunk_past_the_ceilings() -> None:
    cues = [cue(i * 25, i * 25 + 25, "a b") for i in range(8)]

    chunks = chunk_timed_segments(cues, FakeEmbedder(), max_seconds=60, overlap_tokens=60)

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.t_start is not None and chunk.t_end is not None
        assert chunk.t_end - chunk.t_start <= 60


def test_timed_chunker_edge_inputs() -> None:
    assert chunk_timed_segments([], FakeEmbedder()) == []
    only = chunk_timed_segments([cue(3, 3, "anlik")], FakeEmbedder())
    assert [(c.text, c.t_start, c.t_end) for c in only] == [("anlik", 3, 3)]


def test_timed_cleaning_only_normalizes_and_keeps_repeats_and_numbers() -> None:
    cues = [cue(i, i + 1, "evet\n3") for i in range(6)] + [cue(7, 8, "    ")]

    cleaned, stats = normalize_timed_segments(cues)

    assert len(cleaned) == 6
    assert all(c.text == "evet\n3" for c in cleaned)
    assert (stats.repeated_lines_removed, stats.page_numbers_removed) == (0, 0)
    assert stats.empty_segments_dropped == 1


def test_page_cleaning_without_layout_preserves_repeated_lines_and_numbers() -> None:
    pages = [RawSegment(text=f"Ust bilgi\nicerik {i}\n{i}", page=i) for i in range(1, 7)]

    cleaned = clean_segments(pages)

    assert [s.text for s in cleaned] == [s.text for s in pages]
