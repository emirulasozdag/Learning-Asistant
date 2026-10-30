"""Veri sınıfına göre model rotası: hosted ya da local (ADR-8, FR-08).

Kural tabanlıdır ve sessiz geri düşme yoktur: bir veri sınıfı yerele yönleniyorsa ve yerel model
yapılandırılmamışsa çağrı `LocalRouteUnavailable` ile durur; hosted modele gönderilmez.
"""

from enum import StrEnum
from typing import Literal

from app.core.config import settings
from app.llm.base import LLMError

Route = Literal["hosted", "local"]


class DataClass(StrEnum):
    """Modele giden yükün en hassas parçası."""

    # Soru, getirilen onaylı ders parçaları ve sohbet geçmişi; kimlik yok (ADR-5 A).
    COURSE_EVIDENCE = "course_evidence"
    # Öğrencinin kendi yazdığı cevap (değerlendirme). ADR-5: aydınlatma metninde yazılıysa hosted.
    STUDENT_WORK = "student_work"
    # Ad, e-posta, kullanıcı/oturum kimliği gibi kişisel veri. Hiçbir ayarda hosted'a gitmez.
    PERSONAL = "personal"


class LocalRouteUnavailable(LLMError):
    """Yük yerel modele yönlendi ama yerel model yapılandırılmamış."""


class RoutingConfigError(ValueError):
    """Rota ayarı geçersiz (ör. LLM_STUDENT_WORK_ROUTE için bilinmeyen değer)."""


def route_for(data: DataClass) -> Route:
    if data is DataClass.COURSE_EVIDENCE:
        return "hosted"
    if data is DataClass.PERSONAL:
        return "local"
    value = settings.llm_student_work_route
    if value not in ("hosted", "local"):
        raise RoutingConfigError(
            f"LLM_STUDENT_WORK_ROUTE '{value}' geçersiz; 'hosted' ya da 'local' olmalı."
        )
    return value  # type: ignore[return-value]


def local_configured() -> bool:
    return bool(settings.llm_local_base_url and settings.llm_local_model)
