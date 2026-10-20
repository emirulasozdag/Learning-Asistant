import csv

import pytest
from factories import ANSWER, NOW, SHA, gold_set, record, result
from pydantic import ValidationError

from harness.claims import claim_sha256, split_claims
from harness.labels import (
    LabelSet,
    LabelSource,
    draw_sample,
    labels_from_sheet,
    read_sheet,
    sheet_rows,
    write_sheet,
)
from harness.schemas import ItemKind

# --- İddia bölme -------------------------------------------------------------------------------


def test_split_claims_drops_markers_headings_and_fragments():
    answer = (
        "## Özet\n"
        "İkili arama sıralı dizide çalışır [1]. Her adımda aralık yarıya iner [S2].\n"
        "Şöyle düşünün:\n"
        "- Ortadaki eleman hedefle karşılaştırılır [1].\n"
        "Evet.\n"
        "```\nkod satırı burada var\n```"
    )
    assert split_claims(answer) == [
        "İkili arama sıralı dizide çalışır.",
        "Her adımda aralık yarıya iner.",
        "Ortadaki eleman hedefle karşılaştırılır.",
    ]


def test_split_claims_is_deterministic():
    assert split_claims(ANSWER) == split_claims(ANSWER)
    assert len(split_claims(ANSWER)) == 2


# --- Şema --------------------------------------------------------------------------------------


@pytest.mark.parametrize("rater", ["Ayşe Yılmaz", "a", "ali@x.com"])
def test_rater_must_be_pseudonym(rater):
    with pytest.raises(ValidationError):
        LabelSet(run_id="r", source="human", rater=rater, labeled_at=NOW, items=[])


def test_judge_labels_need_model_and_prompt():
    with pytest.raises(ValidationError, match="Judge"):
        LabelSet(run_id="r", source="judge", rater="judge", labeled_at=NOW, items=[])


def test_score_range_and_unique_items():
    item = {"item_id": "q1", "score": 3}
    with pytest.raises(ValidationError):
        LabelSet(run_id="r", source="human", rater="rater-a", labeled_at=NOW, items=[item])
    twice = [{"item_id": "q1", "score": 1}, {"item_id": "q1", "score": 2}]
    with pytest.raises(ValidationError, match="iki kez"):
        LabelSet(run_id="r", source="human", rater="rater-a", labeled_at=NOW, items=twice)


# --- Örneklem ----------------------------------------------------------------------------------


def test_sample_is_reproducible_and_answerable_only():
    run = record(
        [result(f"q{n}") for n in range(10)]
        + [result("o1", kind=ItemKind.OUT_OF_SCOPE), result("e1", error="X: y")]
    )
    first = draw_sample(run, size=4, seed=13, now=NOW)
    assert first == draw_sample(run, size=4, seed=13, now=NOW)
    assert first.frame_size == 10
    assert len(first.item_ids) == 4
    assert not {"o1", "e1"} & set(first.item_ids)
    assert len(draw_sample(run, size=50, seed=1).item_ids) == 10


# --- Tablo -------------------------------------------------------------------------------------


def _filled(run, rows, score="2", label="supported"):
    filled = []
    for row in rows:
        row = dict(row)
        if row["row"] == "answer":
            row["score"] = score
        else:
            row["label"] = label
        filled.append(row)
    return filled


def test_sheet_round_trip(tmp_path):
    run = record([result("q1"), result("q2", declined=True)])
    rows = sheet_rows(run, gold_set(["q1", "q2"]), ["q1", "q2"])
    # Reddedilen cevap tabloya girmez; cevap satırı + iki iddia satırı.
    assert [row["row"] for row in rows] == ["answer", "claim", "claim"]
    assert "Ders 3 s.2" in rows[0]["passages"]
    path = tmp_path / "sheet.csv"
    write_sheet(_filled(run, rows), path)
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")  # Excel için BOM

    labels = labels_from_sheet(run, read_sheet(path), "rater-a", now=NOW)
    assert labels.source is LabelSource.HUMAN
    (item,) = labels.items
    assert item.score == 2
    assert [c.label for c in item.claims] == ["supported", "supported"]
    # Etiket dosyası metin taşımaz.
    dumped = labels.model_dump_json()
    assert "İkili" not in dumped and "Soru" not in dumped


