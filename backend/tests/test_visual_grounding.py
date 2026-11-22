"""Görsel kanıtla cevap (#26): kareye dayanan iddialar karenin görüntüsüyle kontrol edilir.

Üretici ve judge sahte istemcilerdir (anahtar gerekmez). Görüntü kabul eden sahte judge,
görsel isteğin parçalarını kaydeder; testler judge'a türetilmiş metnin (OCR) gitmediğini ve
görüntünün gittiğini doğrular. Veritabanı gerektiren testler `TEST_DATABASE_URL` yoksa atlanır.
"""

import base64
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import openai
import pytest
from google.genai import types
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import Course, Document, VideoFrame
from app.generation.answer import CLARIFY, CLARIFY_PREFIX, VISUAL_RULES, stream_answer
from app.generation.visual import (
    FrameImage,
    FrameLocator,
    StoredFrameSource,
    VisualContext,
    VisualEvidence,
    format_frames,
    read_frame_image,
)
from app.ingestion.documents import frame_dir
from app.llm import hosted
from app.llm.base import (
    ImageInputUnsupported,
    ImagePart,
    LLMError,
    TextPart,
    supports_images,
)
from app.llm.local import LocalLLMClient
from app.llm.openrouter import OpenRouterLLMClient, _content_part, _rejects_images
from app.llm.release import ReleasingClient
from app.llm.routing import LocalRouteUnavailable
from app.retrieval.types import VideoPosition
from app.schemas.ask import AskResponse
from app.verification.citations import claim_units
from app.verification.claims import check_claims
from app.verification.judge import JudgeContractError
from app.verification.visual import (
    VISUAL_JUDGE_PROMPT_VERSION,
    VisualClaimVerdict,
    VisualFact,
    VisualJudgeOutput,
    validate_visual_verdicts,
)
from tests.test_answer import COURSE, PASSAGES, RELEVANT, FakeLLM
from tests.test_claims import FakeJudge
from tests.test_gemini import FakeModels, gemini, response

PNG = b"\x89PNG\r\n\x1a\n" + b"kare-piksel"
DERIVED = "Dijkstra O(V^2) GIZLI-OCR-METNI"


def frame(frame_id: int = 7, image: bool = True, **kwargs) -> VisualEvidence:
    values = {
        "frame_id": frame_id,
        "course_id": 1,
        "document_id": 30,
        "document_title": "Ders 5 videosu",
        "t_start": 190.0,
        "t_end": 410.0,
        "t_frame": 192.0,
        "status": "readable",
        "derived_text": DERIVED,
        "derived_by": "tesseract/5.5.0/tur+eng",
        "confidence": 0.93,
        "transcript": "Simdi grafa bakalim.",
        "image": FrameImage(PNG, "image/png") if image else None,
    }
    values.update(kwargs)
    return VisualEvidence(**values)


Decide = Callable[[str, list[str]], tuple[str, list[str], str]]


class FakeVisionJudge(FakeJudge):
    """Metin iddiaları `FakeJudge` gibi; kareli iddialar `see(claim_id, cites)` kararıyla.

    `see` (karar, destek kaynakları, görüntüde görülen) döndürür.
    """

    accepts_images = True

    def __init__(self, see: Decide | None = None, error: Exception | None = None, **kwargs):
        super().__init__(**kwargs)
        self.see = see or (lambda claim_id, cites: ("supported", cites[-1:], "karede yaziyor"))
        self.vision_error = error
        self.vision_calls: list[list] = []

    def complete_json_with_images[T: BaseModel](self, system: str, parts: list, schema: type[T]):
        self.vision_calls.append(parts)
        if self.vision_error:
            raise self.vision_error
        claims = "".join(part.text for part in parts if isinstance(part, TextPart))
        verdicts = []
        for line in claims.splitlines():
            if not line.startswith("<claim "):
                continue
            claim_id = line.split('id="')[1].split('"')[0]
            cites = line.split('cites="')[1].split('"')[0].split(",")
            decision, sources, observed = self.see(claim_id, cites)
            verdicts.append(
                VisualClaimVerdict(
                    claim_id=claim_id,
                    atomic_facts=[
                        VisualFact(
                            fact="bilgi",
                            decision=decision,
                            supporting_sources=sources,
                            observed=observed,
                        )
                    ],
                )
            )
        return VisualJudgeOutput(verdicts=verdicts)  # type: ignore[return-value]


