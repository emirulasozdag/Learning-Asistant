"""Değerlendirme girdi/çıktı şemaları: kaynak konumu, gold set, materyal envanteri, koşu kaydı.

Gold set ve envanter JSON dosyalarıdır; bu modeller onların tek tanımıdır (`harness.validate`
aynı modellerle doğrular). Ders içeriği (pasaj metni) bu dosyalara yazılmaz: kanıt, dokümanın
içerik parmak izi ve sayfa / video zamanıyla gösterilir.
"""

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

SCHEMA_VERSION = 1

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Kaynak konumu -----------------------------------------------------------------------------


class SourceLocator(_Strict):
    """Yeniden indekslemede değişmeyen kanıt konumu.

    Chunk id'leri her yüklemede değişir; doküman, dosya içeriğinin SHA-256'sıyla tanınır.
    `page` (PDF/PPTX) ya da `t_start`/`t_end` (video, saniye) verilir; ikisi de yoksa
    dokümanın tamamı kanıt sayılır.
    """

    document_sha256: Sha256
    page: int | None = Field(default=None, ge=1)
    t_start: float | None = Field(default=None, ge=0)
    t_end: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _check_interval(self) -> Self:
        if (self.t_start is None) != (self.t_end is None):
            raise ValueError("t_start ve t_end birlikte verilmeli")
        if self.t_start is not None and self.t_end is not None and self.t_end < self.t_start:
            raise ValueError("t_end, t_start'tan küçük olamaz")
        if self.page is not None and self.t_start is not None:
            raise ValueError("Konum ya sayfa ya video zamanı olmalı, ikisi birden değil")
        return self

    def matches(self, other: "SourceLocator") -> bool:
        """`other` (sistemin getirdiği parça) bu gold kanıtına düşüyor mu?"""
        if self.document_sha256 != other.document_sha256:
            return False
        if self.page is not None:
            return other.page == self.page
        if self.t_start is not None and self.t_end is not None:
            if other.t_start is None or other.t_end is None:
                return False
            return other.t_start <= self.t_end and self.t_start <= other.t_end
        return True


# --- Gold set ----------------------------------------------------------------------------------


class Split(StrEnum):
    """Kalibrasyon örnekleri eşik/prompt ayarında kullanılır; held-out yalnızca ölçümde."""

    CALIBRATION = "calibration"
    HELDOUT = "heldout"


class ItemKind(StrEnum):
    ANSWERABLE = "answerable"
    OUT_OF_SCOPE = "out_of_scope"


class Review(_Strict):
    """Eğitmen incelemesi. Kişisel veri yerine rol/takma ad yazılır (ör. "instructor-1")."""

    reviewer: str = Field(min_length=1, max_length=64)
    reviewed_at: datetime


class GoldItem(_Strict):
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    split: Split
    kind: ItemKind
    question: str = Field(min_length=3, max_length=2000)
    topic: str | None = Field(default=None, max_length=200)
    # Cevaplanabilir sorularda eğitmenin referans cevabı (judge ve insan değerlendirmesi için).
    reference_answer: str | None = Field(default=None, max_length=8000)
    evidence: list[SourceLocator] = []
    # Örneğin nereden geldiği: eğitmen yazdı, geçmiş sınavdan uyarlandı, ekip taslağı...
    origin: Literal["instructor", "past_exam", "team_draft"]
    review: Review | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _check_kind(self) -> Self:
        if self.kind is ItemKind.OUT_OF_SCOPE:
            if self.evidence or self.reference_answer:
                raise ValueError(f"{self.id}: kapsam dışı soruda kanıt/referans cevap olmaz")
        return self

    @property
    def reviewed(self) -> bool:
        return self.review is not None


class GoldSet(_Strict):
    schema_version: Literal[1] = SCHEMA_VERSION
    course_code: str = Field(min_length=2, max_length=32)
    # Gold set'in dayandığı envanter (aynı klasördeki manifest dosyasının adı).
    manifest: str
    items: list[GoldItem]

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        seen: set[str] = set()
        for item in self.items:
            if item.id in seen:
                raise ValueError(f"Tekrarlanan soru id'si: {item.id}")
            seen.add(item.id)
        return self


# --- Materyal envanteri ------------------------------------------------------------------------


class ManifestStatus(StrEnum):
    # Eğitmen bu derste kullanılmasını onayladı.
    APPROVED = "approved"
    # Bilerek dışarıda: aktif/yayınlanmamış sınav, telif, eğitmen istemedi...
    EXCLUDED = "excluded"


