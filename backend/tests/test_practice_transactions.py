"""#94: pratik uç noktalarındaki model çağrıları açık bir veritabanı işlemi içinde beklemez.

Sahte modeller her çağrıda `pg_stat_activity`'ye bakar (gerçek veritabanı).
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Course, PracticeAttempt, PracticeQuestion
from app.generation.grade import GradeOutput
from app.verification.practice_checks import Agreement, OpenSolution
from tests.conftest import make_pdf
from tests.test_flow import upload
from tests.test_practice import LONG_PAGES, SHORT, FakeJSON, create, use
from tests.test_tutor_transactions import open_transactions


class Probing(FakeJSON):
    def __init__(self, db_engine, name, *answers) -> None:
        super().__init__(name, *answers)
        self.db_engine = db_engine
        self.seen: list[int] = []

    def complete_json(self, system, prompt, schema):
        self.seen.append(open_transactions(self.db_engine))
        return super().complete_json(system, prompt, schema)


@pytest.fixture
def chunk_id(client: TestClient, course: Course, tmp_path: Path) -> str:
    document = upload(client, course.id, make_pdf(tmp_path / "arama.pdf", LONG_PAGES)).json()
    return str(client.get(f"/documents/{document['id']}/chunks").json()[0]["id"])


def test_generation_checking_and_grading_run_with_no_open_transaction(
    client: TestClient, db: Session, db_engine, course: Course, chunk_id: str, monkeypatch
) -> None:
    generator = Probing(db_engine, "gen", SHORT)
    checker = Probing(
        db_engine,
        "checker",
        OpenSolution(answerable=True, answer="yarıya iner"),
        Agreement(equivalent=True, reason=""),
    )
    use(monkeypatch, generator, checker)

    created = create(client, course, source_id=chunk_id, type="short_answer")

    assert created.status_code == 200, created.text
    assert generator.seen and checker.seen
    assert set(generator.seen + checker.seen) == {0}
    assert db.scalars(select(PracticeQuestion)).one().status == "released"

    grader = Probing(
        db_engine,
        "grader",
        GradeOutput(
            criteria=[
                {"index": 0, "awarded": 2, "rationale": "doğru"},
                {"index": 1, "awarded": 1, "rationale": "eksik"},
            ],
            understood=["yarıya inme"],
            missing_concepts=["log n"],
            feedback="Yarıya inmeyi doğru söyledin.",
        ),
    )
    use(monkeypatch, grader)

    answered = client.post(
        f"/practice/{created.json()['id']}/answer", json={"answer_text": "Yarıya iner."}
    )

    assert answered.status_code == 200, answered.text
    assert grader.seen == [0]
    assert answered.json()["score"] == 3.0
    db.expire_all()
    assert len(db.scalars(select(PracticeAttempt)).all()) == 1
