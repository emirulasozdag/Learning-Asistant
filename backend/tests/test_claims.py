"""İddia kontrolü (#10): iddia birimleri, judge sözleşmesi, cevap akışı, rota, hallucination.

Judge sahte bir istemcidir (anahtar gerekmez); şemaya uyan çıktıyı testin verdiği kararlarla
üretir. Veritabanı gerektiren tek test `TEST_DATABASE_URL` yoksa atlanır.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import select

from app.api import ask as ask_api
from app.core.config import settings
from app.db.models import Course, Message
from app.generation.answer import stream_answer
from app.llm import gateway
from app.llm.base import LLMError
from app.llm.local import LocalLLMClient
from app.llm.routing import DataClass, LocalRouteUnavailable, RoutingConfigError, route_for
from app.qa import service as qa_service
from app.schemas.ask import AskResponse
from app.verification.citations import claim_units, remove_claims, verify_answer
from app.verification.hallucination import hallucination_rate, summarize
from app.verification.judge import (
    AtomicFact,
    ClaimVerdict,
    JudgeContractError,
    JudgeOutput,
    build_prompt,
    label_claims,
)
from tests.test_answer import COURSE, PASSAGES, RELEVANT, FakeLLM

LABELS = {"S1": PASSAGES[0], "S2": PASSAGES[1]}
THREE_CLAIMS = (
    "Dizi sirali oldugu icin sag yari elenir [S1]. "
    "Arama her adimda yariya iner [S1]. "
    "Zaman karmasikligi O(log n) olur [S2]."
)


class FakeJudge:
    """Her iddiaya `decide(claim_id, cites)` kararını veren sahte judge."""

    name = "fake-judge"
    model = "judge-model"

    def __init__(self, decide=None, output: JudgeOutput | None = None, error=None) -> None:
        self.decide = decide or (lambda claim_id, cites: ("supported", cites[:1]))
        self.output = output
        self.error = error
        self.prompts: list[str] = []

    def stream_text(self, system, messages):
        raise NotImplementedError

    def complete_json[T: BaseModel](self, system: str, prompt: str, schema: type[T]) -> T:
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        if self.output is not None:
            return self.output  # type: ignore[return-value]
        verdicts = []
        for line in prompt.splitlines():
            if not line.startswith("<claim "):
                continue
            claim_id = line.split('id="')[1].split('"')[0]
            cites = line.split('cites="')[1].split('"')[0].split(",")
            decision, sources = self.decide(claim_id, cites)
            verdicts.append(
                ClaimVerdict(
                    claim_id=claim_id,
                    atomic_facts=[
                        AtomicFact(fact="bilgi", decision=decision, supporting_sources=sources)
                    ],
                )
            )
        return JudgeOutput(verdicts=verdicts)  # type: ignore[return-value]


def reject(*claim_ids: str):
    return lambda claim_id, cites: (
        ("unsupported", []) if claim_id in claim_ids else ("supported", cites[:1])
    )


def run(llm, judge=None, mode="required", judge_error=None) -> tuple[list[str], AskResponse]:
    items = list(
        stream_answer(
            COURSE,
            "Neden?",
            [],
            RELEVANT,
            llm,
            judge=judge,
            claim_check=mode,
            judge_error=judge_error,
        )
    )
    *deltas, final = items
    assert isinstance(final, AskResponse)
    return deltas, final


# --- İddia birimleri ---


def test_claim_units_group_unlabelled_sentences_with_the_next_cited_one() -> None:
    answer = "Dizi siralidir. Bu yuzden sag yari elenir [S1, S2]. Uydurma bilgi var olabilir [S9]."
    expanded, units = claim_units(answer, LABELS)

    assert [(u.text, u.labels) for u in units] == [
        # "Dizi siralidir." iddia sayılmayacak kadar kısa; birime katılmaz.
        ("Bu yuzden sag yari elenir.", ["S1", "S2"])
    ]
    assert expanded[units[0].span[0] : units[0].span[1]].strip().endswith("[S1][S2].")


def test_removing_a_rejected_claim_keeps_the_rest_intact() -> None:
    expanded, units = claim_units(THREE_CLAIMS, LABELS)
    verification = verify_answer(remove_claims(expanded, [units[1].span]), LABELS)

    assert verification.text == (
        "Dizi sirali oldugu icin sag yari elenir [1]. Zaman karmasikligi O(log n) olur [2]."
    )
    assert verification.supported_claims == 2


def test_removing_a_claim_takes_its_unlabelled_lead_in_and_empty_list_item() -> None:
    answer = "Giris cumlesi burada yer alir. Sag yari elenir [S1].\n- Liste maddesi iddia [S2].\n"
    expanded, units = claim_units(answer, LABELS)

    assert remove_claims(expanded, [units[0].span]) == "- Liste maddesi iddia [S2].\n"
    assert remove_claims(expanded, [units[1].span]).strip() == (
        "Giris cumlesi burada yer alir. Sag yari elenir [S1]."
    )


# --- Judge sözleşmesi ---


def test_judge_sees_only_cited_sources_and_claim_ids() -> None:
    _, units = claim_units("Sag yari elenir [S1].", LABELS)
    prompt = build_prompt(units, LABELS)

    assert '<source label="S1">' in prompt and "S2" not in prompt
    assert '<claim id="C1" cites="S1">Sag yari elenir.</claim>' in prompt


def test_unsupported_fact_or_foreign_source_makes_claim_unsupported() -> None:
    _, units = claim_units(THREE_CLAIMS, LABELS)
    judge = FakeJudge(
        decide=lambda claim_id, cites: {
            "C1": ("supported", ["S1"]),
            "C2": ("unsupported", []),
            # Destek iddianın alıntılamadığı kaynakta gösterildi: kabul edilmez.
            "C3": ("supported", ["S1"]),
        }[claim_id]
    )
    results = label_claims(units, LABELS, judge)

    assert [(r.label, r.reason) for r in results] == [
        ("supported", None),
        ("unsupported", "unsupported_fact"),
        ("unsupported", "source_mismatch"),
    ]
    assert results[0].cited_source_ids == ["11"]
    assert results[0].facts[0]["supporting_source_ids"] == ["11"]
    assert results[0].judge_model == "judge-model"


@pytest.mark.parametrize(
    "verdict_ids",
    [["C1"], ["C1", "C2", "C3", "C4"], ["C1", "C1", "C2"]],
    ids=["missing", "extra", "duplicate"],
)
def test_judge_output_must_cover_each_claim_exactly_once(verdict_ids: list[str]) -> None:
    _, units = claim_units(THREE_CLAIMS, LABELS)
    fact = AtomicFact(fact="x", decision="supported", supporting_sources=["S1"])
    output = JudgeOutput(
        verdicts=[ClaimVerdict(claim_id=cid, atomic_facts=[fact]) for cid in verdict_ids]
    )
    with pytest.raises(JudgeContractError):
        label_claims(units, LABELS, FakeJudge(output=output))


def test_verdict_without_atomic_facts_is_rejected_by_the_schema() -> None:
    with pytest.raises(ValueError):
        ClaimVerdict(claim_id="C1", atomic_facts=[])


# --- Cevap akışı ---


def test_checked_answer_is_shown_without_streaming_an_unchecked_draft() -> None:
    llm = FakeLLM(["Dizi sirali oldugu icin ", "sag yari elenir [S1]."])
    judge = FakeJudge()
    deltas, response = run(llm, judge)

    assert deltas == []
    assert response.outcome == "answered"
    assert response.answer == "Dizi sirali oldugu icin sag yari elenir [1]."
    assert response.claim_check is not None
    assert response.claim_check.status == "checked"
    assert (response.claim_check.claims, response.claim_check.unsupported) == (1, 0)
    assert response.claim_check.records[0]["label"] == "supported"
    assert len(judge.prompts) == 1


def test_claims_rejected_by_the_judge_are_removed_from_the_answer() -> None:
    _, response = run(FakeLLM([THREE_CLAIMS]), FakeJudge(decide=reject("C2")))

    assert response.outcome == "answered"
    assert response.answer is not None and "yariya iner" not in response.answer
    assert response.unsupported_removed == 1
    assert response.claim_check is not None and response.claim_check.unsupported == 1


def test_answer_is_declined_when_too_few_claims_survive_the_judge() -> None:
    _, response = run(FakeLLM([THREE_CLAIMS]), FakeJudge(decide=reject("C1", "C2")))

    assert response.declined and response.answer is None
    assert response.outcome == "unsupported"
    assert response.claim_check is not None and response.claim_check.unsupported == 2


@pytest.mark.parametrize(
    ("judge", "judge_error", "status"),
    [
        (None, None, "not_configured"),
        (None, "Judge generator ile aynı aileden", "failed"),
        (FakeJudge(error=LLMError("judge kapalı")), None, "failed"),
        (FakeJudge(output=JudgeOutput(verdicts=[])), None, "failed"),
    ],
    ids=["no-judge", "bad-config", "provider-error", "contract-error"],
)
def test_unchecked_generated_text_is_never_shown(judge, judge_error, status) -> None:
    llm = FakeLLM(["Uretilen ama kontrol edilemeyen cevap [S1]."])
    deltas, response = run(llm, judge, judge_error=judge_error)

    assert deltas == []
    assert response.outcome == "verification_failure"
    assert response.mode == "extractive"
    # Gösterilen metin kaynağın kendisidir, üretilen cevap değil.
    assert response.answer is not None and "Uretilen" not in response.answer
    assert PASSAGES[0].text in response.answer
    assert response.claim_check is not None and response.claim_check.status == status
    assert response.claim_check.error


def test_judge_is_not_called_when_citation_check_already_rejects() -> None:
    judge = FakeJudge()
    _, response = run(FakeLLM(["Hic kaynagi olmayan uzun bir iddia cumlesi."]), judge)

    assert response.outcome == "unsupported"
    assert judge.prompts == []


def test_claim_check_off_keeps_draft_streaming_and_marks_the_answer() -> None:
    deltas, response = run(FakeLLM(["Sag yari elenir [S1]."]), mode="off")

    assert deltas == ["Sag yari elenir [S1]."]
    assert response.outcome == "answered"
    assert response.claim_check is not None and response.claim_check.status == "off"


def test_audit_records_and_errors_are_not_part_of_the_api_response() -> None:
    _, response = run(FakeLLM(["Sag yari elenir [S1]."]), FakeJudge())
    body = response.model_dump()

    assert set(body["claim_check"]) == {
        "status",
        "judge_model",
        "claims",
        "unsupported",
        "prompt_version",
    }


# --- Judge seçimi ve veri rotası ---


@pytest.mark.parametrize(
    ("provider", "model", "family"),
    [
        ("gemini", "gemini-3.8-flash", "gemini"),
        ("anthropic", "claude-opus-5-5", "claude"),
        ("openrouter", "anthropic/claude-opus-5.5", "claude"),
        ("openrouter", "google/gemini-3.8-flash", "gemini"),
        ("openrouter", "openai/gpt-5.5", "gpt"),
        ("local", "qwen3:8b", "qwen"),
        ("local", "gemma3:12b", "gemini"),
    ],
)
def test_model_family(provider: str, model: str, family: str) -> None:
    assert gateway.model_family(provider, model) == family


def test_judge_from_the_generator_family_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "llm_model", "gemini-3.8-flash")
    monkeypatch.setattr(settings, "judge_provider", "openrouter")
    monkeypatch.setattr(settings, "judge_model", "google/gemini-3.5-flash-lite")
    monkeypatch.setattr(settings, "judge_api_key", "key")

    with pytest.raises(gateway.JudgeConfigError):
        gateway.select_judge_client()
    judge, error = gateway.resolve_judge()
    assert judge is None and error and "aynı model ailesinden" in error


def test_judge_from_another_family_is_built(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "llm_model", "")
    monkeypatch.setattr(settings, "judge_provider", "openrouter")
    monkeypatch.setattr(settings, "judge_model", "anthropic/claude-opus-5.5")
    monkeypatch.setattr(settings, "judge_api_key", "key")

    judge = gateway.select_judge_client()
    assert judge is not None and judge.model == "anthropic/claude-opus-5.5"


def test_missing_judge_key_or_unknown_provider_fails_clearly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "judge_provider", "openrouter")
    monkeypatch.setattr(settings, "judge_model", "anthropic/claude-opus-5.5")
    monkeypatch.setattr(settings, "judge_api_key", "")
    with pytest.raises(gateway.JudgeConfigError, match="JUDGE_API_KEY"):
        gateway.select_judge_client()

    monkeypatch.setattr(settings, "judge_provider", "bilinmeyen")
    with pytest.raises(gateway.JudgeConfigError, match="JUDGE_PROVIDER"):
        gateway.select_judge_client()


def test_data_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    assert route_for(DataClass.COURSE_EVIDENCE) == "hosted"
    assert route_for(DataClass.PERSONAL) == "local"
    monkeypatch.setattr(settings, "llm_student_work_route", "hosted")
    assert route_for(DataClass.STUDENT_WORK) == "hosted"
    monkeypatch.setattr(settings, "llm_student_work_route", "local")
    assert route_for(DataClass.STUDENT_WORK) == "local"
    monkeypatch.setattr(settings, "llm_student_work_route", "bulut")
    with pytest.raises(RoutingConfigError):
        route_for(DataClass.STUDENT_WORK)


def test_local_route_never_falls_back_to_hosted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_api_key", "hosted-key")
    monkeypatch.setattr(settings, "llm_local_base_url", "")
    monkeypatch.setattr(settings, "llm_local_model", "")
    monkeypatch.setattr(settings, "llm_student_work_route", "local")

    for data in (DataClass.PERSONAL, DataClass.STUDENT_WORK):
        client = gateway.select_client(data=data)
        assert isinstance(client, LocalLLMClient) and not client.configured
        with pytest.raises(LocalRouteUnavailable):
            client.complete_json("s", "p", BaseModel)
        with pytest.raises(LocalRouteUnavailable):
            list(client.stream_text("s", []))


def test_configured_local_route_uses_the_local_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_local_base_url", "http://localhost:11434/v1")
    monkeypatch.setattr(settings, "llm_local_model", "qwen3:8b")

    client = gateway.select_client(data=DataClass.PERSONAL)
    assert isinstance(client, LocalLLMClient) and client.configured
    assert client.model == "qwen3:8b"


# --- Hallucination oranı ---


def test_hallucination_summary_counts_checked_answers_only() -> None:
    stats = summarize(
        [
            {"claim_check": {"status": "checked", "claims": 3, "unsupported": 1}},
            {"claim_check": {"status": "checked", "claims": 2, "unsupported": 0}},
            {"claim_check": {"status": "failed", "claims": 0, "unsupported": 0}},
            {"claim_check": {"status": "off"}},
            {"claim_check": None},
            {},
        ]
    )

    assert (stats.checked_answers, stats.answers_with_unsupported) == (2, 1)
    assert stats.answer_rate == pytest.approx(0.5)
    assert stats.claim_rate == pytest.approx(0.2)
    assert stats.unchecked_answers == 1
    assert summarize([]).answer_rate is None


# --- Uçtan uca (veritabanı) ---


def test_claim_check_is_logged_with_the_message(
    client: TestClient,
    db,
    course: Course,
    sample_pdf: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.test_flow import upload

    upload(client, course.id, sample_pdf)
    monkeypatch.setattr(settings, "claim_check", "required")
    monkeypatch.setattr(ask_api, "select_client", lambda: FakeLLM(["Sag yari elenir [S1]."]))
    monkeypatch.setattr(qa_service, "resolve_judge", lambda: (FakeJudge(), None))

    body = client.post(
        "/ask", json={"course_id": course.id, "question": "Neden sag yari elenir?"}
    ).json()

    assert body["outcome"] == "answered"
    assert body["claim_check"]["status"] == "checked"
    assert "records" not in body["claim_check"]
    meta = db.scalars(select(Message.meta).where(Message.role == "assistant")).one()
    record = meta["claim_check"]["records"][0]
    assert record["label"] == "supported"
    assert record["cited_source_ids"] == [body["citations"][0]["source_id"]]
    assert meta["claim_check"]["prompt_version"] == "claim-judge-v1"
    stats = hallucination_rate(db, course.id)
    assert (stats.checked_answers, stats.answer_rate) == (1, 0.0)
