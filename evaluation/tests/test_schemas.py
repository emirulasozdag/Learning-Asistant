import pytest
from pydantic import ValidationError

from harness.schemas import (
    CorpusManifest,
    GoldItem,
    GoldSet,
    ManifestDocument,
    SourceLocator,
)

SHA_A = "a" * 64
SHA_B = "b" * 64


def loc(sha=SHA_A, **kw):
    return SourceLocator(document_sha256=sha, **kw)


def item(id="q1", **kw):
    data = {
        "id": id,
        "split": "heldout",
        "kind": "answerable",
        "question": "Ne demek bu?",
        "origin": "instructor",
    }
    return GoldItem(**{**data, **kw})


# --- SourceLocator.matches ---------------------------------------------------------------------


def test_page_match_same_page_only():
    assert loc(page=3).matches(loc(page=3))
    assert not loc(page=3).matches(loc(page=4))
    assert not loc(page=3).matches(loc())  # sayfa bilgisi yok


def test_time_interval_overlap():
    gold = loc(t_start=10, t_end=20)
    assert gold.matches(loc(t_start=15, t_end=30))
    assert gold.matches(loc(t_start=20, t_end=25))  # sınırda temas
    assert gold.matches(loc(t_start=12, t_end=14))  # içinde
    assert not gold.matches(loc(t_start=21, t_end=30))
    assert not gold.matches(loc(page=1))  # zaman bilgisi yok


def test_document_level_matches_any_position_in_document():
    gold = loc()
    assert gold.matches(loc(page=7))
    assert gold.matches(loc(t_start=1, t_end=2))
    assert gold.matches(loc())


def test_different_document_never_matches():
    assert not loc(page=1).matches(loc(SHA_B, page=1))
    assert not loc().matches(loc(SHA_B))


# --- SourceLocator doğrulama -------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"t_start": 1},
        {"t_end": 1},
        {"t_start": 5, "t_end": 1},
        {"page": 1, "t_start": 1, "t_end": 2},
        {"page": 0},
        {"t_start": -1, "t_end": 2},
    ],
)
def test_locator_invalid_positions(kwargs):
    with pytest.raises(ValidationError):
        loc(**kwargs)


@pytest.mark.parametrize("sha", ["a" * 63, "A" * 64, "g" * 64, ""])
def test_locator_bad_sha(sha):
    with pytest.raises(ValidationError):
        SourceLocator(document_sha256=sha)


def test_locator_rejects_extra_fields():
    with pytest.raises(ValidationError):
        SourceLocator(document_sha256=SHA_A, passage="metin")


# --- GoldItem / GoldSet ------------------------------------------------------------------------


def test_out_of_scope_with_evidence_rejected():
    with pytest.raises(ValidationError):
        item(kind="out_of_scope", evidence=[loc()])


def test_out_of_scope_with_reference_answer_rejected():
    with pytest.raises(ValidationError):
        item(kind="out_of_scope", reference_answer="cevap")


def test_out_of_scope_plain_ok():
    assert item(kind="out_of_scope").evidence == []


def test_reviewed_property():
    assert not item().reviewed
    reviewed = item(review={"reviewer": "instructor-1", "reviewed_at": "2026-10-01T10:00:00Z"})
    assert reviewed.reviewed


def test_bad_item_id_rejected():
    with pytest.raises(ValidationError):
        item(id="bad id!")


def test_duplicate_ids_rejected():
    with pytest.raises(ValidationError, match="Tekrarlanan"):
        GoldSet(course_code="BLM2512", manifest="m.json", items=[item("x"), item("x")])


def test_goldset_ok():
    gold = GoldSet(course_code="BLM2512", manifest="m.json", items=[item("x"), item("y")])
    assert len(gold.items) == 2


# --- Manifest ----------------------------------------------------------------------------------


def doc(sha=SHA_A, **kw):
    data = {"sha256": sha, "title": "Ders 1", "material_type": "pdf", "status": "approved"}
    return {**data, **kw}


def test_approved_without_permission_rejected():
    with pytest.raises(ValidationError, match="izin"):
        ManifestDocument(**doc())


def test_excluded_without_reason_rejected():
    with pytest.raises(ValidationError, match="gerekçe"):
        ManifestDocument(**doc(status="excluded"))


def test_manifest_duplicate_documents_rejected():
    docs = [ManifestDocument(**doc(permission="p")), ManifestDocument(**doc(permission="p"))]
    with pytest.raises(ValidationError):
        CorpusManifest(course_code="BLM2512", documents=docs)


def test_manifest_hash_sets():
    approved = ManifestDocument(**doc(SHA_A, permission="p"))
    excluded = ManifestDocument(**doc(SHA_B, status="excluded", exclusion_reason="sınav"))
    manifest = CorpusManifest(course_code="BLM2512", documents=[approved, excluded])
    assert manifest.approved_hashes() == {SHA_A}
    assert manifest.excluded_hashes() == {SHA_B}
