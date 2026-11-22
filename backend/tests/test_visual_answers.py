"""Görsel kanıtın `/ask` ve AI Tutor'a bağlanması (#26, ADR-12).

İstekte doğrulanmış video bağlamı (#25) varsa durdurulan anın kareleri üreticiye (türetilmiş
metin, konuşma) ve kareye dayanan iddialar görüntüyle judge'a gider; kare alıntısı
`GET /sources/frame:<id>` ile açılır; mesaj kaydına yalnızca kimlikler ve zamanlar yazılır.
Video verilmeyen istek önceki gibidir.

Gerçek veritabanı; üretici ve judge sahtedir (anahtar gerekmez).
"""

import json
import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import ask as ask_api
from app.core.config import settings
from app.db.models import Course, Document, Message, VideoFrame
from app.generation.answer import CLARIFY
from app.llm.base import ChatMessage, ImagePart, LLMError, TextPart
from app.qa import service as qa_service
from app.schemas.ask import AskResponse, VideoRef
from app.schemas.tutor import CourseAnswerBlock, TutorTurnRequest
from app.tutor import service as tutor_service
from tests.conftest import enroll
from tests.test_answer import FakeLLM
from tests.test_claims import FakeJudge
from tests.test_video import LESSON, QUESTION, add_video
from tests.test_visual_grounding import PNG, FakeVisionJudge, _frame

# Modelin netleştirme metnine sızdırdığı, kontrol edilmemiş kare iddiası.
UNCHECKED_CLAIM = "Diyagramda A, B'yi engelliyor."
# Kare görüntüsünün içindekiyle karışmayan, kayıtta aranacak OCR metinleri (`_frame`: "slayt N").
OCR_TEXTS = ("slayt 0", "slayt 1", "slayt 2")
TEXT_CLAIM = "Ikili arama sirali dizide hedef degeri arar [S1]."


class FrameCitingLLM(FakeLLM):
    """Bir metin iddiası ve durdurulan andaki kareyi alıntılayan bir iddia yazan sahte üretici.

    Kare yoksa yalnızca metin iddiasını yazar. `reply` verilirse onu yazar (ör. netleştirme);
    içindeki `{frame}` ekrandaki karenin etiketiyle değiştirilir.
    """

    def __init__(self, reply: str | None = None) -> None:
        super().__init__()
        self.reply = reply

    def stream_text(self, system: str, messages: list[ChatMessage]) -> Iterator[str]:
        self.calls.append((system, messages))
        on_screen = re.search(r'ekrandaki_kare="(S\d+)"', messages[-1]["content"])
        label = on_screen.group(1) if on_screen else None
        if self.reply is not None:
            yield self.reply.replace("{frame}", label or "S99")
            return
        if label is None:
            yield TEXT_CLAIM
            return
        yield f"{TEXT_CLAIM} Slaytta orta elemanin formulu yaziyor [{label}]."

    @property
    def prompt(self) -> str:
        ((_, messages),) = self.calls
        return messages[-1]["content"]


@pytest.fixture
def video(api, db: Session, course: Course) -> tuple[Document, list[VideoFrame]]:
    """Altyazılı onaylı video ve üç saklanan kare (0–100, 100–300, 300–700 sn)."""
    document = add_video(db, course)
    frames = [
        _frame(db, document, 0, 0.0, 100.0),
        _frame(db, document, 1, 100.0, 300.0),
        _frame(db, document, 2, 300.0, 700.0),
    ]
    db.commit()
    return document, frames


@pytest.fixture
def models(monkeypatch: pytest.MonkeyPatch) -> tuple[FrameCitingLLM, FakeVisionJudge]:
    """İddia kontrolü zorunlu; üretici ve görüntü kabul eden judge sahte."""
    llm, judge = FrameCitingLLM(), FakeVisionJudge()
    monkeypatch.setattr(settings, "claim_check", "required")
    monkeypatch.setattr(ask_api, "select_client", lambda: llm)
    monkeypatch.setattr(qa_service, "resolve_judge", lambda: (judge, None))
    return llm, judge