def run(llm, judge=None, visual=None, mode="required", retrieval=RELEVANT):
    items = list(
        stream_answer(
            COURSE,
            "Bu diyagram ne?",
            [],
            retrieval,
            llm,
            judge=judge,
            claim_check=mode,
            visual=visual,
        )
    )
    *deltas, final = items
    assert isinstance(final, AskResponse)
    return deltas, final


VISUAL = VisualContext(frames=[frame()], focus=VideoPosition(30, 200.0))
# S1, S2 metin parçaları; S3 kare.
VISUAL_ANSWER = "Arama her adimda yariya iner [S1]. Diyagramda kaynak dugumden kuyruga ok var [S3]."


# --- Yalnızca metin: davranış değişmedi ---


def test_text_only_answer_is_identical_with_and_without_an_empty_visual_context() -> None:
    answer = "Dizi sirali oldugu icin sag yari elenir [S1]. Karmasiklik O(log n) olur [S2]."
    results = []
    for visual in (None, VisualContext(), VisualContext(frames=[], focus=VideoPosition(30, 5.0))):
        llm, judge = FakeLLM([answer]), FakeJudge()
        deltas, response_ = run(llm, judge, visual=visual)
        results.append((llm.calls, judge.prompts, deltas, response_.model_dump()))
    assert results[0] == results[1] == results[2]
    ((system, messages),) = results[0][0]
    assert "Video kareleri" not in system and "<kareler>" not in messages[-1]["content"]
    assert results[0][3]["claim_check"]["prompt_version"] == "claim-judge-v1"


def test_text_only_claim_check_keeps_records_and_counts_unchanged() -> None:
    labels = {"S1": PASSAGES[0], "S2": PASSAGES[1]}
    answer = "Sag yari elenir burada [S1]. Karmasiklik O(log n) olur [S2]."
    judge = FakeJudge(
        decide=lambda claim_id, cites: (
            ("unsupported", []) if claim_id == "C2" else ("supported", cites[:1])
        )
    )

    checked = check_claims(answer, labels, judge, "required")

    assert checked.removed == checked.check.unsupported == 1 and checked.ambiguous == 0
    assert [set(record) for record in checked.check.records] == [
        {
            "claim_id",
            "claim",
            "cited_source_ids",
            "label",
            "judge_model",
            "reason",
            "facts",
            "rationale",
        }
    ] * 2
    assert [r["claim_id"] for r in checked.check.records] == ["C1", "C2"]


# --- Kareye dayanan iddia: görüntüyle doğrulanır ---


def test_frame_grounded_claim_is_verified_against_the_image_not_the_caption() -> None:
    judge = FakeVisionJudge()

    _, result = run(FakeLLM([VISUAL_ANSWER]), judge, visual=VISUAL)

    assert result.outcome == "answered" and result.answer is not None
    assert [c.source_id for c in result.citations] == ["11", "frame:7"]
    assert (result.citations[1].t_start, result.citations[1].t_end) == (190.0, 410.0)
    # Metin iddiası metin judge'ına, kareli iddia görsel çağrıya; görüntü gitti, OCR metni gitmedi.
    assert len(judge.prompts) == 1 and "S3" not in judge.prompts[0]
    (parts,) = judge.vision_calls
    images = [part for part in parts if isinstance(part, ImagePart)]
    assert images == [ImagePart(PNG, "image/png")]
    sent_text = "".join(part.text for part in parts if isinstance(part, TextPart))
    assert DERIVED not in sent_text and "Simdi grafa" not in sent_text
    check = result.claim_check
    assert check is not None and check.claims == 2 and check.unsupported == 0
    assert check.prompt_version == f"claim-judge-v1+{VISUAL_JUDGE_PROMPT_VERSION}"
    first, second = check.records
    assert (first["claim_id"], second["claim_id"]) == ("C1", "C2")
    assert second["label"] == "supported" and second["facts"][0]["observed"]
    assert second["frames"] == [
        {
            "source_id": "frame:7",
            "frame_id": 7,
            "document_id": 30,
            "t_start": 190.0,
            "t_end": 410.0,
            "t_frame": 192.0,
            "status": "readable",
            "derived_by": "tesseract/5.5.0/tur+eng",
            "image_sent": True,
        }
    ]


