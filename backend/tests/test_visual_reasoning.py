"""Görsel akıl yürütme ve belirsizlik (#30): mekânsal/zamansal çıkarım, kaynak çelişkisi,
karışık destek ve köken kaydı.

Üretici ve judge sahte istemcilerdir (`test_visual_grounding`); anahtar ve veritabanı gerekmez.
Gerçek kareler ve eğitmen etiketleriyle ölçüm `evaluation/` altındaki görsel koşulla yapılır.
"""

from app.generation.answer import (
    CLARIFY,
    CONFLICT,
    CONFLICT_NOTE,
    FRAME_INSUFFICIENT,
    VISUAL_RULES,
    VISUAL_RULES_VERSION,
)
from app.generation.visual import VisualContext
from app.qa.service import answer_meta
from app.retrieval.types import VideoPosition
from app.verification.visual import (
    SYSTEM_PROMPT,
    VISUAL_JUDGE_PROMPT_VERSION,
    VisualFact,
)
from tests.test_answer import FakeLLM
from tests.test_claims import FakeJudge
from tests.test_visual_grounding import VISUAL, FakeVisionJudge, frame, run

# S1, S2 metin parçaları; S3 ve S4 aynı videonun ardışık iki karesi.
TWO_FRAMES = VisualContext(
    frames=[frame(7), frame(8, t_start=410.0, t_end=600.0, t_frame=412.0)],
    focus=VideoPosition(30, 420.0),
)
TEXT_CLAIMS = (
    "Arama her adimda yariya iner [S1]. Karmasiklik O(log n) olur [S2]. "
    "Sag yari elenir bu yuzden [S1]."
)
ORDER_CLAIM = "Hoca once kaynak dugumu yazdi, sonra kuyrugu sildi [S3]."


def reasons(response) -> list[str | None]:
    return [record["reason"] for record in response.claim_check.records]


# --- Zamansal çıkarım: tek durağan kare "önce/sonra"yı göstermez ---


def test_order_of_events_from_a_single_frame_is_not_supported() -> None:
    judge = FakeVisionJudge(
        see=lambda claim_id, cites: ("supported", cites, "karede yazi var", "temporal")
    )

    _, result = run(FakeLLM([ORDER_CLAIM]), judge, visual=VISUAL)

    assert result.declined and result.answer is None
    assert result.outcome == "insufficient_evidence"
    assert result.decline_reason == FRAME_INSUFFICIENT
    assert result.visual_gap == "frame_insufficient"
    assert reasons(result) == ["temporal_inference"]
    assert result.claim_check.records[0]["label"] == "unsupported"  # type: ignore[union-attr]
    assert result.claim_check.records[0]["facts"][0]["kind"] == "temporal"  # type: ignore[union-attr]


def test_order_stated_in_the_transcript_is_supported_and_the_frame_citation_dropped() -> None:
    # Sıra konuşmada (S1) söyleniyor; kare yalnızca alıntılandı, sırayı göstermiyor.
    answer = "Hoca once kaynak dugumu yazdi, sonra kuyrugu sildi [S1][S3]. " + TEXT_CLAIMS
    judge = FakeVisionJudge(see=lambda claim_id, cites: ("supported", ["S1"], "", "temporal"))

    _, result = run(FakeLLM([answer]), judge, visual=VISUAL)

    assert result.outcome == "answered" and result.visual_gap is None
    assert result.answer is not None and result.answer.startswith("Hoca once kaynak dugumu")
    assert "frame:7" not in [c.source_id for c in result.citations]
    assert result.claim_check.records[0]["dropped_frame_citations"] == ["frame:7"]  # type: ignore[union-attr]


def test_order_shown_by_two_frame_images_is_supported() -> None:
    answer = "Hoca once kaynak dugumu yazdi, sonra kuyrugu sildi [S3][S4]. " + TEXT_CLAIMS
    judge = FakeVisionJudge(
        see=lambda claim_id, cites: (
            ("supported", cites, "ilk karede kuyruk var, ikincide yok", "temporal")
            if len(cites) == 2
            else ("supported", cites[-1:], "")
        )
    )

    _, result = run(FakeLLM([answer]), judge, visual=TWO_FRAMES)

    assert result.outcome == "answered"
    assert [c.source_id for c in result.citations][:2] == ["frame:7", "frame:8"]
    assert reasons(result)[0] is None


# --- Mekânsal çıkarım: görüntüde görülen öğe yazılmalı ---


def test_arrow_direction_without_a_visible_observation_is_not_accepted() -> None:
    answer = "Ok kaynak dugumden kuyruga gidiyor [S3]."
    judge = FakeVisionJudge(see=lambda claim_id, cites: ("supported", cites, "", "spatial"))

    _, result = run(FakeLLM([answer]), judge, visual=VISUAL)

    assert result.outcome == "insufficient_evidence"
    assert result.visual_gap == "frame_insufficient"
    assert reasons(result) == ["no_visual_observation"]


