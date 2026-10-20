"""İstekteki kullanıcı ve ders düzeyinde yetki (ADR-1, ADR-2, CONTRACTS.md §3).

Kimlik yalnızca oturum çerezinden çözülür; istek gövdesinde ya da sorguda gelmez. Roller her
istekte `enrollments` tablosundan okunur: üyelik silinince erişim hemen biter.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.auth.sessions import user_for_token
from app.core.config import settings
from app.db.models import Enrollment, User
from app.db.session import get_db
from app.schemas.common import ErrorCode, Role

_NOT_FOUND_DETAIL: dict[ErrorCode, str] = {
    "course_not_found": "Ders bulunamadı",
    "document_not_found": "Doküman bulunamadı",
    "source_not_found": "Kaynak bulunamadı",
    "conversation_not_found": "Sohbet bulunamadı",
    "practice_item_not_found": "Pratik sorusu bulunamadı",
}


@dataclass
class CurrentUser:
    id: int
    roles: dict[int, Role]  # course_id → rol
    user: User

    @property
    def consented(self) -> bool:
        """Aydınlatma metninin güncel sürümünü kabul etti mi (ADR-4)."""
        return (
            self.user.consented_at is not None
            and self.user.policy_version == settings.privacy_policy_version
        )


def get_current_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> CurrentUser:
    """Oturum çerezinden kullanıcıyı çözer; oturum yoksa ya da süresi dolduysa 401."""
    user = user_for_token(db, request.cookies.get(settings.session_cookie_name))
    if user is None:
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED, "Oturum açmanız gerekiyor", "not_authenticated"
        )
    rows = db.execute(
        select(Enrollment.course_id, Enrollment.role).where(Enrollment.user_id == user.id)
    ).all()
    return CurrentUser(id=user.id, roles={course_id: role for course_id, role in rows}, user=user)


AuthUser = Annotated[CurrentUser, Depends(get_current_user)]


def require_course_role(
    user: CurrentUser,
    course_id: int,
    *roles: Role,
    not_found: ErrorCode = "course_not_found",
) -> Role:
    """Kullanıcının bu derste (verildiyse) gereken role sahip olduğunu doğrular.

    Üye olmayana 404 döner: dersin (ya da dokümanın, kaynağın) varlığı sızdırılmaz. Üye ama
    rolü yetmiyorsa 403 `insufficient_role`.
    """
    role = user.roles.get(course_id)
    if role is None:
        raise not_found_error(not_found)
    if roles and role not in roles:
        raise ApiError(status.HTTP_403_FORBIDDEN, "Bu işlem için yetkiniz yok", "insufficient_role")
    return role


def not_found_error(code: ErrorCode) -> ApiError:
    return ApiError(status.HTTP_404_NOT_FOUND, _NOT_FOUND_DETAIL.get(code, "Bulunamadı"), code)


def require_consent(user: CurrentUser) -> None:
    """Kayıt tutulan yollar (soru-cevap) aydınlatma metninin kabulünü ister (ADR-4)."""
    if not user.consented:
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            "Devam etmek için aydınlatma metnini onaylamanız gerekiyor",
            "consent_required",
        )
