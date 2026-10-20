"""Pratik döngüsü (#15, #16, #20): üret → kontrol → sakla; cevap → değerlendir → kaydet.

Gerçek veritabanı, sahte modeller: her model istenen şemaya göre sıradaki cevabı döndürür.
`client` dersin eğitmeni olarak oturum açmıştır (conftest).
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import select

from app.api import practice as practice_api
from app.api import tutor as tutor_api
from app.db.models import Course, PracticeAttempt, PracticeQuestion
from app.generation.grade import GradeOutput
from app.generation.question import Criterion, GeneratedQuestion
from app.llm.base import LLMUsage, ToolCall
from app.llm.gateway import LLMRole
from app.verification.practice_checks import Agreement, MCQSolution, OpenSolution
from tests.conftest import enroll, make_pdf, make_user
from tests.test_flow import upload
from tests.test_tutor import FakeOrchestrator

LONG_PAGES = [
    (
        "Ikili Arama",
        "Ikili arama sirali bir dizide hedef degeri arar. Her adimda ortadaki eleman hedefle "
        "karsilastirilir ve kalan araligin yarisi atilir. Bu nedenle ikili arama sirali dizide "
        "O(log n) zamanda calisir. Dizi sirali degilse ikili arama dogru sonuc vermez; once "
        "siralamak gerekir. Dogrusal arama ise her elemana tek tek bakar ve O(n) zaman alir.",
    )
]
EVIDENCE = "ortadaki eleman hedefle karsilastirilir ve kalan araligin yarisi atilir"


class FakeJSON:
    """Şemaya göre sıradaki cevabı döndürür; hata da sıraya konabilir."""

    def __init__(self, name: str, *answers: BaseModel | Exception) -> None:
        self.model = name
        self.answers = list(answers)
        self.calls: list[tuple[str, str]] = []
        self.usage: list[LLMUsage] = []

    def complete_json[T: BaseModel](self, system: str, prompt: str, schema: type[T]) -> T:
        self.calls.append((schema.__name__, prompt))
        answer = next(a for a in self.answers if isinstance(a, (schema, Exception)))
        self.answers.remove(answer)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def stream_text(self, system, messages):  # pragma: no cover - kullanılmaz
        raise NotImplementedError


def mcq(**changes) -> GeneratedQuestion:
    base = dict(
        prompt="Ikili arama her adimda ne yapar?",
        options=["Yarıyı atar", "Baştan tarar", "Diziyi sıralar", "Rastgele seçer"],
        correct_option=0,
        reference_answer="Ortadaki elemanla karşılaştırıp yarıyı atar.",
        explanation="Kaynağa göre her adımda aralığın yarısı atılır.",
        concept="ikili arama adımı",
        evidence_quote=EVIDENCE,
    )
    return GeneratedQuestion(**{**base, **changes})


SHORT = GeneratedQuestion(
    prompt="Ikili arama neden O(log n) zaman alir?",
    reference_answer="Her adımda kalan aralığın yarısı atıldığı için.",
    explanation="Aralık her adımda yarıya iner.",
    concept="ikili arama karmaşıklığı",
    evidence_quote=EVIDENCE,
    criteria=[
        Criterion(description="Yarıya inme", points=2),
        Criterion(description="log n", points=2),
    ],
)


@pytest.fixture
def chunk_id(client: TestClient, course: Course, tmp_path: Path) -> str:
    document = upload(client, course.id, make_pdf(tmp_path / "arama.pdf", LONG_PAGES)).json()
    return str(client.get(f"/documents/{document['id']}/chunks").json()[0]["id"])


def use(monkeypatch, generator: FakeJSON, checker: FakeJSON | None = None) -> None:
    clients = {LLMRole.GENERATOR: generator, LLMRole.CHECKER: checker or generator}
    monkeypatch.setattr(
        practice_api, "select_client", lambda role=LLMRole.GENERATOR: clients.get(role)
    )


def create(client: TestClient, course: Course, **body):
    return client.post("/practice", json={"course_id": course.id, "type": "mcq", **body})


def test_released_mcq_hides_the_key_and_stores_checks_and_rubric(
    client: TestClient, db, course: Course, chunk_id: str, monkeypatch
) -> None:
    checker = FakeJSON("checker", MCQSolution(answerable=True, chosen_option=0, reason="S"))
    use(monkeypatch, FakeJSON("gen", mcq()), checker)

    response = create(client, course, source_id=chunk_id)

    assert response.status_code == 200, response.text
    item = response.json()
    assert item["options"] == ["Yarıyı atar", "Baştan tarar", "Diziyi sıralar", "Rastgele seçer"]
    assert item["source"]["source_id"] == chunk_id
    assert "correct_option" not in json.dumps(item) and "Kaynağa göre" not in json.dumps(item)
    stored = db.get(PracticeQuestion, item["id"])
    assert stored.status == "released" and stored.answer_key == {"correct_option": 0}
    assert [c["name"] for c in stored.checks] == [
        "shape",
        "clarity",
        "distinct_options",
        "evidence_in_source",
        "independent_solve",
    ]
    assert stored.rubric.origin == "generated" and stored.rubric.source_ids == [chunk_id]


def test_failed_candidate_is_kept_as_rejected_and_its_failures_guide_the_retry(
    client: TestClient, db, course: Course, chunk_id: str, monkeypatch
) -> None:
    generator = FakeJSON("gen", mcq(evidence_quote="uydurma bir alinti cumlesi burada"), mcq())
    checker = FakeJSON("checker", MCQSolution(answerable=True, chosen_option=0, reason="S"))
    use(monkeypatch, generator, checker)

    response = create(client, course, source_id=chunk_id)

    statuses = db.scalars(select(PracticeQuestion.status).order_by(PracticeQuestion.id)).all()
    assert response.status_code == 200
    assert statuses == ["rejected", "released"]
    assert "evidence_in_source" in generator.calls[1][1]  # ikinci deneme hatayı biliyor
    assert len(checker.calls) == 1  # belirlenimci kontrolden kalan aday modele çözdürülmez


def test_no_valid_item_after_all_candidates_fail(
    client: TestClient, db, course: Course, chunk_id: str, monkeypatch
) -> None:
    wrong = MCQSolution(answerable=True, chosen_option=2, reason="farklı")
    use(monkeypatch, FakeJSON("gen", mcq(), mcq(), mcq()), FakeJSON("checker", wrong, wrong, wrong))

    response = create(client, course, source_id=chunk_id)

    assert response.status_code == 422 and response.json()["code"] == "no_valid_item"
    assert db.scalars(select(PracticeQuestion.status)).all() == ["rejected"] * 3


def test_topic_without_matching_material_is_no_valid_item(
    client: TestClient, course: Course, chunk_id: str, monkeypatch
) -> None:
    use(monkeypatch, FakeJSON("gen"))

    response = create(client, course, topic="Fransa'nın başkenti")

    assert response.status_code == 422 and response.json()["code"] == "no_valid_item"


def test_topic_finds_a_long_enough_passage(
    client: TestClient, course: Course, chunk_id: str, monkeypatch
) -> None:
    checker = FakeJSON("checker", MCQSolution(answerable=True, chosen_option=0, reason="S"))
    use(monkeypatch, FakeJSON("gen", mcq()), checker)

    response = create(client, course, topic="ikili arama sirali dizi")

    assert response.status_code == 200, response.text
    assert response.json()["source"]["source_id"] == chunk_id


def released(client, course, chunk_id, monkeypatch, question=None, solution=None) -> dict:
    question = question or mcq()
    solution = solution or MCQSolution(answerable=True, chosen_option=0, reason="S")
    extra = [] if isinstance(solution, MCQSolution) else [Agreement(equivalent=True, reason="")]
    use(monkeypatch, FakeJSON("gen", question), FakeJSON("checker", solution, *extra))
    kind = "mcq" if question.options else "short_answer"
    response = create(client, course, source_id=chunk_id, type=kind)
    assert response.status_code == 200, response.text
    return response.json()


def test_mcq_answer_reveals_the_key_and_records_the_attempt(
    client: TestClient, client_for, db, course: Course, chunk_id: str, monkeypatch
) -> None:
    item = released(client, course, chunk_id, monkeypatch)
    student = make_user(db, "ogrenci@example.com", research_logging=True)
    enroll(db, student, course, "student")

    wrong = client_for(student).post(f"/practice/{item['id']}/answer", json={"selected_option": 2})
    right = client_for(student).post(f"/practice/{item['id']}/answer", json={"selected_option": 0})

    assert wrong.status_code == 200, wrong.text
    assert wrong.json()["score"] == 0 and wrong.json()["missing_concepts"] == ["ikili arama adımı"]
    assert wrong.json()["correct_option"] == 0
    assert wrong.json()["explanation"].startswith("Doğru cevap: A) Yarıyı atar.")
    assert right.json()["score"] == 1 and right.json()["understood"] == ["ikili arama adımı"]
    attempts = db.scalars(select(PracticeAttempt).order_by(PracticeAttempt.id)).all()
    assert [(a.user_id, a.selected_option, a.research_logged) for a in attempts] == [
        (student.id, 2, True),
        (student.id, 0, True),
    ]


def test_open_answer_is_graded_against_the_stored_rubric(
    client: TestClient, db, course: Course, chunk_id: str, monkeypatch
) -> None:
    solution = OpenSolution(answerable=True, answer="yarıya iner")
    item = released(client, course, chunk_id, monkeypatch, SHORT, solution)
    grader = FakeJSON(
        "grader",
        GradeOutput(
            criteria=[
                {"index": 0, "awarded": 2, "rationale": "doğru"},
                {"index": 1, "awarded": 9, "rationale": "fazla verildi"},
            ],
            understood=["yarıya inme"],
            missing_concepts=["log n"],
            feedback="Yarıya inmeyi doğru söyledin.",
        ),
    )
    use(monkeypatch, grader)

    response = client.post(f"/practice/{item['id']}/answer", json={"answer_text": "Yarıya iner."})

    body = response.json()
    assert response.status_code == 200, response.text
    assert (body["score"], body["max_score"]) == (4.0, 4.0)  # 9 → ölçüt sınırı 2
    assert body["missing_concepts"] == []  # tam puanda eksik gösterilmez
    assert body["reference_answer"] == "Her adımda kalan aralığın yarısı atıldığı için."
    assert (
        "Her adımda kalan aralığın yarısı atıldığı için." in grader.calls[0][1]
    )  # rubrik + referans


def test_ungradable_open_answer_is_503_and_nothing_is_stored(
    client: TestClient, db, course: Course, chunk_id: str, monkeypatch
) -> None:
    item = released(
        client, course, chunk_id, monkeypatch, SHORT, OpenSolution(answerable=True, answer="x")
    )
    use(monkeypatch, FakeJSON("grader", GradeOutput(criteria=[], feedback="eksik")))

    response = client.post(f"/practice/{item['id']}/answer", json={"answer_text": "Yarıya iner."})

    assert response.status_code == 503
    assert db.scalars(select(PracticeAttempt)).all() == []


def test_answer_type_must_match_the_question(
    client: TestClient, course: Course, chunk_id: str, monkeypatch
) -> None:
    item = released(client, course, chunk_id, monkeypatch)

    response = client.post(f"/practice/{item['id']}/answer", json={"answer_text": "yarı"})
    out_of_range = client.post(f"/practice/{item['id']}/answer", json={"selected_option": 7})

    assert response.status_code == 422 and out_of_range.status_code == 422


def test_outsiders_and_rejected_items_are_not_found(
    client: TestClient, client_for, db, course: Course, chunk_id: str, monkeypatch
) -> None:
    item = released(client, course, chunk_id, monkeypatch)
    wrong = MCQSolution(answerable=True, chosen_option=3, reason="")
    use(monkeypatch, FakeJSON("gen", mcq(), mcq(), mcq()), FakeJSON("c", wrong, wrong, wrong))
    create(client, course, source_id=chunk_id)
    rejected = db.scalars(
        select(PracticeQuestion).where(PracticeQuestion.status == "rejected")
    ).first()
    outsider = client_for(make_user(db, "disaridan@example.com"))

    for item_id, user in ((item["id"], outsider), (rejected.id, client)):
        response = user.post(f"/practice/{item_id}/answer", json={"selected_option": 0})
        assert response.status_code == 404
        assert response.json()["code"] == "practice_item_not_found"


def test_follow_up_targets_the_missing_concepts_of_my_own_attempt(
    client: TestClient, client_for, db, course: Course, chunk_id: str, monkeypatch
) -> None:
    item = released(client, course, chunk_id, monkeypatch)
    attempt = client.post(f"/practice/{item['id']}/answer", json={"selected_option": 1}).json()
    generator = FakeJSON("gen", mcq(prompt="Takip: ikili arama neyi atar?"))
    use(
        monkeypatch,
        generator,
        FakeJSON("c", MCQSolution(answerable=True, chosen_option=0, reason="")),
    )
    other = make_user(db, "baska@example.com")
    enroll(db, other, course, "student")

    follow_up = create(client, course, follow_up_of_attempt_id=attempt["attempt_id"])
    foreign = client_for(other).post(
        "/practice",
        json={
            "course_id": course.id,
            "type": "mcq",
            "follow_up_of_attempt_id": attempt["attempt_id"],
        },
    )

    assert follow_up.status_code == 200, follow_up.text
    assert follow_up.json()["source"]["source_id"] == chunk_id
    assert "Odaklanılacak konu: ikili arama adımı" in generator.calls[0][1]
    # Öğrencinin bu bölümden aldığı soru tekrar sorulmasın diye üreticiye gösterilir.
    assert "Ikili arama her adimda ne yapar?" in generator.calls[0][1]
    stored = db.get(PracticeQuestion, follow_up.json()["id"])
    assert stored.follow_up_of_attempt_id == attempt["attempt_id"]
    assert foreign.status_code == 404


def test_tutor_practice_block_never_contains_the_key(
    client: TestClient, course: Course, chunk_id: str, monkeypatch
) -> None:
    generator = FakeJSON("gen", mcq())
    checker = FakeJSON("checker", MCQSolution(answerable=True, chosen_option=0, reason="S"))
    clients = {LLMRole.GENERATOR: generator, LLMRole.CHECKER: checker, LLMRole.RERANKER: None}
    orchestrator = FakeOrchestrator(
        [ToolCall("generate_practice", {"topic": "ikili arama sirali dizi"}, "p1")]
    )
    monkeypatch.setattr(tutor_api, "select_orchestrator", lambda: orchestrator)
    monkeypatch.setattr(tutor_api, "select_client", lambda role=LLMRole.GENERATOR: clients[role])

    response = client.post(
        "/tutor/turn", json={"course_id": course.id, "message": "Bana bir soru sor"}
    )

    body = response.json()
    assert response.status_code == 200, response.text
    assert [b["type"] for b in body["blocks"]] == ["practice"]
    assert "generate_practice" in orchestrator.tools
    serialized = json.dumps(body, ensure_ascii=False)
    assert "correct_option" not in serialized and "Kaynağa göre" not in serialized
    assert body["trace"]["steps"][0]["status"] == "created"


def test_graded_assignments_are_never_a_practice_source(
    client: TestClient, course: Course, tmp_path: Path, monkeypatch
) -> None:
    pdf = make_pdf(tmp_path / "odev.pdf", LONG_PAGES)
    document = upload(client, course.id, pdf, material_type="assignment").json()
    chunk = client.get(f"/documents/{document['id']}/chunks").json()[0]["id"]
    generator = FakeJSON("gen", mcq())
    use(monkeypatch, generator)

    by_source = create(client, course, source_id=str(chunk))
    by_topic = create(client, course, topic="ikili arama sirali dizi")

    assert by_source.status_code == 422 and "ödev" in by_source.json()["detail"]
    assert by_topic.status_code == 422 and by_topic.json()["code"] == "no_valid_item"
    assert generator.calls == []


def test_quiz_me_uses_the_sources_of_the_answer_just_read(
    client: TestClient, course: Course, chunk_id: str, monkeypatch
) -> None:
    from app.retrieval.rerank import PassageScore, RerankOutput
    from tests.test_answer import FakeLLM
    from tests.test_flow import parse_sse

    answer = FakeLLM(["Ikili arama ortadaki elemanla karsilastirip yariyi atar [S1]."])
    monkeypatch.setattr(tutor_api, "select_orchestrator", lambda: None)
    monkeypatch.setattr(
        tutor_api,
        "select_client",
        lambda role=LLMRole.GENERATOR: answer if role is LLMRole.GENERATOR else None,
    )
    first = client.post(
        "/tutor/turn",
        json={"course_id": course.id, "message": "Ikili arama sirali dizide nasil calisir?"},
    ).json()
    assert first["blocks"][0]["response"]["citations"][0]["source_id"] == chunk_id

    reranker = FakeJSON("reranker", RerankOutput(scores=[PassageScore(label="P1", relevance=3)]))
    clients = {
        LLMRole.GENERATOR: FakeJSON("gen", mcq()),
        LLMRole.CHECKER: FakeJSON(
            "checker", MCQSolution(answerable=True, chosen_option=0, reason="S")
        ),
        LLMRole.RERANKER: reranker,
    }
    orchestrator = FakeOrchestrator([ToolCall("generate_practice", {"topic": "ikili arama"}, "p1")])
    monkeypatch.setattr(tutor_api, "select_orchestrator", lambda: orchestrator)
    monkeypatch.setattr(tutor_api, "select_client", lambda role=LLMRole.GENERATOR: clients[role])
    monkeypatch.setattr(
        "app.practice.service.retrieve", lambda *a, **k: pytest.fail("arama gerekmez")
    )

    response = client.post(
        "/tutor/turn/stream",
        json={
            "course_id": course.id,
            "message": "Bu konuda beni test et",
            "conversation_id": first["conversation_id"],
        },
    )

    events = parse_sse(response.text)
    stages = [data["label"] for name, data in events if name == "status"]
    block = next(data["block"] for name, data in events if name == "block")
    assert block["type"] == "practice" and block["item"]["source"]["source_id"] == chunk_id
    assert stages == [
        "Pratik sorusu hazırlanıyor ve kontrol ediliyor…",
        "Konuyu anlatan bölüm seçiliyor…",
        "Soru yazılıyor…",
        "Soru bağımsız çözümle kontrol ediliyor…",
    ]
    assert [name for name, _ in reranker.calls] == ["RerankOutput"]
