"""Hesap, onay ve kişisel veri işlemleri (ADR-1, ADR-4)."""

import re
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.passwords import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.core.config import settings
from app.db.models import Conversation, Enrollment, User
from app.schemas.auth import Consent, ConsentUpdate, Me, Membership, RegisterRequest, UserOut

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class InvalidInput(ValueError):
    """Kullanıcıya gösterilecek doğrulama hatası."""


class EmailExists(ValueError):
    pass


def normalize_email(email: str) -> str:
    return email.strip().lower()


def register(db: Session, data: RegisterRequest) -> User:
    """Öğrenci hesabı açar. Rol verilmez: üyelik derse katılım koduyla gelir (ADR-1, ADR-2)."""
    email = normalize_email(data.email)
    name = data.name.strip()
    if not _EMAIL.match(email):
        raise InvalidInput("Geçerli bir e-posta adresi girin.")
    if not name:
        raise InvalidInput("Ad boş olamaz.")
    if not MIN_PASSWORD_LENGTH <= len(data.password) <= MAX_PASSWORD_LENGTH:
        raise InvalidInput(
            f"Şifre {MIN_PASSWORD_LENGTH}–{MAX_PASSWORD_LENGTH} karakter uzunluğunda olmalı."
        )
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise EmailExists(email)
    user = User(name=name, email=email, password_hash=hash_password(data.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:  # Aynı e-postayla eşzamanlı kayıt.
        db.rollback()
        raise EmailExists(email) from exc
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if not verify_password(user.password_hash if user else None, password) or user is None:
        return None
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        db.commit()
    return user


def me(db: Session, user: User) -> Me:
    rows = db.execute(
        select(Enrollment.course_id, Enrollment.role)
        .where(Enrollment.user_id == user.id)
        .order_by(Enrollment.course_id)
    ).all()
    return Me(
        user=UserOut(
            id=user.id,
            name=user.name,
            email=user.email,
            title=user.title,
            can_create_courses=user.can_create_courses,
        ),
        memberships=[Membership(course_id=course_id, role=role) for course_id, role in rows],
        consent=consent(user),
    )


def consent(user: User) -> Consent:
    """`consented_at` boşsa aydınlatma metni henüz kabul edilmemiştir (`policy_version` boş)."""
    return Consent(
        research_logging=user.research_logging,
        consented_at=user.consented_at,
        policy_version=user.policy_version or "",
    )


def update_consent(db: Session, user: User, data: ConsentUpdate) -> Consent:
    """Aydınlatma metninin güncel sürümünü kabul eder ve araştırma kaydı tercihini yazar.

    Araştırma kaydı kapatılınca eğitmen analitiği bu kullanıcının verisini artık kullanmaz
    (analitik her istekte yeniden hesaplanır).
    """
    if data.policy_version != settings.privacy_policy_version:
        raise InvalidInput(
            f"Aydınlatma metninin güncel sürümü {settings.privacy_policy_version}; "
            "sayfayı yenileyip yeniden onaylayın."
        )
    user.policy_version = data.policy_version
    user.consented_at = datetime.now(UTC)
    user.research_logging = data.research_logging
    db.commit()
    return consent(user)


def delete_my_data(db: Session, user: User) -> None:
    """Verilerimi sil (ADR-4): kullanıcının bütün sohbetleri ve mesajları silinir."""
    db.execute(delete(Conversation).where(Conversation.user_id == user.id))
    db.commit()


def delete_account(db: Session, user: User) -> None:
    """Hesabı siler: oturumlar, üyelikler, sohbetler ve mesajlar birlikte gider (CASCADE).

    Kullanıcının onayladığı dokümanlar dersin malıdır, kalır; `approved_by` boşalır.
    """
    db.delete(user)
    db.commit()
