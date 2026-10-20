"""Kimlik, üyelik ve onay sözleşmeleri (docs/CONTRACTS.md §3, DECISIONS.md ADR-1, 2, 4).

Yalnızca tip tanımları: bu şemaları kullanan endpoint henüz yok (#11, #12).
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import Role


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    title: str | None = None


class Membership(BaseModel):
    """Kullanıcının bir dersteki rolü."""

    course_id: int
    role: Role


class Consent(BaseModel):
    """Araştırma/analiz kaydı için ayrı opt-in (varsayılan kapalı)."""

    research_logging: bool
    consented_at: datetime | None = None
    policy_version: str


class ConsentUpdate(BaseModel):
    research_logging: bool
    policy_version: str


class Me(BaseModel):
    """`GET /me`: oturumdaki kullanıcı, ders üyelikleri ve onay durumu."""

    user: UserOut
    memberships: list[Membership] = []
    consent: Consent


class JoinCourseRequest(BaseModel):
    """Katılım kodu ile derse katılma (ADR-2)."""

    code: str = Field(min_length=1, max_length=64)


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1)


class RegisterRequest(BaseModel):
    """Öğrenci kaydı. Rol alanı yoktur: eğitmen/TA rolü kayıtla alınamaz (ADR-1)."""

    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1)
