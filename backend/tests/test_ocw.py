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
    _resource(root, "zoom", "ZoomNotes for Linear Algebra", "Related Resources", ["Readings"])
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
        (MaterialType.TEXTBOOK, "ZoomNotes for Linear Algebra"),
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


# --- ders videoları ve paketi içeri alma (#28) -------------------------------------------------

CUES = [
    (0.0, 6.0, "binary search halves the sorted range each step"),
    (6.0, 12.0, "so the running time is logarithmic in n"),
]


def _video(
    root: Path,
    name: str,
    title: str,
    youtube_id: str,
    captions: list[tuple[str, str]] | None = None,
    archive_url: str = "",
) -> None:
    """OCW video kaynağı; `captions`: (dil, dosya adı) — dosya pakette oluşturulur."""
    from tests.conftest import make_vtt

    (root / "static_resources").mkdir(parents=True, exist_ok=True)
    resources = []
    for language, stored in captions or []:
        if stored.endswith(".vtt"):
            make_vtt(root / "static_resources" / stored, CUES)
        resources.append({"file": f"/courses/x/{stored}", "language": language})
    _write(
        root / "resources" / name / "data.json",
        {
            "resourcetype": "Video",
            "title": title,
            "parent_title": "Lecture Videos",
            "learning_resource_types": ["Lecture Videos"],
            "video_files": {
                "archive_url": archive_url,
                "video_captions_resources": resources,
            },
            "video_metadata": {"youtube_id": youtube_id},
        },
    )


@pytest.fixture
def video_package(package: Path) -> Path:
    _video(
        package,
        "lecture-10-dfs",
        "Lecture 10: DFS",
        "yt10",
        [("es", f"{'b' * 32}_yt10_es.vtt"), ("en", f"{'c' * 32}_yt10.vtt")],
        "https://archive.org/download/x/lec10.mp4",
    )
    _video(
        package,
        "lecture-2-ds",
        "Lecture 2: Data Structures",  # ders notuyla aynı başlık (gerçek OCW paketinde de öyle)
        "yt2",
        [("en", f"{'d' * 32}_yt2.vtt")],
        "http://www.archive.org/download/old/02.mp4",
    )
    _video(package, "lecture-3-sets", "Lecture 3: Sets", "yt3", [("en", "x_yt3.srt")])
    _video(package, "quiz-review", "Quiz Review", "ytq", [])
    return package


def test_videos_are_read_with_their_captions_youtube_id_and_mp4(video_package: Path) -> None:
    videos, skipped = ocw.list_videos(video_package)

    assert [v.title for v in videos] == ["Lecture 2: Data Structures", "Lecture 10: DFS"]
    dfs = videos[1]
    assert dfs.captions.name == f"{'c' * 32}_yt10.vtt"  # dersin dilindeki altyazı seçilir
    assert dfs.filename == "lecture-10-dfs.vtt"
    assert dfs.media_url == "https://www.youtube.com/watch?v=yt10"
    assert dfs.archive_url == "https://archive.org/download/x/lec10.mp4"
    # Eski paketlerdeki http:// adresi https'e çevrilir.
    assert videos[0].archive_url == "https://www.archive.org/download/old/02.mp4"
    # Altyazısı olmayan ya da VTT olmayan videolar atlanır ve söylenir.
    assert skipped == ["Lecture 3: Sets", "Quiz Review"]


class _FakeStream:
    def __init__(self) -> None:
        import io

        self.body = io.BytesIO(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)

    def __enter__(self):
        return self.body

    def __exit__(self, *exc) -> None:
        return None


@needs_db
def test_package_import_adds_notes_and_videos_and_is_repeatable(
    api, db: Session, video_package: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy import select

    from app.core.config import settings
    from app.db.models import Document, ProcessingJob
    from app.embeddings.fake import FakeEmbedder
    from app.scripts.import_ocw import import_package

    fetched: list[str] = []

    def fetch(url: str) -> _FakeStream:
        fetched.append(url)
        return _FakeStream()

    first = import_package(db, video_package, FakeEmbedder(), log=lambda _: None)

    course = first.course
    assert (course.code, course.language) == ("6.006", "en")
    videos = db.scalars(
        select(Document).where(Document.course_id == course.id, Document.material_type == "video")
    ).all()
    # Ders notuyla aynı başlıklı video da eklenir: tekrar, başlık ve türle belirlenir.
    assert {(v.title, v.media_url, v.filename) for v in videos} == {
        ("Lecture 10: DFS", "https://www.youtube.com/watch?v=yt10", "lecture-10-dfs.vtt"),
        ("Lecture 2: Data Structures", "https://www.youtube.com/watch?v=yt2", "lecture-2-ds.vtt"),
    }
    assert first.videos == 2
    assert all(v.status == "ready" and v.duration_s for v in videos)
    assert first.without_captions == ["Lecture 3: Sets", "Quiz Review"]
    assert fetched == []  # --frames verilmedikçe hiçbir şey indirilmez

    # Tekrar çalıştırmak çoğaltmaz; kareler istenince yalnızca mp4'ü olan video kuyruğa girer.
    monkeypatch.setattr(settings, "frame_extraction", "ocr")
    again = import_package(
        db, video_package, FakeEmbedder(), frames=5, fetch=fetch, log=lambda _: None
    )

    assert again.added == 0 and again.skipped == first.added + first.skipped
    assert fetched == [
        "https://www.archive.org/download/old/02.mp4",
        "https://archive.org/download/x/lec10.mp4",
    ]
    assert again.frames_queued == 2
    jobs = db.scalars(select(ProcessingJob)).all()
    assert {job.kind for job in jobs} == {"frames"} and all(
        Path(j.input_path).is_file() for j in jobs
    )


@needs_db
def test_frames_are_not_queued_when_frame_extraction_is_off(
    api, db: Session, video_package: Path
) -> None:
    from sqlalchemy import select

    from app.db.models import ProcessingJob
    from app.embeddings.fake import FakeEmbedder
    from app.scripts.import_ocw import import_package

    messages: list[str] = []
    summary = import_package(
        db,
        video_package,
        FakeEmbedder(),
        frames=5,
        fetch=lambda url: _FakeStream(),
        log=messages.append,
    )

    assert summary.frames_queued == 0
    assert db.scalars(select(ProcessingJob)).all() == []
    assert any("kapalı" in message for message in messages)


def test_application_code_has_no_course_specific_logic() -> None:
    """Ders, veri ve ayarla eklenir (#28): uygulama kodunda ders koduna bağlı bir dize yoktur.
    Açıklama metinleri (docstring) sayılmaz."""
    import ast

    app_dir = Path(__file__).resolve().parents[1] / "app"
    codes = ("6.006", "6-006", "18.06", "18-06", "BLM2512", "BLM3021")
    offenders = []
    for path in app_dir.rglob("*.py"):
        if "scripts" in path.parts:
            continue  # içe aktarma ve tohum betiklerinin kullanım örnekleri
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
        }
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
            ):
                if any(code in node.value for code in codes):
                    offenders.append(f"{path.name}: {node.value[:60]!r}")
    assert offenders == []