def test_sheet_never_overwrites(tmp_path):
    path = tmp_path / "sheet.csv"
    write_sheet([], path)
    with pytest.raises(FileExistsError):
        write_sheet([], path)


def test_read_sheet_accepts_comma_csv(tmp_path):
    run = record([result("q1")])
    rows = _filled(run, sheet_rows(run, gold_set(["q1"]), ["q1"]), score="1,0", label="U")
    path = tmp_path / "sheet.csv"
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]), delimiter=",")
        writer.writeheader()
        writer.writerows(rows)
    labels = labels_from_sheet(run, read_sheet(path), "rater-b")
    assert labels.items[0].score == 1
    assert {c.label for c in labels.items[0].claims} == {"unsupported"}


def test_incomplete_sheet_lists_every_problem():
    run = record([result("q1")])
    rows = _filled(run, sheet_rows(run, gold_set(["q1"]), ["q1"]), score="", label="belki")
    with pytest.raises(ValueError) as exc:
        labels_from_sheet(run, rows, "rater-a")
    message = str(exc.value)
    assert "puan 0, 1 ya da 2" in message
    assert "supported ya da unsupported" in message


def test_sheet_from_other_run_or_changed_answer_rejected():
    run = record([result("q1")])
    rows = _filled(run, sheet_rows(run, gold_set(["q1"]), ["q1"]))
    other = record([result("q1")], run_id="run-2")
    with pytest.raises(ValueError, match="başka bir koşu"):
        labels_from_sheet(other, rows, "rater-a")
    changed = record([result("q1", answer="Tamamen farklı bir cevap metni burada.")])
    with pytest.raises(ValueError, match="uyuşmuyor"):
        labels_from_sheet(changed, rows, "rater-a")


def test_missing_claim_rows_are_rejected():
    run = record([result("q1")])
    rows = _filled(run, sheet_rows(run, gold_set(["q1"]), ["q1"]))[:-1]
    with pytest.raises(ValueError, match="hepsi etiketlenmemiş"):
        labels_from_sheet(run, rows, "rater-a")


def test_claim_hash_matches_split():
    run = record([result("q1")])
    rows = sheet_rows(run, gold_set(["q1"]), ["q1"])
    claims = split_claims(ANSWER)
    assert [r["claim_sha256"] for r in rows[1:]] == [claim_sha256(c) for c in claims]
    assert SHA not in rows[1]["claim_sha256"]


def test_duplicate_rows_are_rejected():
    run = record([result("q1")])
    rows = _filled(run, sheet_rows(run, gold_set(["q1"]), ["q1"]))
    second = dict(rows[0], score="0")
    with pytest.raises(ValueError, match="ikinci cevap satırı"):
        labels_from_sheet(run, [*rows, second], "rater-a")
    with pytest.raises(ValueError, match="ikinci satırı"):
        labels_from_sheet(run, [*rows, rows[1]], "rater-a")


def test_sheet_must_cover_the_sample():
    run = record([result("q1"), result("q2")])
    rows = _filled(run, sheet_rows(run, gold_set(["q1", "q2"]), ["q1", "q2"]))
    only_q1 = [row for row in rows if row["item_id"] == "q1"]
    with pytest.raises(ValueError, match="q2: örneklemdeki soru tabloda yok"):
        labels_from_sheet(run, only_q1, "rater-a", expected_ids={"q1", "q2"})
    with pytest.raises(ValueError, match="örneklemde yok"):
        labels_from_sheet(run, rows, "rater-a", expected_ids={"q1"})
    assert len(labels_from_sheet(run, rows, "rater-a", expected_ids={"q1", "q2"}).items) == 2


def test_long_passages_are_cut_with_a_visible_marker():
    run = record([result("q1", retrieved_text=["x" * 40_000])])
    (answer_row, *_) = sheet_rows(run, gold_set(["q1"]), ["q1"])
    assert len(answer_row["passages"]) < 32_767
    assert "kesildi" in answer_row["passages"]
