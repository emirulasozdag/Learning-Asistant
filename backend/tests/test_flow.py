"""Uçtan uca akış: ders → materyal yükle → soru sor → kaynağı aç (gerçek veritabanı).

Sahte embedder ve (gerektiğinde) sahte LLM ile çalışır; TEST_DATABASE_URL yoksa atlanır.
"""

import json
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api import ask as ask_api
from app.db.models import Chunk, Course, Message
from tests.test_answer import FakeLLM


def upload(client: TestClient, course_id: int, path: Path, material_type: str = "notes"):
    with path.open("rb") as file:
        return client.post(
            f"/courses/{course_id}/materials",
            data={"material_type": material_type},
            files={"file": (path.name, file)},
        )


def test_courses_are_listed(client: TestClient, course: Course) -> None:
    response = client.get("/courses")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": course.id,
            "code": "BLM2512",
            "name": "Veri Yapilari ve Algoritmalar",
            "language": "tr",
            "role": None,
        }
    ]


def test_upload_pdf_creates_document_and_page_numbered_chunks(
    client: TestClient, course: Course, sample_pdf: Path
) -> None:
    response = upload(client, course.id, sample_pdf)

    assert response.status_code == 201
    document = response.json()
    assert document["title"] == "notlar"
    assert document["page_count"] == 3
    assert document["chunk_count"] == 3
    assert document["file_url"] == f"/api/documents/{document['id']}/file"

    chunks = client.get(f"/documents/{document['id']}/chunks").json()
    assert [c["page"] for c in chunks] == [1, 2, 3]
    assert "sag yari elenir" in chunks[1]["text"]

    listed = client.get(f"/courses/{course.id}/materials").json()
    assert [(d["id"], d["chunk_count"]) for d in listed] == [(document["id"], 3)]


def test_uploaded_file_is_served_back(client: TestClient, course: Course, sample_pdf: Path) -> None:
    document = upload(client, course.id, sample_pdf).json()

    response = client.get(f"/documents/{document['id']}/file")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == sample_pdf.read_bytes()


def test_upload_pptx(client: TestClient, course: Course, sample_pptx: Path) -> None:
    response = upload(client, course.id, sample_pptx, material_type="slides")

    assert response.status_code == 201
    assert response.json()["material_type"] == "slides"
    assert response.json()["chunk_count"] == 3


def test_upload_rejects_unsupported_type_and_unknown_course(
    client: TestClient, course: Course, tmp_path: Path
) -> None:
    text_file = tmp_path / "notlar.txt"
    text_file.write_text("merhaba")

    unsupported = upload(client, course.id, text_file)
    unknown_course = upload(client, 9999, text_file)

    assert unsupported.status_code == 422
    assert "Desteklenmeyen dosya türü" in unsupported.json()["detail"]
    assert unknown_course.status_code == 404


def test_upload_rejects_pdf_without_text_and_keeps_nothing(
    client: TestClient, course: Course, tmp_path: Path
) -> None:
    path = tmp_path / "taranmis.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(path)

    response = upload(client, course.id, path)

    assert response.status_code == 422
    assert "metin çıkarılamadı" in response.json()["detail"]
    assert client.get(f"/courses/{course.id}/materials").json() == []
    assert not any((tmp_path / "uploads").rglob("*.pdf"))


def test_ask_returns_cited_answer_and_source_opens_at_page(
    client: TestClient, course: Course, sample_pdf: Path
) -> None:
    document = upload(client, course.id, sample_pdf).json()

    answer = client.post(
        "/ask", json={"course_id": course.id, "question": "Neden sag yari elenir?"}
    ).json()

    assert not answer["declined"]
    assert answer["mode"] == "extractive"
    assert "sag yari elenir" in answer["answer"]
    citation = answer["citations"][0]
    assert (citation["document_title"], citation["page"]) == ("notlar", 2)

    source = client.get(f"/sources/{citation['source_id']}").json()
    assert source["page"] == 2
    assert source["document_id"] == document["id"]
    assert source["media_url"] == f"/api/documents/{document['id']}/file#page=2"