def test_generator_sees_frames_with_provenance_and_the_focus_frame() -> None:
    llm = FakeLLM([VISUAL_ANSWER])

    run(llm, FakeVisionJudge(), visual=VISUAL)

    ((system, messages),) = llm.calls
    prompt = messages[-1]["content"]
    assert system.endswith(VISUAL_RULES.format(clarify=CLARIFY_PREFIX))
    assert prompt.index("</kaynaklar>") < prompt.index("<kareler>") < prompt.index("Soru:")
    assert 'etiket="S3" video="Ders 5 videosu" zaman="3:10–6:50"' in prompt
    assert f'<türetilmiş_metin kaynak="tesseract/5.5.0/tur+eng">{DERIVED}' in prompt
    assert '<durdurulan_an zaman="3:20" ekrandaki_kare="S3"/>' in prompt


def test_frame_claim_the_image_does_not_show_is_removed() -> None:
    judge = FakeVisionJudge(see=lambda claim_id, cites: ("unsupported", [], ""))

    _, result = run(
        FakeLLM([VISUAL_ANSWER + " Ikili arama O(log n) zaman alir [S2]."]), judge, visual=VISUAL
    )

    assert result.outcome == "answered"
    assert "Diyagramda" not in (result.answer or "")
    assert "frame:7" not in [c.source_id for c in result.citations]
    assert result.claim_check is not None and result.claim_check.unsupported == 1
    assert result.unsupported_removed == 1
    assert result.claim_check.records[1]["reason"] == "unsupported_fact"


def test_support_from_a_frame_without_saying_what_is_visible_is_not_accepted() -> None:
    judge = FakeVisionJudge(see=lambda claim_id, cites: ("supported", ["S3"], " "))
    labels = {"S1": PASSAGES[0], "S3": frame().as_passage()}

    checked = check_claims(
        "Diyagramda kaynaktan kuyruga ok var [S3].",
        labels,
        judge,
        "required",
        frames={"S3": frame()},
    )

    assert checked.check.records[0]["label"] == "unverifiable"
    assert checked.check.records[0]["reason"] == "no_visual_observation"
    assert checked.removed == 1 and checked.text.strip() == ""


def test_visual_judge_output_that_does_not_match_the_claims_fails_the_check() -> None:
    judge = FakeVisionJudge()
    judge.complete_json_with_images = lambda system, parts, schema: VisualJudgeOutput(verdicts=[])

    _, result = run(FakeLLM([VISUAL_ANSWER]), judge, visual=VISUAL)

    assert result.outcome == "verification_failure" and result.mode == "extractive"
    assert result.claim_check is not None and result.claim_check.status == "failed"
    assert "frame:" not in str([c.source_id for c in result.citations])


def test_visual_judge_giving_two_verdicts_for_one_claim_breaks_the_contract() -> None:
    labels = {"S3": frame().as_passage()}
    _, units = claim_units("Diyagramda kaynaktan kuyruga ok var [S3].", labels)
    twice = VisualJudgeOutput(
        verdicts=[
            VisualClaimVerdict(
                claim_id="C1",
                atomic_facts=[
                    VisualFact(fact="x", decision="supported", supporting_sources=["S3"])
                ],
            )
        ]
        * 2
    )
    with pytest.raises(JudgeContractError):
        validate_visual_verdicts(units, labels, {"S3": frame()}, twice, "m")


# --- Görüntü yoksa ya da judge görüntü kabul etmiyorsa: kontrol edilemez ---


def test_caption_only_frame_claim_is_not_accepted_even_if_the_caption_states_it() -> None:
    judge = FakeVisionJudge()
    visual = VisualContext(frames=[frame(image=False)])
    answer = "Arama her adimda yariya iner [S1]. Slaytta Dijkstra O(V^2) yaziyor [S3]."

    _, result = run(FakeLLM([answer]), judge, visual=visual)

    assert judge.vision_calls == []  # görüntü yok: judge'a sorulmadı
    assert all(DERIVED not in prompt for prompt in judge.prompts)
    assert "Dijkstra" not in (result.answer or "")
    assert "frame:7" not in [c.source_id for c in result.citations]
    record = result.claim_check.records[1]  # type: ignore[union-attr]
    assert (record["label"], record["reason"]) == ("unverifiable", "image_unavailable")
    assert record["frames"][0]["image_sent"] is False
    assert result.claim_check.unsupported == 0  # type: ignore[union-attr]


