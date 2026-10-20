"""Real provider checks: RUN_E5_TESTS=1, installed embeddings extra and cached model.

PILOT_MATERIAL_DIR optionally enables approved local OCW files; source content is never
stored in this repository. These tests use the same tokenizer/model as actual uploads.
"""

import os
from pathlib import Path

import pymupdf
import pytest

from app.core.config import settings
from app.embeddings.e5 import E5Embedder, _load
from app.ingestion.chunking import chunk_segments, chunk_timed_segments
from app.ingestion.cleaning import clean_segments
from app.ingestion.parsers.pdf_parser import parse_pdf
from app.ingestion.types import RawSegment
from tests.test_flow import upload

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_E5_TESTS"), reason="RUN_E5_TESTS is not set"
)


@pytest.fixture(scope="module")
def embedder() -> E5Embedder:
    return E5Embedder(settings.embedding_model)


@pytest.mark.parametrize(
    "sample",
    [
        "Özyinelemeli algoritmaların karmaşıklığını değerlendiriyoruz. ",
        "extraordinarily counterintuitive computational intractability. ",
        "items[index_value] += calculate_result(node.left_child); ",
        "node.left_child[index_value]+=node.right_child[index_value];",
    ],
    ids=["turkish", "english", "code", "unspaced-code"],
)
def test_real_token_budget_and_lossless_splitting(embedder: E5Embedder, sample: str) -> None:
    source = sample * 150
    chunks = chunk_segments([RawSegment(text=source, page=3)], embedder, overlap_tokens=0)
    model = _load(embedder.model_name)

    assert len(chunks) > 1
    assert "".join(chunk.text for chunk in chunks) == source
    for chunk in chunks:
        actual = len(model.tokenizer.encode(f"passage: {chunk.text}", add_special_tokens=True))
        assert actual == embedder.count_passage_tokens(chunk.text)
        assert actual <= model.max_seq_length
        assert chunk.page == 3


def test_e5_rejects_oversized_passages_instead_of_truncating(embedder: E5Embedder) -> None:
    with pytest.raises(ValueError, match="exceeds the embedding token budget"):
        embedder.embed_passages(["items[index] += node.left_child;" * 150])


def test_long_cues_obey_real_budget_without_inventing_timestamps(embedder: E5Embedder) -> None:
    source = "Özyinelemeli algoritmaların karmaşıklığı. " * 150
    chunks = chunk_timed_segments(
        [RawSegment(text=source, t_start=10, t_end=80)],
        embedder,
        overlap_tokens=0,
    )
    assert len(chunks) > 1
    assert "".join(chunk.text for chunk in chunks) == source
    assert all(
        embedder.count_passage_tokens(chunk.text) <= embedder.max_passage_tokens for chunk in chunks
    )
    assert all((chunk.t_start, chunk.t_end) == (10, 80) for chunk in chunks)


@pytest.mark.parametrize(
    "suffix", ["_lec2.pdf", "_lec3.pdf", "_lec9.pdf", "_r03.pdf", "_r07.pdf", "_r14.pdf"]
)
def test_approved_pilot_documents(embedder: E5Embedder, suffix: str) -> None:
    root = os.environ.get("PILOT_MATERIAL_DIR")
    if not root:
        pytest.skip("PILOT_MATERIAL_DIR is not set")
    paths = list(Path(root).rglob(f"*{suffix}"))
    assert len(paths) == 1, f"Expected one approved pilot file matching {suffix}"
    raw = parse_pdf(paths[0])
    cleaned = clean_segments(raw)
    chunks = chunk_segments(cleaned, embedder, overlap_tokens=0)
    assert chunks
    assert all(
        embedder.count_passage_tokens(chunk.text) <= embedder.max_passage_tokens for chunk in chunks
    )
    for segment in cleaned:
        assert "".join(chunk.text for chunk in chunks if chunk.page == segment.page) == segment.text
    # Layout whitespace is retained exactly, including all surviving code/table lines.
    for segment in raw:
        cleaned_page = next((page for page in cleaned if page.page == segment.page), None)
        for index, line in enumerate(segment.text.split("\n")):
            if line.strip() and index not in segment.margin_lines:
                assert cleaned_page is not None and line in cleaned_page.text


def test_real_provider_upload_ask_and_source(client, course, sample_pdf, monkeypatch) -> None:
    monkeypatch.setattr(settings, "embedding_provider", "e5")
    response = upload(client, course.id, sample_pdf)
    assert response.status_code == 201, response.text
    document = response.json()
    assert document["report"]["embedding_model"] == settings.embedding_model
    assert document["report"]["warnings"] == []
    answer = client.post(
        "/ask",
        json={"course_id": course.id, "question": "Neden sag yari elenir?"},
    )
    assert answer.status_code == 200
    assert answer.json()["outcome"] == "answered"
    source = client.get(f"/sources/{answer.json()['citations'][0]['source_id']}")
    assert source.status_code == 200
    assert source.json()["document_id"] == document["id"]
    assert source.json()["page"] == 2
    assert source.json()["highlights"]
    assert client.get(f"/documents/{document['id']}/pages/2.png").status_code == 200


def test_approved_pilot_upload_ask_and_source(
    client, course, tmp_path, monkeypatch, embedder
) -> None:
    root = os.environ.get("PILOT_MATERIAL_DIR")
    if not root:
        pytest.skip("PILOT_MATERIAL_DIR is not set")
    paths = list(Path(root).rglob("*_r03.pdf"))
    assert len(paths) == 1
    path = tmp_path / "approved-pilot-excerpt.pdf"
    with pymupdf.open(paths[0]) as source, pymupdf.open() as excerpt:
        excerpt.insert_pdf(source, from_page=0, to_page=1)
        excerpt.save(path)
    expected = clean_segments(parse_pdf(path))
    monkeypatch.setattr(settings, "embedding_provider", "e5")
    response = upload(client, course.id, path)
    assert response.status_code == 201, response.text
    document = response.json()
    chunks = client.get(f"/documents/{document['id']}/chunks").json()
    assert all(
        embedder.count_passage_tokens(chunk["text"]) <= embedder.max_passage_tokens
        for chunk in chunks
    )
    for segment in expected:
        for line in segment.text.split("\n"):
            if line.strip():
                assert any(
                    line in chunk["text"] for chunk in chunks if chunk["page"] == segment.page
                )
    # An exact local excerpt tests retrieval without committing the approved course text.
    question = chunks[0]["text"][:350]
    answer = client.post("/ask", json={"course_id": course.id, "question": question})
    assert answer.status_code == 200
    assert answer.json()["outcome"] == "answered", answer.text
    source = client.get(f"/sources/{answer.json()['citations'][0]['source_id']}").json()
    assert source["document_id"] == document["id"]
    assert source["page"] in {1, 2}
    assert source["highlights"]
    assert client.get(f"/documents/{document['id']}/file").content == path.read_bytes()
    assert client.get(f"/documents/{document['id']}/pages/{source['page']}.png").status_code == 200
