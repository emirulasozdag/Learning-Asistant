"""Kimlik, üyelik ve onay sözleşmeleri (docs/CONTRACTS.md §3, DECISIONS.md ADR-1, 2, 4).

Yalnızca tip tanımları: bu şemaları kullanan endpoint henüz yok (#11, #12).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Role


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    title: str | None = None
    # Ders açabilir mi (eğitmen hesabı, ADR-1). Arayüz hiç dersi olmayan eğitmeni de eğitmen
    # ana sayfasına bununla yönlendirir (DECISIONS.md açık soru 7).
    can_create_courses: bool = False


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


class DemoAccount(BaseModel):
    """Sunum modunda giriş ekranında gösterilen hesap (DEMO_LOGIN; üretimde kapalı)."""

    role: Literal["instructor", "student"]
    name: str
    email: str
    title: str | None = None


class DemoCourse(BaseModel):
    """Sunum modunda gösterilen ders ve katılım kodu."""

    course_id: int
    code: str
    name: str
    join_code: str


class DemoInfo(BaseModel):
    accounts: list[DemoAccount]
    courses: list[DemoCourse]


class DemoLoginRequest(BaseModel):
    role: Literal["instructor", "student"]