def test_judge_without_image_support_marks_frame_claims_unverifiable() -> None:
    judge = FakeJudge()  # görüntü yöntemi yok
    assert not supports_images(judge)

    _, result = run(
        FakeLLM([VISUAL_ANSWER + " Ikili arama O(log n) zaman alir [S2]."]), judge, visual=VISUAL
    )

    assert result.outcome == "answered"
    assert "Diyagramda" not in (result.answer or "")
    assert all("S3" not in prompt for prompt in judge.prompts)
    record = result.claim_check.records[1]  # type: ignore[union-attr]
    assert (record["label"], record["reason"]) == ("unverifiable", "images_not_supported")


def test_model_that_rejects_images_marks_frame_claims_unverifiable() -> None:
    judge = FakeVisionJudge(error=ImageInputUnsupported("model goruntu almiyor"))

    _, result = run(
        FakeLLM([VISUAL_ANSWER + " Ikili arama O(log n) zaman alir [S2]."]), judge, visual=VISUAL
    )

    assert result.outcome == "answered" and "Diyagramda" not in (result.answer or "")
    assert result.claim_check.records[1]["reason"] == "images_not_supported"  # type: ignore[union-attr]


def test_provider_error_during_the_visual_check_fails_the_whole_check() -> None:
    judge = FakeVisionJudge(error=LLMError("ag hatasi"))

    _, result = run(FakeLLM([VISUAL_ANSWER]), judge, visual=VISUAL)

    assert result.outcome == "verification_failure"


def test_frame_claims_are_dropped_when_claim_check_is_off() -> None:
    deltas, result = run(
        FakeLLM(
            ["Arama her adimda ", "yariya iner [S1]. Diyagramda kaynak ", "dugumden ok var [S3]."]
            + [" Ikili arama O(log n) zaman alir [S2]."]
        ),
        visual=VISUAL,
        mode="off",
    )

    # Kare varken taslak akmaz: kontrol edilmemiş kare iddiası hiçbir parçada öğrenciye ulaşmaz.
    assert deltas == []
    assert result.outcome == "answered" and "Diyagramda" not in (result.answer or "")
    assert result.claim_check is not None and result.claim_check.status == "off"
    assert result.claim_check.records[0]["reason"] == "not_checked"


def test_rejected_frame_claim_never_appears_in_any_delta() -> None:
    chunks = ["Arama her adimda yariya iner [S1]. ", "Diyagramda kaynaktan kuyruga ok var [S3]."]
    for mode, judge in (
        ("off", None),
        ("required", FakeVisionJudge(see=lambda claim_id, cites: ("unsupported", [], ""))),
    ):
        deltas, result = run(
            FakeLLM(chunks + [" Karmasiklik O(log n) olur [S2]."]), judge, visual=VISUAL, mode=mode
        )

        assert all("Diyagramda" not in delta for delta in deltas)
        assert "Diyagramda" not in (result.answer or "")


def test_text_only_answer_still_streams_drafts_when_claim_check_is_off() -> None:
    deltas, _ = run(FakeLLM(["Sag yari ", "elenir [S1]."]), mode="off")

    assert "".join(deltas) == "Sag yari elenir [S1]."


# --- Karışık alıntı: kare alıntısı yalnızca görüntüden doğrulanınca kalır ---

MIXED_ANSWER = (
    "Arama her adimda yariya iner [S1][S3]. Diyagramda kaynaktan kuyruga ok var [S3]. "
    "Karmasiklik O(log n) olur [S2]. Sag yari elenir bu yuzden [S1]."
)


def test_frame_citation_supported_only_by_text_is_dropped_from_the_answer() -> None:
    # Metin (S1) iddiayı destekliyor; görüntü desteklemiyor (judge kareyi destek göstermedi).
    # Kareye dayanan ikinci iddia ise görüntüyle çelişiyor.
    def see(claim_id: str, cites: list[str]) -> tuple[str, list[str], str]:
        return ("supported", ["S1"], "") if claim_id == "C1" else ("unsupported", [], "")

    _, result = run(FakeLLM([MIXED_ANSWER]), FakeVisionJudge(see=see), visual=VISUAL)

    assert result.outcome == "answered"
    assert result.answer == (
        "Arama her adimda yariya iner [1]. Karmasiklik O(log n) olur [2]. "
        "Sag yari elenir bu yuzden [1]."
    )
    assert [c.source_id for c in result.citations] == ["11", "12"]
    first, second = result.claim_check.records[:2]  # type: ignore[union-attr]
    assert first["label"] == "supported" and first["dropped_frame_citations"] == ["frame:7"]
    assert second["label"] == "unsupported" and second["dropped_frame_citations"] == []


