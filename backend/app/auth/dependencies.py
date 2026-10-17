from dataclasses import dataclass
from typing import Literal

Role = Literal["student", "instructor", "ta"]


@dataclass
class CurrentUser:
    id: int
    roles: dict[int, Role]  # course_id → rol


def get_current_user() -> CurrentUser:
    """İstekteki kullanıcıyı çöz. Uygulanınca endpoint'lere Depends ile bağlanacak."""
    raise NotImplementedError


def require_course_role(user: CurrentUser, course_id: int, *roles: Role) -> None:
    """Kullanıcının bu derste gereken role sahip olduğunu doğrula."""
    raise NotImplementedError
