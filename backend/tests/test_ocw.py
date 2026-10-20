"""OCW "Download Course" paketi okuma: ders bilgisi, dosya türleri, izlence ve takvim."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Course, User
from app.ingestion import ocw
from app.schemas.materials import MaterialType
from tests.conftest import SAMPLE_PAGES, TEST_DATABASE_URL, enroll, make_pdf, make_user

SYLLABUS_HTML = """
    <h3 id="prerequisites">Prerequisites</h3>
<ul>
<li><em><a href="https://ocw.mit.edu/x">6.0001 Intro</a></em>:  Basic   Python.</li>
</ul>
<p>Read the <a href="../x">notes</a> &amp; practice.</p>
    <h3>Grading</h3>
<p><table>
<thead><tr><th>Assignments</th><th>Percentages</th></p></tr>
<p></thead>
<tr><td>Quiz 1</td><td>20%</td></p><p></tr>
</table>
"""

# OCW takvim tablosu: <p> etiketleri hücre sınırlarını aşar (geçersiz HTML).
CALENDAR_HTML = """<p>Lectures occured on Tuesdays.</p>
<p><table><thead><tr><th>Week</th><th>Lectures</th><th>Key Dates</th></p></tr><p></thead>
<tr><td></p><p>1</p><p></td>
<td></p><p>Lecture 1: Introduction</p><p>Lecture 2: Data Structures</p><p></td>
<td></p><p>Problem Set 0 Due</p></td><p></tr>
<tr><td></p><p>2</p><p></td><td colspan="2"></p><p>Final Exam</p></td></tr>
</table>"""


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _resource(root: Path, name: str, title: str, section: str | None, types: list[str]) -> None:
    stored = f"{'a' * 32}_{name}.pdf"
    (root / "static_resources").mkdir(exist_ok=True)
    make_pdf(root / "static_resources" / stored, SAMPLE_PAGES[:1])
    _write(
        root / "resources" / name / "data.json",
        {
            "file": f"/courses/x/{stored}",
            "file_type": "application/pdf",
            "title": title,
            "parent_title": section,
            "learning_resource_types": types,
        },
    )


@pytest.fixture
def package(tmp_path: Path) -> Path:
    root = tmp_path / "ocw"
    _write(
        root / "data.json",
        {
            "primary_course_number": "6.006",
            "course_title": "Introduction to Algorithms",
            "course_description": "Data structures and algorithms.\n",
            "instructors": [{"title": "Prof. Erik Demaine"}, {"title": "Dr. Jason Ku"}],
            "department_numbers": ["6"],
            "level": ["Undergraduate"],
            "term": "Spring",
            "year": "2020",
        },
    )
    _write(root / "pages" / "syllabus" / "data.json", {"content": SYLLABUS_HTML})
    _write(root / "pages" / "calendar" / "data.json", {"content": CALENDAR_HTML})
    _resource(root, "lec10", "Lecture 10: Depth-First Search", "Lecture Notes", ["Lecture Notes"])
    _resource(root, "lec2", "Lecture 2: Data Structures", "Lecture Notes", ["Lecture Notes"])
    _resource(root, "q3", "Quiz 3", None, ["Exams"])
    _resource(root, "ps1", "Problem Set 1", "Assignments", ["Problem Sets"])
    _resource(root, "prob1", "Problem Session 1", "Practice Problems", ["Problem-solving Notes"])
    _resource(root, "3play", "3play pdf file", None, [])
    return root


def test_reads_course_info_with_license_note(package: Path) -> None:
    info = ocw.read_course(package)

    assert (info.code, info.name, info.term, info.level) == (
        "6.006",
        "Introduction to Algorithms",
        "Spring 2020",
        "undergraduate",
    )
    assert info.instructor_name == "Prof. Erik Demaine, Dr. Jason Ku"
    assert info.department == "Electrical Engineering and Computer Science"
    assert info.description.endswith(ocw.LICENSE_NOTE)


def test_files_are_typed_by_section_and_naturally_ordered(package: Path) -> None:
    files = ocw.list_files(package)

    assert [(f.material_type, f.title) for f in files] == [
        (MaterialType.ASSIGNMENT, "Problem Set 1"),
        (MaterialType.NOTES, "Lecture 2: Data Structures"),
        (MaterialType.NOTES, "Lecture 10: Depth-First Search"),
        (MaterialType.PAST_EXAM, "Quiz 3"),
        (MaterialType.PRACTICE_PROBLEM, "Problem Session 1"),
    ]
    assert files[0].filename == "ps1.pdf"


def test_syllabus_becomes_plain_text_blocks(package: Path) -> None:
    assert ocw.read_syllabus(package) == [
        {"type": "heading", "text": "Prerequisites"},
        {"type": "list", "items": ["6.0001 Intro: Basic Python."]},
        {"type": "paragraph", "text": "Read the notes & practice."},
        {"type": "heading", "text": "Grading"},
        {"type": "table", "rows": [["Assignments", "Percentages"], ["Quiz 1", "20%"]]},
    ]


def test_calendar_survives_broken_table_html(package: Path) -> None:
    assert ocw.read_calendar(package) == {
        "intro": "Lectures occured on Tuesdays.",
        "columns": ["Hafta", "Dersler", "Önemli tarihler"],
        "rows": [
            [
                {"lines": ["1"], "span": 1},
                {"lines": ["Lecture 1: Introduction", "Lecture 2: Data Structures"], "span": 1},
                {"lines": ["Problem Set 0 Due"], "span": 1},
            ],
            [{"lines": ["2"], "span": 1}, {"lines": ["Final Exam"], "span": 2}],
        ],
    }


def test_missing_pages_give_no_outline(tmp_path: Path) -> None:
    assert ocw.read_syllabus(tmp_path) is None
    assert ocw.read_calendar(tmp_path) is None


needs_db = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL tanımlı değil")


@needs_db
def test_outline_endpoint(client: TestClient, course: Course, db: Session, package: Path) -> None:
    assert client.get(f"/courses/{course.id}/outline").json() == {
        "syllabus": None,
        "calendar": None,
    }

    course.syllabus = ocw.read_syllabus(package)
    course.calendar = ocw.read_calendar(package)
    db.commit()
    outline = client.get(f"/courses/{course.id}/outline").json()

    assert outline["syllabus"][0] == {
        "type": "heading",
        "text": "Prerequisites",
        "items": None,
        "rows": None,
    }
    assert outline["calendar"]["rows"][1][1] == {"lines": ["Final Exam"], "span": 2}
    assert client.get("/courses/999999/outline").status_code == 404


@needs_db
def test_outline_is_for_course_members_only(
    client_for: Callable[[User | None], TestClient], course: Course, db: Session
) -> None:
    student = make_user(db, "ogrenci@example.com")
    enroll(db, student, course, "student")
    outsider = make_user(db, "baska@example.com")
    path = f"/courses/{course.id}/outline"

    assert client_for(student).get(path).status_code == 200
    assert client_for(outsider).get(path).status_code == 404
    assert client_for(None).get(path).status_code == 401
