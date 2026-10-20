"""Etiket/judge testleri için küçük koşu kaydı ve etiket üreticileri."""

from datetime import UTC, datetime

from harness.claims import claim_sha256, split_claims
from harness.labels import AnswerLabel, ClaimLabel, LabelSet, LabelSource
from harness.schemas import (
    CorpusDocument,
    CorpusSnapshot,
    GoldItem,
    GoldSet,
    ItemKind,
    ItemResult,
    RunConfig,
    RunRecord,
    SourceLocator,
    Split,
)

SHA = "a" * 64
NOW = datetime(2026, 11, 3, 10, 0, tzinfo=UTC)
ANSWER = "İkili arama sıralı dizide çalışır [1]. Her adımda arama aralığı yarıya iner [1]."


def result(id, kind=ItemKind.ANSWERABLE, answer=ANSWER, declined=False, **kw):
    data = {
        "id": id,
        "split": Split.CALIBRATION,
        "kind": kind,
        "outcome": "insufficient_evidence" if declined else "answered",
        "declined": declined,
        "mode": "llm",
        "model": "anthropic/claude-opus-5.5",
        "answer": None if declined else answer,
        "retrieved": [SourceLocator(document_sha256=SHA, page=2)],
        "retrieved_text": ["İkili arama sıralı dizide ortadaki elemana bakar."],
    }
    return ItemResult(**{**data, **kw})


def record(items, split=Split.CALIBRATION, run_id="run-1"):
    return RunRecord(
        run_id=run_id,
        started_at=NOW,
        config=RunConfig(
            condition="full",
            split=split,
            git_commit="c" * 40,
            git_dirty=False,
            gold_set_sha256="g" * 64,
            manifest_sha256="m" * 64,
            llm_provider="openrouter",
            llm_model="anthropic/claude-opus-5.5",
            llm_base_url="https://openrouter.ai/api/v1",
            llm_enabled=True,
            prompt_sha256="p" * 64,
            embedding_provider="fake",
            embedding_model="fake",
            retrieval={"k": 5},
        ),
        corpus=CorpusSnapshot(
            course_code="BLM2512",
            documents=[
                CorpusDocument(sha256=SHA, title="Ders 3", material_type="notes", chunk_count=4)
            ],
        ),
        items=items,
    )


def gold_set(ids, reference="Dizi sıralı olmalı; aralık her adımda yarıya iner."):
    return GoldSet(
        course_code="BLM2512",
        manifest="manifest.json",
        items=[
            GoldItem(
                id=id,
                split="calibration",
                kind="answerable",
                question=f"Soru {id}?",
                reference_answer=reference,
                evidence=[SourceLocator(document_sha256=SHA, page=2)],
                origin="instructor",
            )
            for id in ids
        ],
    )


def labels(
    run,
    scores,
    claims=None,
    rater="rater-a",
    source=LabelSource.HUMAN,
    model=None,
    answer=ANSWER,
):
    """scores: {item_id: puan}; claims: {item_id: [etiket, ...]} (varsayılan: hepsi supported)."""
    claims = claims or {}
    texts = split_claims(answer)
    judge = source is LabelSource.JUDGE
    return LabelSet(
        run_id=run.run_id,
        source=source,
        rater=rater,
        judge_model=(model or "openai/gpt-6.1") if judge else None,
        judge_prompt_sha256=("e" * 64) if judge else None,
        labeled_at=NOW,
        items=[
            AnswerLabel(
                item_id=item_id,
                score=score,
                claims=[
                    ClaimLabel(index=i, claim_sha256=claim_sha256(text), label=label)
                    for i, (text, label) in enumerate(
                        zip(texts, claims.get(item_id, ["supported"] * len(texts)), strict=True)
                    )
                ],
            )
            for item_id, score in scores.items()
        ],
    )
