from typing import Literal

from pydantic import BaseModel

# Kullanıcının bir dersteki rolü. Rol ders başınadır: bir kişi bir derste eğitmen,
# başka bir derste öğrenci olabilir.
Role = Literal["student", "instructor", "ta"]

# Uygulama hatalarının makine tarafından okunan kodu (docs/CONTRACTS.md §5).
ErrorCode = Literal[
    "course_not_found",
    "source_not_found",
    "conversation_not_found",
    "document_not_found",
    "unsupported_file_type",
    "file_too_large",
    "ingestion_failed",
    "course_exists",
    "no_valid_item",
    # Pratik sorusu yok, kontrolden geçmemiş ya da kullanıcı dersin üyesi değil.
    "practice_item_not_found",
    "invalid_video",
    "not_authenticated",
    "insufficient_role",
    # #11: aydınlatma metninin güncel sürümü kabul edilmeden soru sorulamaz (ADR-4).
    "consent_required",
    # #11: bu e-postayla bir hesap zaten var.
    "email_exists",
    "not_implemented",
    "validation_error",
]


class ApiErrorBody(BaseModel):
    """Hata zarfı: `detail` kullanıcıya gösterilebilir metin, `code` programın kullandığı sabit."""

    detail: str
    code: ErrorCode


class Citation(BaseModel):
    """Bir cevabın dayandığı kaynak parçası: sayfa ve/veya video zamanı (sunum slayt 4)."""

    source_id: str
    document_title: str | None = None
    page: int | None = None
    t_start: float | None = None
    t_end: float | None = None