def test_frame_citation_validated_from_the_image_is_kept() -> None:
    judge = FakeVisionJudge(see=lambda claim_id, cites: ("supported", cites, "karede ok var"))

    _, result = run(FakeLLM([MIXED_ANSWER]), judge, visual=VISUAL)

    assert [c.source_id for c in result.citations] == ["11", "frame:7", "12"]
    assert result.answer is not None and result.answer.startswith(
        "Arama her adimda yariya iner [1][2]."
    )
    assert result.claim_check.records[0]["dropped_frame_citations"] == []  # type: ignore[union-attr]


# --- Belirsiz sahne: netleştirme ---


UNCHECKED_CLAIM = "Diyagramda A, B'yi engelliyor."


def test_generator_asks_for_clarification_when_the_scene_is_ambiguous() -> None:
    judge = FakeVisionJudge()
    for mode in ("off", "required"):
        deltas, result = run(
            FakeLLM(["NETLE", f"ŞTİR: {UNCHECKED_CLAIM} Hangi oku kastediyorsun?"]),
            judge,
            visual=VISUAL,
            mode=mode,
        )

        assert deltas == []  # netleştirme taslak olarak akmaz
        assert result.declined and result.answer is None
        assert result.outcome == "needs_clarification"
        # Modelin NETLEŞTİR'den sonra yazdığı metin kontrol edilmedi: öğrenciye sabit soru gider.
        assert result.decline_reason == CLARIFY
        assert "engelliyor" not in result.model_dump_json()
    assert judge.prompts == [] and judge.vision_calls == []


def test_images_are_recorded_only_when_the_visual_request_is_sent() -> None:
    labels = {"S1": PASSAGES[0], "S3": frame().as_passage()}
    answer = "Arama her adimda yariya iner [S1]. Diyagramda kaynaktan kuyruga ok var [S3]."

    # Metin judge'ı önce hata verir: görsel istek hiç gitmez, görüntü gönderilmiş sayılmaz.
    text_fails = FakeVisionJudge()
    text_fails.error = LLMError("metin judge'i erisilemedi")
    checked = check_claims(answer, labels, text_fails, "required", frames={"S3": frame()})
    assert checked.check.status == "failed"
    assert text_fails.vision_calls == [] and checked.images_sent == []

    # Görsel istek gönderildi, sonra hata verdi: görüntü gönderilmiştir, kayda girer.
    vision_fails = FakeVisionJudge(error=LLMError("ag hatasi"))
    checked = check_claims(answer, labels, vision_fails, "required", frames={"S3": frame()})
    assert checked.check.status == "failed"
    assert len(vision_fails.vision_calls) == 1 and checked.images_sent == [7]

    # Görüntü yok ya da judge görüntü almıyor: istek gitmez.
    for judge, frames in ((FakeVisionJudge(), {"S3": frame(image=False)}), (FakeJudge(), None)):
        checked = check_claims(answer, labels, judge, "required", frames=frames or {"S3": frame()})
        assert checked.images_sent == []


def test_clarify_prefix_is_not_special_without_visual_context() -> None:
    # Yalnızca metinde "NETLEŞTİR:" önceki gibi alıntısız metindir; doğrulamadan geçemez.
    _, result = run(FakeLLM(["NETLEŞTİR: Hangi kismi kastediyorsun acaba?"]), mode="off")

    assert result.outcome == "unsupported"
    assert result.decline_reason != CLARIFY


def test_checker_ambiguity_leads_to_a_clarification_request() -> None:
    judge = FakeVisionJudge(see=lambda claim_id, cites: ("ambiguous", [], ""))
    answer = (
        "Diyagramda kaynak dugumden kuyruga ok var [S3]. Kuyruktan hedefe ikinci ok gider [S3]."
    )

    _, result = run(FakeLLM([answer]), judge, visual=VISUAL)

    assert result.declined and result.decline_reason == CLARIFY
    assert result.outcome == "needs_clarification"
    assert result.unsupported_removed == 2
    assert [r["reason"] for r in result.claim_check.records] == ["ambiguous_scene"] * 2  # type: ignore[union-attr]
    assert result.claim_check.unsupported == 0  # type: ignore[union-attr]