def test_arrow_direction_seen_in_the_image_is_kept() -> None:
    answer = "Ok kaynak dugumden kuyruga gidiyor [S3]. " + TEXT_CLAIMS
    judge = FakeVisionJudge(
        see=lambda claim_id, cites: ("supported", cites, "soldaki kutudan sagdakine ok", "spatial")
    )

    _, result = run(FakeLLM([answer]), judge, visual=VISUAL)

    assert result.outcome == "answered" and result.visual_gap is None
    assert "frame:7" in [c.source_id for c in result.citations]


# --- Kaynak çelişkisi: bir kaynak sessizce seçilmez ---


def test_conflict_between_frame_and_transcript_is_removed_and_reported() -> None:
    answer = "Diyagramda kuyruktan kaynaga ok var [S1][S3]. " + TEXT_CLAIMS
    judge = FakeVisionJudge(see=lambda claim_id, cites: ("contradicted", [], "", "spatial"))

    _, result = run(FakeLLM([answer]), judge, visual=VISUAL)

    assert result.outcome == "answered"
    assert result.answer is not None and "kuyruktan kaynaga" not in result.answer
    assert result.coverage_gap == CONFLICT_NOTE
    assert result.visual_gap == "source_conflict"
    assert reasons(result)[0] == "source_conflict"
    assert result.visual is not None and result.visual.gap == "source_conflict"


def test_conflict_alone_asks_instead_of_choosing_a_source() -> None:
    answer = "Diyagramda kuyruktan kaynaga ok var [S1][S3]. Kuyruk en sagda duruyor [S3]."

    def see(claim_id: str, cites: list[str]) -> tuple:
        return ("contradicted", [], "") if claim_id == "C1" else ("ambiguous", [], "")

    _, result = run(FakeLLM([answer]), FakeVisionJudge(see=see), visual=VISUAL)

    # Çelişki belirsizlikten önce gelir: öğrenciye çelişki söylenir.
    assert result.outcome == "needs_clarification"
    assert result.decline_reason == CONFLICT and result.visual_gap == "source_conflict"


def test_ambiguity_still_asks_which_part_is_meant() -> None:
    judge = FakeVisionJudge(see=lambda claim_id, cites: ("ambiguous", [], ""))

    _, result = run(FakeLLM(["Diyagramda kaynaktan kuyruga ok var [S3]."]), judge, visual=VISUAL)

    assert result.decline_reason == CLARIFY and result.visual_gap == "scene_ambiguous"


def test_generator_clarification_is_marked_as_scene_ambiguity() -> None:
    _, result = run(FakeLLM(["NETLEŞTİR: hangi ok?"]), FakeVisionJudge(), visual=VISUAL)

    assert result.outcome == "needs_clarification" and result.visual_gap == "scene_ambiguous"


# --- Köken ve yalnızca metin regresyonu ---


def test_generator_and_checker_provenance_is_recorded() -> None:
    answer = "Diyagramda kaynak dugumden kuyruga ok var [S3]. " + TEXT_CLAIMS

    _, result = run(FakeLLM([answer]), FakeVisionJudge(), visual=VISUAL)
    meta = answer_meta(result)

    assert meta["visual"]["rules_version"] == VISUAL_RULES_VERSION
    assert meta["visual"]["frames"][0]["status"] == "readable"
    assert meta["visual"]["frames"][0]["confidence"] == 0.93
    assert VISUAL_JUDGE_PROMPT_VERSION in meta["claim_check"]["prompt_version"]
    assert meta["claim_check"]["judge_model"] == "judge-model"
    assert meta["model"] == "fake-model"
    assert "visual_gap" not in meta
    # Görüntü ve OCR metni kayda girmez (ADR-12).
    assert "GIZLI-OCR-METNI" not in str(meta)


def test_visual_gap_is_written_to_the_message_record() -> None:
    judge = FakeVisionJudge(see=lambda claim_id, cites: ("supported", cites, "x", "temporal"))

    _, result = run(FakeLLM([ORDER_CLAIM]), judge, visual=VISUAL)

    assert answer_meta(result)["visual_gap"] == "frame_insufficient"


def test_text_only_answer_has_no_visual_gap_or_trace() -> None:
    _, result = run(FakeLLM([TEXT_CLAIMS]), FakeJudge())

    assert result.outcome == "answered"
    assert result.visual_gap is None and result.visual is None
    assert "visual" not in answer_meta(result) and "visual_gap" not in answer_meta(result)


def test_prompts_state_the_spatial_and_temporal_rules() -> None:
    assert VISUAL_JUDGE_PROMPT_VERSION == "visual-claim-judge-v2"
    assert "time attribute of a frame only identifies it" in SYSTEM_PROMPT
    assert '"contradicted"' in SYSTEM_PROMPT
    assert "tek bir kareden çıkarma" in VISUAL_RULES


def test_verdicts_without_a_kind_default_to_content() -> None:
    fact = VisualFact(fact="bilgi", decision="supported", supporting_sources=["S3"], observed="x")

    assert fact.kind == "content"
