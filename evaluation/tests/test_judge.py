import pytest
from factories import NOW, gold_set, record, result

from app.llm.base import LLMError
from harness import judge
from harness.judge import (
    PROMPT_SHA256,
    ClaimOutput,
    JudgeError,
    ScoreOutput,
    check_independent,
    judge_run,
    model_families,
)
from harness.labels import LabelSource


class FakeJudge:
    """Sahte judge: istenen sabit puan/etiketi döndürür, çağrıları kaydeder."""

    def __init__(self, model="openai/gpt-6.1", score=2, label="supported", fail_on=None):
        self.model = model
        self.score = score
        self.label = label
        self.fail_on = fail_on
        self.prompts: list[tuple[str, str]] = []

    def complete_json(self, system, prompt, schema):
        self.prompts.append((system, prompt))
        if self.fail_on and self.fail_on in prompt:
            raise LLMError("kota")
        if schema is ScoreOutput:
            return ScoreOutput(reason="r", score=self.score)
        count = prompt.split("<iddialar>\n", 1)[1].count("\n")
        return ClaimOutput(
            claims=[{"index": i, "reason": "r", "label": self.label} for i in range(count)]
        )


@pytest.mark.parametrize(
    ("model", "families"),
    [
        ("anthropic/claude-opus-5.5", {"anthropic"}),
        ("claude-haiku-5-5", {"anthropic"}),
        ("openai/gpt-6.1", {"openai"}),
        ("openai/o3-mini", {"openai"}),
        ("google/gemini-3.8-flash", {"google"}),
        ("meta-llama/llama-4-70b", {"meta"}),
        ("nvidia/llama-3.1-nemotron", {"meta"}),
        ("llama3.1:8b", {"meta"}),
        ("qwen/qwen3-32b", {"qwen"}),
        ("deepseek/deepseek-r1-distill-llama-70b", {"deepseek", "meta"}),
        ("openrouter/auto", set()),
    ],
)
def test_model_families(model, families):
    assert model_families(model) == families


def test_same_family_judge_is_rejected():
    with pytest.raises(JudgeError, match="aynı aileden"):
        check_independent("anthropic/claude-haiku-5.5", {"anthropic/claude-opus-5.5"})
    with pytest.raises(JudgeError, match="tanınmadı"):
        check_independent("openrouter/auto", set())
    # Damıtılmış model tabanını paylaşır: Llama generator'a DeepSeek-distill-Llama judge olmaz.
    with pytest.raises(JudgeError, match="meta"):
        check_independent("deepseek/deepseek-r1-distill-llama-70b", {"meta-llama/llama-3.3-70b"})
    check_independent("openai/gpt-6.1", {"anthropic/claude-opus-5.5"})
    # LLM'siz koşu (generator yok): aile çatışması yok.
    check_independent("openai/gpt-6.1", set())


def test_judge_run_scores_and_labels_answered_items():
    run = record([result("q1"), result("q2", declined=True)])
    client = FakeJudge(score=1, label="unsupported")

    labels, gaps = judge_run(run, gold_set(["q1", "q2"]), client, now=lambda: NOW)

    assert labels.source is LabelSource.JUDGE
    assert labels.judge_model == "openai/gpt-6.1"
    assert labels.judge_prompt_sha256 == PROMPT_SHA256
    (item,) = labels.items  # reddedilen soru judge'a gitmez
    assert item.score == 1
    assert [c.label for c in item.claims] == ["unsupported", "unsupported"]
    assert gaps == []
    # Judge pasajları ve referansı gördü; prompt'ta kimlik yok.
    joined = "\n".join(prompt for _, prompt in client.prompts)
    assert "Ders 3 s.2" in joined and "aralık her adımda" in joined


def test_judge_failure_leaves_item_unlabeled_with_gap():
    run = record([result("q1"), result("q2")])
    labels, gaps = judge_run(run, gold_set(["q1", "q2"]), FakeJudge(fail_on="Soru q2"))
    assert [item.item_id for item in labels.items] == ["q1"]
    assert any("q2" in gap and "etiketlenmedi" in gap for gap in gaps)


def test_judge_missing_claim_is_an_error_not_a_guess():
    class Short(FakeJudge):
        def complete_json(self, system, prompt, schema):
            if schema is ClaimOutput:
                return ClaimOutput(claims=[{"index": 0, "reason": "r", "label": "supported"}])
            return super().complete_json(system, prompt, schema)

    labels, gaps = judge_run(record([result("q1")]), gold_set(["q1"]), Short())
    assert labels.items == []
    assert any("eksik ya da fazla" in gap for gap in gaps)


@pytest.mark.parametrize("texts", [[], [""], ["a", "b"]])
def test_judge_without_complete_passage_text_does_not_label_claims(texts):
    run = record([result("q1", retrieved_text=texts)])
    labels, gaps = judge_run(run, gold_set(["q1"]), FakeJudge())
    assert labels.items[0].score == 2 and labels.items[0].claims == []
    assert any("pasaj metni" in gap for gap in gaps)


def test_judge_rejects_same_family_as_generator():
    with pytest.raises(JudgeError):
        judge_run(record([result("q1")]), gold_set(["q1"]), FakeJudge("anthropic/claude-x"))


def test_client_from_env_without_key_raises(monkeypatch):
    from app.core.config import settings

    monkeypatch.setenv("EVAL_JUDGE_MODEL", "openai/gpt-6.1")
    monkeypatch.delenv("EVAL_JUDGE_API_KEY", raising=False)
    monkeypatch.setattr(settings, "llm_api_key", "")
    with pytest.raises(JudgeError, match="anahtar"):
        judge.client_from_env()
    monkeypatch.delenv("EVAL_JUDGE_MODEL")
    with pytest.raises(JudgeError, match="EVAL_JUDGE_MODEL"):
        judge.client_from_env()


def test_cli_without_judge_writes_nothing(tmp_path, monkeypatch, capsys):
    run = record([result("q1")])
    gold_path = tmp_path / "gold.json"
    gold_path.write_text(gold_set(["q1"]).model_dump_json(), encoding="utf-8")
    from harness.fingerprint import file_sha256

    run.config.gold_set_sha256 = file_sha256(gold_path)
    run_path = tmp_path / "run.json"
    run_path.write_text(run.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(
        judge, "client_from_env", lambda: (_ for _ in ()).throw(JudgeError("anahtar yok"))
    )

    assert judge.main(["--run", str(run_path), "--gold", str(gold_path)]) == 2
    assert not (tmp_path / "run.judge.json").exists()
    assert "anahtar yok" in capsys.readouterr().err