def test_ambiguous_frame_claim_is_dropped_but_a_supported_answer_stays() -> None:
    judge = FakeVisionJudge(see=lambda claim_id, cites: ("ambiguous", [], ""))
    answer = (
        "Arama her adimda yariya iner [S1]. Karmasiklik O(log n) olur [S2]. "
        "Sag yari elenir bu yuzden [S1]. Diyagramda kaynaktan kuyruga ok var [S3]."
    )

    _, result = run(FakeLLM([answer]), judge, visual=VISUAL)

    assert result.outcome == "answered" and "Diyagramda" not in (result.answer or "")


def test_no_frame_on_screen_at_the_paused_moment_is_shown_to_the_generator() -> None:
    frames = {"S3": frame()}
    assert 'ekrandaki_kare="yok"' in format_frames(frames, VideoPosition(30, 500.0))
    assert 'ekrandaki_kare="yok"' in format_frames(frames, VideoPosition(31, 200.0))
    assert VisualContext([frame()], VideoPosition(30, 410.0)).focus_frame() is None
    assert VisualContext([frame()], VideoPosition(30, 190.0)).focus_frame() == frame()


# --- Sağlayıcı istemcileri ---


def test_gemini_sends_images_inline_with_the_text_and_validates_the_schema() -> None:
    class Verdict(BaseModel):
        ok: bool

    models = FakeModels(responses=[response(types.Part(text='{"ok": true}'))])
    client = gemini(models)

    result = client.complete_json_with_images(
        "s", [TextPart("<frame>"), ImagePart(PNG, "image/png"), TextPart("</frame>")], Verdict
    )

    assert result == Verdict(ok=True) and supports_images(client)
    (content,) = models.calls[0]["contents"]
    assert [part.text for part in content.parts] == ["<frame>", None, "</frame>"]
    assert content.parts[1].inline_data.data == PNG
    assert content.parts[1].inline_data.mime_type == "image/png"
    assert models.calls[0]["config"].response_json_schema == Verdict.model_json_schema()


def test_anthropic_and_openai_compatible_image_blocks() -> None:
    encoded = base64.b64encode(PNG).decode("ascii")
    assert hosted._block(ImagePart(PNG, "image/png")) == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": encoded},
    }
    assert hosted._block(TextPart("x")) == {"type": "text", "text": "x"}

    assert _content_part(ImagePart(PNG, "image/png")) == {
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{encoded}"},
    }


def _status_error(status: int, message: str) -> openai.APIStatusError:

    request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    return openai.APIStatusError(
        message, response=httpx.Response(status, request=request), body=None
    )


def test_openai_compatible_endpoint_rejecting_images_is_reported_as_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _rejects_images(_status_error(404, "No endpoints found that support image input"))
    assert not _rejects_images(_status_error(404, "Model not found"))
    assert not _rejects_images(_status_error(500, "image backend down"))

    client = OpenRouterLLMClient(api_key="k", model="text-only", base_url="https://x.invalid")

    def create(**kwargs):
        raise _status_error(404, "No endpoints found that support image input")

    monkeypatch.setattr(client._client.chat.completions, "create", create)

    class Verdict(BaseModel):
        ok: bool

    with pytest.raises(ImageInputUnsupported):
        client.complete_json_with_images("s", [TextPart("x")], Verdict)
    # Görüntüsüz JSON çağrısı aynı hatayı genel LLMError olarak verir (önceki davranış).
    with pytest.raises(LLMError) as error:
        client.complete_json("s", "p", Verdict)
    assert not isinstance(error.value, ImageInputUnsupported)


def test_unconfigured_local_model_takes_no_images() -> None:
    client = LocalLLMClient()

    assert not supports_images(client)
    with pytest.raises(LocalRouteUnavailable):
        client.complete_json_with_images("s", [TextPart("x")], BaseModel)


def test_releasing_client_releases_before_an_image_call_and_keeps_capability() -> None:
    released: list[str] = []
    judge = FakeVisionJudge()
    wrapped = ReleasingClient(judge, lambda: released.append("commit"))

    assert supports_images(wrapped) and not supports_images(ReleasingClient(FakeJudge(), list))
    wrapped.complete_json_with_images(
        "s", [TextPart('<claim id="C1" cites="S3">x</claim>')], VisualJudgeOutput
    )
    assert released == ["commit"] and len(judge.vision_calls) == 1
    with pytest.raises(ImageInputUnsupported):
        ReleasingClient(FakeJudge(), list).complete_json_with_images("s", [], VisualJudgeOutput)