class ManifestDocument(_Strict):
    """Envanterdeki bir doküman. Dosyanın kendisi repoya girmez; yalnızca parmak izi."""

    sha256: Sha256
    title: str = Field(min_length=1, max_length=300)
    material_type: str = Field(min_length=1, max_length=32)
    status: ManifestStatus
    # Kullanım izninin kaydı (ör. "eğitmen e-postası 2026-10-25"); gerekçe zorunlu.
    permission: str | None = Field(default=None, max_length=500)
    exclusion_reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _check_status(self) -> Self:
        if self.status is ManifestStatus.APPROVED and not self.permission:
            raise ValueError(f"{self.title}: onaylı dokümanın izin kaydı yok")
        if self.status is ManifestStatus.EXCLUDED and not self.exclusion_reason:
            raise ValueError(f"{self.title}: dışlanan dokümanın gerekçesi yok")
        return self


class MissingInput(_Strict):
    """Henüz elde olmayan dış girdi; uydurma değer yerine açıkça kaydedilir."""

    what: str = Field(min_length=3, max_length=300)
    owner: str = Field(min_length=1, max_length=100)
    blocking: list[str] = []


class CorpusManifest(_Strict):
    schema_version: Literal[1] = SCHEMA_VERSION
    course_code: str = Field(min_length=2, max_length=32)
    approved_by: Review | None = None
    documents: list[ManifestDocument]
    missing_inputs: list[MissingInput] = []

    @model_validator(mode="after")
    def _unique_documents(self) -> Self:
        hashes = [document.sha256 for document in self.documents]
        if len(hashes) != len(set(hashes)):
            raise ValueError("Envanterde aynı dosya iki kez var")
        return self

    def approved_hashes(self) -> set[str]:
        return {d.sha256 for d in self.documents if d.status is ManifestStatus.APPROVED}

    def excluded_hashes(self) -> set[str]:
        return {d.sha256 for d in self.documents if d.status is ManifestStatus.EXCLUDED}


# --- Koşu kaydı --------------------------------------------------------------------------------


class CorpusDocument(_Strict):
    """Koşu anında veritabanında indeksli olan doküman."""

    sha256: str | None
    title: str
    material_type: str
    chunk_count: int
    # Dosya diskte yoksa parmak izi hesaplanamaz.
    file_missing: bool = False


class CorpusSnapshot(_Strict):
    course_code: str
    documents: list[CorpusDocument]
    # Envanterde onaylı olup indekste olmayan dokümanlar (sha256).
    approved_not_indexed: list[str] = []
    # İndekste olup envanterde onaylı olmayan dokümanlar (başlık); varsa koşu reddedilir.
    unapproved_indexed: list[str] = []


class RunConfig(_Strict):
    condition: str
    split: Split | None
    git_commit: str | None
    git_dirty: bool | None
    gold_set_sha256: str
    manifest_sha256: str
    llm_provider: str
    llm_model: str | None
    llm_base_url: str | None
    llm_enabled: bool
    prompt_sha256: str
    embedding_provider: str
    embedding_model: str
    retrieval: dict[str, float | int]


class ItemResult(_Strict):
    id: str
    split: Split
    kind: ItemKind
    outcome: str | None
    declined: bool | None
    mode: str | None
    model: str | None
    answer: str | None
    cited: list[SourceLocator] = []
    # Getirilen parçalar, sıra korunarak (1. eleman en iyi).
    retrieved: list[SourceLocator] = []
    best_similarity: float | None = None
    latency_ms: float | None = None
    error: str | None = None


class MetricValue(_Strict):
    value: float | None
    numerator: int | None = None
    denominator: int
    target: str | None = None
    # Hesaplanamadıysa neden (ör. "judge kalibre değil, #13").
    gap: str | None = None


class RunRecord(_Strict):
    schema_version: Literal[1] = SCHEMA_VERSION
    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    config: RunConfig
    corpus: CorpusSnapshot
    items: list[ItemResult] = []
    metrics: dict[str, MetricValue] = {}
    gaps: list[str] = []


def load_gold_set(path: Path) -> GoldSet:
    return GoldSet.model_validate_json(path.read_text(encoding="utf-8"))


def load_manifest(path: Path) -> CorpusManifest:
    return CorpusManifest.model_validate_json(path.read_text(encoding="utf-8"))