def test_ask_out_of_scope_question_is_declined(
    client: TestClient, course: Course, sample_pdf: Path
) -> None:
    upload(client, course.id, sample_pdf)

    answer = client.post(
        "/ask", json={"course_id": course.id, "question": "Fransa'nın başkenti neresi?"}
    ).json()

    assert answer["declined"] is True
    assert answer["answer"] is None
    assert answer["citations"] == []


def test_search_is_isolated_per_course(
    client: TestClient, db, course: Course, sample_pdf: Path
) -> None:
    other = Course(code="FIZ101", name="Fizik", language="tr")
    db.add(other)
    db.commit()
    upload(client, course.id, sample_pdf)

    answer = client.post("/ask", json={"course_id": other.id, "question": "ikili arama"}).json()

    assert answer["declined"] is True


def test_missing_source_and_document_return_404(client: TestClient, course: Course) -> None:
    assert client.get("/sources/123").status_code == 404
    assert client.get("/sources/abc").status_code == 404
    assert client.get("/documents/123/chunks").status_code == 404
    assert client.get("/documents/123/file").status_code == 404


# --- Sprint 1: ders oluşturma, vektörler, rapor, silme, sayfa görüntüsü, sohbet, akış ---


def parse_sse(body: str) -> list[tuple[str, object]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_create_course_normalizes_code_and_rejects_duplicates(client: TestClient) -> None:
    created = client.post("/courses", json={"code": "blm 2512", "name": " Veri Yapilari "})
    duplicate = client.post("/courses", json={"code": "BLM2512", "name": "Baska"})

    assert created.status_code == 201
    assert created.json() == {
        "id": created.json()["id"],
        "code": "BLM2512",
        "name": "Veri Yapilari",
        "language": "tr",
        "role": None,
    }
    assert duplicate.status_code == 409
    assert "zaten var" in duplicate.json()["detail"]
    assert client.post("/courses", json={"code": "X", "name": "Kisa"}).status_code == 422


def test_upload_returns_pipeline_report_and_stores_vectors(
    client: TestClient, db, course: Course, sample_pdf: Path
) -> None:
    document = upload(client, course.id, sample_pdf).json()

    report = document["report"]
    assert report["pages_read"] == 3
    assert report["chunks"] == report["vectors"] == 3
    assert report["vector_dim"] == 768
    assert report["embedding_model"] == "fake"
    assert set(report["timings_ms"]) == {"parse", "clean", "chunk", "embed"}
    assert db.scalar(select(func.count(Chunk.id)).where(Chunk.embedding.is_not(None))) == 3
    # Liste cevabında rapor yok (yalnızca yükleme anında).
    assert client.get(f"/courses/{course.id}/materials").json()[0]["report"] is None


def test_delete_document_removes_chunks_and_file(
    client: TestClient, db, course: Course, sample_pdf: Path, tmp_path: Path
) -> None:
    document = upload(client, course.id, sample_pdf).json()

    response = client.delete(f"/documents/{document['id']}")

    assert response.status_code == 204
    assert client.get(f"/courses/{course.id}/materials").json() == []
    assert db.scalar(select(func.count(Chunk.id))) == 0
    assert not any((tmp_path / "uploads").rglob("*.pdf"))
    assert client.delete(f"/documents/{document['id']}").status_code == 404


def test_pdf_source_has_page_image_and_highlights(
    client: TestClient, course: Course, sample_pdf: Path
) -> None:
    document = upload(client, course.id, sample_pdf).json()
    answer = client.post(
        "/ask", json={"course_id": course.id, "question": "Neden sag yari elenir?"}
    ).json()

    source = client.get(f"/sources/{answer['citations'][0]['source_id']}").json()
    image = client.get(f"/documents/{document['id']}/pages/2.png")

    assert source["page_image_url"] == f"/api/documents/{document['id']}/pages/2.png"
    assert source["highlights"], "alıntılanan satırlar sayfada bulunmalı"
    for box in source["highlights"]:
        assert 0 <= box["x"] < 1 and 0 <= box["y"] < 1 and box["width"] > 0
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.content.startswith(b"\x89PNG")
    assert client.get(f"/documents/{document['id']}/pages/99.png").status_code == 404


def test_pptx_source_has_no_page_image(
    client: TestClient, course: Course, sample_pptx: Path
) -> None:
    upload(client, course.id, sample_pptx, material_type="slides")
    answer = client.post(
        "/ask", json={"course_id": course.id, "question": "Neden sag yari elenir?"}
    ).json()

    source = client.get(f"/sources/{answer['citations'][0]['source_id']}").json()

    assert source["page_image_url"] is None and source["highlights"] == []


def test_conversation_is_remembered_and_isolated(
    client: TestClient, db, course: Course, sample_pdf: Path
) -> None:
    upload(client, course.id, sample_pdf)
    first = client.post("/ask", json={"course_id": course.id, "question": "Ikili arama nedir?"})
    conversation_id = first.json()["conversation_id"]

    second = client.post(
        "/ask",
        json={
            "course_id": course.id,
            "question": "Karmasikligi ne?",
            "conversation_id": conversation_id,
        },
    )
    other = Course(code="FIZ101", name="Fizik", language="tr")
    db.add(other)
    db.commit()
    foreign = client.post(
        "/ask",
        json={"course_id": other.id, "question": "?", "conversation_id": conversation_id},
    )

    assert second.json()["conversation_id"] == conversation_id
    roles = db.scalars(
        select(Message.role).where(Message.conversation_id == conversation_id).order_by(Message.id)
    ).all()
    assert roles == ["user", "assistant", "user", "assistant"]
    assert foreign.status_code == 404


def test_stream_endpoint_sends_retrieval_deltas_and_validated_answer(
    client: TestClient, course: Course, sample_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    upload(client, course.id, sample_pdf)
    llm = FakeLLM(["Dizi sirali oldugu icin ", "sag yari elenir [S1]."])
    monkeypatch.setattr(ask_api, "select_client", lambda: llm)

    response = client.post(
        "/ask/stream", json={"course_id": course.id, "question": "Neden sag yari elenir?"}
    )
    events = parse_sse(response.text)

    assert response.headers["content-type"].startswith("text/event-stream")
    assert [name for name, _ in events] == ["retrieval", "delta", "delta", "done"]
    hits = events[0][1]
    done = events[-1][1]
    assert done["answer"] == "Dizi sirali oldugu icin sag yari elenir [1]."
    assert done["model"] == "fake-model"
    assert done["citations"][0]["source_id"] == hits[0]["source_id"]
    assert [hit["used"] for hit in done["retrieval"]][0] is True
    assert done["similarity_threshold"] == pytest.approx(0.78)


def test_irrelevant_question_never_reaches_the_llm(
    client: TestClient, course: Course, sample_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    upload(client, course.id, sample_pdf)
    llm = FakeLLM(["olmamali"])
    monkeypatch.setattr(ask_api, "select_client", lambda: llm)

    done = client.post(
        "/ask", json={"course_id": course.id, "question": "Fransa'nın başkenti neresi?"}
    ).json()

    assert done["declined"] is True
    assert llm.calls == []


def test_follow_up_question_gets_history(
    client: TestClient, course: Course, sample_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    upload(client, course.id, sample_pdf)
    llm = FakeLLM(["Sirali dizide arama [S1]."])
    monkeypatch.setattr(ask_api, "select_client", lambda: llm)

    first = client.post("/ask", json={"course_id": course.id, "question": "Ikili arama nedir?"})
    client.post(
        "/ask",
        json={
            "course_id": course.id,
            "question": "Peki karmasikligi ne?",
            "conversation_id": first.json()["conversation_id"],
        },
    )

    _, messages = llm.calls[1]
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert messages[0]["content"] == "Ikili arama nedir?"
    assert messages[1]["content"] == "Sirali dizide arama."  # alıntı numarası atılır


def test_stream_reports_unexpected_errors_as_event(
    client: TestClient, course: Course, sample_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    upload(client, course.id, sample_pdf)
    monkeypatch.setattr(ask_api, "select_client", lambda: FakeLLM(error=RuntimeError("bozuk")))

    response = client.post("/ask/stream", json={"course_id": course.id, "question": "sag yari"})

    names = [name for name, _ in parse_sse(response.text)]
    assert names[0] == "retrieval" and names[-1] == "error"