# --- Kare görüntüsü okuma ---


def test_frame_image_is_read_only_from_the_documents_frame_folder(tmp_path: Path) -> None:
    folder = tmp_path / "frames" / "30"
    folder.mkdir(parents=True)
    (folder / "0.png").write_bytes(PNG)
    (folder / "1.png").write_bytes(b"not an image")
    (tmp_path / "outside.png").write_bytes(PNG)

    assert read_frame_image(folder / "0.png", folder) == FrameImage(PNG, "image/png")
    assert read_frame_image(folder / "1.png", folder) is None
    assert read_frame_image(folder / "missing.png", folder) is None
    assert read_frame_image(folder / ".." / ".." / "outside.png", folder) is None


def test_frame_locator_needs_exactly_one_of_frame_or_time() -> None:
    with pytest.raises(ValueError):
        FrameLocator(document_id=1)
    with pytest.raises(ValueError):
        FrameLocator(document_id=1, frame_id=2, time_s=3.0)


# --- #24 kayıtlarından kare kanıtı (veritabanı) ---


def _video(db: Session, course: Course, title: str, approved: bool = True) -> Document:
    document = Document(
        course_id=course.id,
        title=title,
        filename=f"{title}.vtt",
        file_path="",
        material_type="video",
        page_count=0,
        duration_s=600.0,
        status="ready",
        approved_at=datetime.now(UTC) if approved else None,
    )
    db.add(document)
    db.flush()
    return document


def _frame(
    db: Session, document: Document, ordinal: int, t_start: float, t_end: float, image: bool = True
) -> VideoFrame:
    folder = frame_dir(document.course_id, document.id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{ordinal}.png"
    if image:
        path.write_bytes(PNG)
    row = VideoFrame(
        document_id=document.id,
        course_id=document.course_id,
        ordinal=ordinal,
        t_start=t_start,
        t_end=t_end,
        t_frame=t_start,
        image_path=str(path),
        status="readable",
        text=f"slayt {ordinal}",
        confidence=0.9,
        extractor="tesseract/test",
    )
    db.add(row)
    db.flush()
    return row


def test_stored_frames_become_authorized_visual_evidence(api, db: Session, course: Course) -> None:
    video = _video(db, course, "Ders 5")
    first = _frame(db, video, 0, 0.0, 100.0)
    second = _frame(db, video, 1, 100.0, 300.0, image=False)
    other_course = Course(code="X1", name="Baska", language="tr")
    db.add(other_course)
    db.flush()
    foreign = _frame(db, _video(db, other_course, "Yabanci"), 0, 0.0, 50.0)
    unapproved = _frame(db, _video(db, course, "Onaysiz", approved=False), 0, 0.0, 50.0)
    db.commit()
    source = StoredFrameSource(db, course)

    loaded = source.load(
        [
            FrameLocator(video.id, frame_id=first.id),
            FrameLocator(video.id, time_s=150.0),
            FrameLocator(video.id, frame_id=foreign.id),  # başka dokümanın karesi
            FrameLocator(foreign.document_id, frame_id=foreign.id),  # başka ders
            FrameLocator(unapproved.document_id, time_s=10.0),  # onaysız video
            FrameLocator(video.id, time_s=50.0),  # aynı kare tekrar edilmez
        ]
    )

    assert [(e.frame_id, e.source_id) for e in loaded] == [
        (first.id, f"frame:{first.id}"),
        (second.id, f"frame:{second.id}"),
    ]
    assert loaded[0].image == FrameImage(PNG, "image/png") and loaded[1].image is None
    assert (loaded[0].document_id, loaded[0].document_title) == (video.id, "Ders 5")
    assert (loaded[0].derived_text, loaded[0].derived_by) == ("slayt 0", "tesseract/test")

    moment = source.moment(VideoPosition(video.id, 120.0))
    assert [e.frame_id for e in moment.frames] == [first.id, second.id]
    assert moment.focus_frame() is not None and moment.focus_frame().frame_id == second.id
    assert source.moment(VideoPosition(foreign.document_id, 10.0)).frames == []