def ask(client: TestClient, course: Course, **video) -> dict:
    body: dict = {"course_id": course.id, "question": QUESTION}
    if video:
        body["video"] = video
    response = client.post("/ask", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def assistant_meta(db: Session) -> dict:
    return db.scalars(select(Message.meta).where(Message.role == "assistant")).one()


def images_sent(judge: FakeVisionJudge) -> list[bytes]:
    return [
        part.data for parts in judge.vision_calls for part in parts if isinstance(part, ImagePart)
    ]


# --- /ask: kareler üreticiye ve judge'a gider ---------------------------------------------------


def test_paused_video_sends_frames_to_the_generator_and_the_image_to_the_judge(
    client: TestClient, db: Session, course: Course, video, models
) -> None:
    document, frames = video
    llm, judge = models

    body = ask(client, course, document_id=document.id, time_s=150)

    assert body["outcome"] == "answered"
    # Üretici: kareler metin parçalarından sonra, durdurulan anda ekrandaki kare işaretli.
    prompt = llm.prompt
    assert prompt.index("</kaynaklar>") < prompt.index("<kareler>") < prompt.index("Soru:")
    assert "slayt 1" in prompt and 'durum="readable"' in prompt
    system, _ = llm.calls[0]
    assert "Video kareleri" in system
    # Judge: kareli iddia görüntüyle kontrol edildi; OCR metni judge'a gitmedi.
    assert images_sent(judge) == [PNG]
    sent_text = "".join(
        p.text for parts in judge.vision_calls for p in parts if isinstance(p, TextPart)
    )
    assert not any(text in sent_text for text in OCR_TEXTS)
    assert body["claim_check"]["prompt_version"] == "claim-judge-v1+visual-claim-judge-v1"
    # Kare alıntısı cevapta kaldı: karenin ekranda kaldığı aralıkla.
    frame_citation = next(c for c in body["citations"] if c["source_id"].startswith("frame:"))
    assert frame_citation == {
        "source_id": f"frame:{frames[1].id}",
        "document_title": document.title,
        "page": None,
        "t_start": 100.0,
        "t_end": 300.0,
    }
    # Görsel kayıt API yanıtına girmez.
    assert "visual" not in body


def test_frame_citation_resolves_through_the_sources_endpoint(
    client: TestClient, db: Session, course: Course, video, models
) -> None:
    document, frames = video

    body = ask(client, course, document_id=document.id, time_s=150)
    source_id = next(
        c["source_id"] for c in body["citations"] if c["source_id"].startswith("frame:")
    )
    detail = client.get(f"/sources/{source_id}")

    assert detail.status_code == 200, detail.text
    detail = detail.json()
    assert detail["source_id"] == source_id == f"frame:{frames[1].id}"
    assert (detail["document_id"], detail["t_start"], detail["t_end"]) == (
        document.id,
        100.0,
        300.0,
    )
    assert [frame["frame_id"] for frame in detail["frames"]] == [frames[1].id]


def test_message_trace_records_frame_ids_and_times_but_no_image_or_ocr_text(
    client: TestClient, db: Session, course: Course, video, models
) -> None:
    document, frames = video

    ask(client, course, document_id=document.id, time_s=150)

    meta = assistant_meta(db)
    visual = meta["visual"]
    # Durdurulan anın penceresindeki kareler (150 − 90 … 150 + 20 sn): ilk iki kare.
    assert visual["frames"] == [
        {
            "frame_id": frame.id,
            "document_id": document.id,
            "t_start": start,
            "t_end": end,
            "t_frame": start,
        }
        for frame, (start, end) in zip(frames[:2], [(0.0, 100.0), (100.0, 300.0)], strict=True)
    ]
    assert visual["judge_images"] == [frames[1].id]
    assert visual["cited"] == [frames[1].id]
    assert f"frame:{frames[1].id}" in meta["cited_source_ids"]
    stored = json.dumps(meta, ensure_ascii=False)
    assert not any(text in stored for text in OCR_TEXTS)
    assert "kare-piksel" not in stored and "iVBOR" not in stored  # görüntü baytı ya da base64


def test_selected_frame_is_always_included_and_focused(
    client: TestClient, db: Session, course: Course, video, models
) -> None:
    document, frames = video
    llm, judge = models

    # 100,5. saniyede ekranda ikinci kare var; öğrenci 1 sn payla bir önceki kareyi seçti.
    body = ask(client, course, document_id=document.id, time_s=100.5, frame_id=frames[0].id)

    assert body["video_context"]["frame"]["frame_id"] == frames[0].id
    # Odak seçilen karededir (0:00–1:40), o anda ekranda olan ikinci karede değil.
    focus = re.search(r'ekrandaki_kare="(S\d+)"', llm.prompt)
    assert focus is not None
    assert f'<kare etiket="{focus.group(1)}" video="{document.title}" zaman="0:00–1:40"' in (
        llm.prompt
    )
    assert f"frame:{frames[0].id}" in [c["source_id"] for c in body["citations"]]
    assert assistant_meta(db)["visual"]["cited"] == [frames[0].id]


def test_frame_claim_the_judge_cannot_see_is_dropped_and_not_cited(
    client: TestClient, db: Session, course: Course, video, models, monkeypatch
) -> None:
    document, _ = video
    llm, _ = models
    # İki metin iddiası: kareli iddia çıkarılınca kapsama yine yeterli kalır.
    llm.reply = f"{TEXT_CLAIM} Arama sirali dizide yapilir [S1]. Slaytta formul var [{{frame}}]."
    text_only_judge = FakeJudge()  # görüntü almıyor
    monkeypatch.setattr(qa_service, "resolve_judge", lambda: (text_only_judge, None))

    body = ask(client, course, document_id=document.id, time_s=150)

    assert body["outcome"] == "answered"
    assert "Slaytta" not in body["answer"]
    assert not any(c["source_id"].startswith("frame:") for c in body["citations"])
    visual = assistant_meta(db)["visual"]
    assert visual["judge_images"] == [] and visual["cited"] == []
    record = assistant_meta(db)["claim_check"]["records"][2]
    assert (record["label"], record["reason"]) == ("unverifiable", "images_not_supported")


def test_text_judge_failure_records_no_image_disclosure(
    client: TestClient, db: Session, course: Course, video, models
) -> None:
    document, _ = video
    _, judge = models
    judge.error = LLMError("metin judge'i erisilemedi")  # metin iddiaları önce kontrol edilir

    body = ask(client, course, document_id=document.id, time_s=150)

    assert body["outcome"] == "verification_failure"
    assert judge.vision_calls == []
    visual = assistant_meta(db)["visual"]
    assert visual["judge_images"] == [] and visual["cited"] == []
    assert len(visual["frames"]) == 2


def test_visual_judge_failure_still_records_the_image_that_was_sent(
    client: TestClient, db: Session, course: Course, video, models
) -> None:
    document, frames = video
    _, judge = models
    judge.vision_error = LLMError("ag hatasi")

    body = ask(client, course, document_id=document.id, time_s=150)

    assert body["outcome"] == "verification_failure"
    assert len(judge.vision_calls) == 1
    assert assistant_meta(db)["visual"]["judge_images"] == [frames[1].id]


def test_streaming_with_frames_sends_no_draft(
    client: TestClient, db: Session, course: Course, video, models, monkeypatch
) -> None:
    document, _ = video
    monkeypatch.setattr(settings, "claim_check", "off")

    with client.stream(
        "POST",
        "/ask/stream",
        json={
            "course_id": course.id,
            "question": QUESTION,
            "video": {"document_id": document.id, "time_s": 150},
        },
    ) as response:
        events = re.findall(r"^event: (\w+)$", response.read().decode(), re.MULTILINE)

    # Kare varken kontrol kapalı olsa da taslak akmaz; kontrol edilmemiş kare iddiası çıkarılır.
    assert "delta" not in events and events[-1] == "done"
    meta = assistant_meta(db)
    assert meta["visual"]["cited"] == []
    assert meta["claim_check"]["records"][0]["reason"] == "not_checked"


# --- Erişim: yalnızca aynı dersin onaylı ve hazır videosu ----------------------------------------


def run_answer_stream(db: Session, course: Course, video: VideoRef) -> AskResponse:
    """API doğrulamasını atlayarak hattı doğrudan çalıştırır (savunma katmanını sınar). Soru
    transkriptin kendi cümlesidir: alakasızlık kapısı videodan bağımsız olarak geçer."""
    done = [
        event
        for event in qa_service.answer_stream(
            db, course, LESSON[0][2], [], ask_api.select_client(), video
        )
        if isinstance(event, qa_service.DoneEvent)
    ]
    return done[0].response


def test_frames_of_another_course_or_an_unapproved_video_never_reach_the_models(
    db: Session, user, course: Course, video, models
) -> None:
    llm, judge = models
    document, frames = video
    other_course = Course(code="BLM9999", name="Baska Ders", language="tr")
    db.add(other_course)
    db.commit()
    enroll(db, user, other_course, "instructor")
    foreign = add_video(db, other_course)
    foreign_frame = _frame(db, foreign, 0, 0.0, 700.0)
    unapproved = add_video(db, course, name="onaysiz.vtt")
    unapproved_frame = _frame(db, unapproved, 0, 0.0, 700.0)
    unapproved.approved_at = None
    db.commit()

    for ref in (
        VideoRef(document_id=foreign.id, time_s=150),
        VideoRef(document_id=unapproved.id, time_s=150),
    ):
        llm.calls.clear()
        response = run_answer_stream(db, course, ref)
        assert "<kareler>" not in llm.prompt
        assert response.visual is None

    # Kendi videosu, ama başka videonun kare kimliği: o kare alınmaz, kendi kareleri alınır.
    llm.calls.clear()
    response = run_answer_stream(
        db, course, VideoRef(document_id=document.id, time_s=150, frame_id=foreign_frame.id)
    )
    assert response.visual is not None
    included = {frame.frame_id for frame in response.visual.frames}
    assert included == {frames[0].id, frames[1].id}
    assert foreign_frame.id not in included and unapproved_frame.id not in included
    assert images_sent(judge) == [PNG]


def test_api_rejects_a_video_of_another_course_before_any_model_call(
    client: TestClient, db: Session, user, course: Course, video, models
) -> None:
    llm, judge = models
    other_course = Course(code="BLM9998", name="Baska Ders 2", language="tr")
    db.add(other_course)
    db.commit()
    enroll(db, user, other_course, "instructor")
    foreign = add_video(db, other_course)
    _frame(db, foreign, 0, 0.0, 700.0)
    db.commit()

    response = client.post(
        "/ask",
        json={
            "course_id": course.id,
            "question": QUESTION,
            "video": {"document_id": foreign.id, "time_s": 150},
        },
    )

    assert response.status_code == 422 and response.json()["code"] == "invalid_video"
    assert llm.calls == [] and judge.vision_calls == []


# --- Yalnızca metin: davranış değişmedi --------------------------------------------------------


def test_text_only_request_sends_no_frames_and_keeps_the_record_unchanged(
    client: TestClient, db: Session, course: Course, video, models
) -> None:
    llm, judge = models

    body = ask(client, course)

    assert body["outcome"] == "answered" and body["video_context"] is None
    system, messages = llm.calls[0]
    assert "Video kareleri" not in system and "<kareler>" not in messages[-1]["content"]
    assert judge.vision_calls == []
    assert body["claim_check"]["prompt_version"] == "claim-judge-v1"
    meta = assistant_meta(db)
    assert set(meta) == {
        "declined",
        "outcome",
        "mode",
        "model",
        "cited_source_ids",
        "claim_check",
        "video",
    }
    assert meta["video"] is None


def test_video_without_stored_frames_answers_from_text_only(
    client: TestClient, db: Session, course: Course, api, models
) -> None:
    llm, judge = models
    document = add_video(db, course)

    body = ask(client, course, document_id=document.id, time_s=150)

    assert body["outcome"] == "answered"
    assert "<kareler>" not in llm.prompt and judge.vision_calls == []
    assert "visual" not in assistant_meta(db)


def test_frames_are_not_loaded_without_a_generator(
    client: TestClient, db: Session, course: Course, video, monkeypatch
) -> None:
    document, _ = video
    monkeypatch.setattr(ask_api, "select_client", lambda: None)

    body = ask(client, course, document_id=document.id, time_s=150)

    assert body["mode"] == "extractive"
    assert not any(c["source_id"].startswith("frame:") for c in body["citations"])
    assert "visual" not in assistant_meta(db)


# --- Netleştirme ---------------------------------------------------------------------------------


def test_ambiguous_scene_returns_a_clarification_outcome(
    client: TestClient, db: Session, course: Course, video, models
) -> None:
    document, frames = video
    llm, judge = models
    llm.reply = f"NETLEŞTİR: {UNCHECKED_CLAIM} Hangi oku kastediyorsun?"

    body = ask(client, course, document_id=document.id, time_s=150)

    assert body["outcome"] == "needs_clarification"
    assert body["declined"] is True and body["answer"] is None
    # Kontrol edilmemiş kare iddiası öğrenciye ve kayda ulaşmaz; sabit soru gösterilir.
    assert body["decline_reason"] == CLARIFY
    assert "engelliyor" not in json.dumps(body, ensure_ascii=False)
    assert "engelliyor" not in json.dumps(assistant_meta(db), ensure_ascii=False)
    assert judge.prompts == [] and judge.vision_calls == []
    meta = assistant_meta(db)
    assert meta["outcome"] == "needs_clarification"
    assert meta["visual"]["judge_images"] == [] and meta["visual"]["cited"] == []
    assert len(meta["visual"]["frames"]) == 2
    content = db.scalars(select(Message.content).where(Message.role == "assistant")).one()
    assert content == body["decline_reason"]


def test_judge_finding_the_frame_ambiguous_asks_for_clarification(
    client: TestClient, db: Session, course: Course, video, models
) -> None:
    document, frames = video
    llm, judge = models
    llm.reply = (
        "Slaytta orta elemanin formulu yaziyor [{frame}]. Formulde iki indeks var [{frame}]."
    )
    judge.see = lambda claim_id, cites: ("ambiguous", [], "")

    body = ask(client, course, document_id=document.id, time_s=150)

    assert body["outcome"] == "needs_clarification" and body["declined"] is True
    assert body["decline_reason"] == CLARIFY
    assert body["claim_check"]["unsupported"] == 0
    assert images_sent(judge) == [PNG]
    meta = assistant_meta(db)
    assert meta["visual"]["judge_images"] == [frames[1].id] and meta["visual"]["cited"] == []
    assert [r["reason"] for r in meta["claim_check"]["records"]] == ["ambiguous_scene"] * 2


# --- AI Tutor -----------------------------------------------------------------------------------


def test_tutor_course_answer_uses_the_paused_frames(
    db: Session, user, course: Course, video, models
) -> None:
    document, frames = video
    llm, judge = models
    request = TutorTurnRequest(
        course_id=course.id,
        message=QUESTION,
        video=VideoRef(document_id=document.id, time_s=150, frame_id=frames[1].id),
    )

    response = tutor_service.turn(db, course, request, None, llm, user)

    (block, *_) = response.blocks
    assert isinstance(block, CourseAnswerBlock) and block.response.outcome == "answered"
    assert f"frame:{frames[1].id}" in [c.source_id for c in block.response.citations]
    assert images_sent(judge) == [PNG]
    meta = assistant_meta(db)
    assert meta["visual"]["cited"] == [frames[1].id]
    assert meta["video"]["frame_id"] == frames[1].id
    # Bloklar öğrenciye giden yanıttır: görsel kayıt bloklara girmez.
    assert "visual" not in meta["blocks"][0]["response"]


def test_tutor_reports_a_clarification_and_offers_no_follow_ups(
    db: Session, user, course: Course, video, models
) -> None:
    document, _ = video
    llm, _ = models
    llm.reply = f"NETLEŞTİR: {UNCHECKED_CLAIM} Hangi oku kastediyorsun?"
    request = TutorTurnRequest(
        course_id=course.id,
        message=QUESTION,
        video=VideoRef(document_id=document.id, time_s=150),
    )

    response = tutor_service.turn(db, course, request, None, llm, user)

    assert [block.type for block in response.blocks] == ["course_answer"]
    (block,) = response.blocks
    assert isinstance(block, CourseAnswerBlock)
    assert block.response.outcome == "needs_clarification"
    assert block.response.decline_reason == CLARIFY
    assert response.trace.steps[0].status == "needs_clarification"
    meta = assistant_meta(db)
    assert meta["outcome"] == "needs_clarification"
    # Öğrenciye giden blok, kayıttaki bloklar ve sohbet metni kontrol edilmemiş iddiayı taşımaz.
    assert "engelliyor" not in response.model_dump_json()
    assert "engelliyor" not in json.dumps(meta, ensure_ascii=False)
    content = db.scalars(select(Message.content).where(Message.role == "assistant")).one()
    assert content == CLARIFY
