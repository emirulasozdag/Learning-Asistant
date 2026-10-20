from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Response, status

from app.api.deps import DbSession
from app.api.errors import ApiError
from app.auth import demo, service
from app.auth.dependencies import AuthUser
from app.auth.sessions import clear_session_cookie, create_session, end_session, set_session_cookie
from app.core.config import settings
from app.schemas.auth import (
    Consent,
    ConsentUpdate,
    DemoInfo,
    DemoLoginRequest,
    LoginRequest,
    Me,
    RegisterRequest,
)

router = APIRouter(tags=["auth"])

SessionCookie = Annotated[str | None, Cookie(alias=settings.session_cookie_name)]


@router.post("/auth/register", response_model=Me, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, db: DbSession, response: Response) -> Me:
    """Öğrenci hesabı açar ve oturumu başlatır. Eğitmen/TA rolü kayıtla alınamaz (ADR-1)."""
    try:
        user = service.register(db, data)
    except service.InvalidInput as exc:
        raise ApiError(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc), "validation_error") from exc
    except service.EmailExists as exc:
        raise ApiError(
            status.HTTP_409_CONFLICT, "Bu e-postayla bir hesap zaten var.", "email_exists"
        ) from exc
    set_session_cookie(response, create_session(db, user))
    return service.me(db, user)


@router.post("/auth/login", response_model=Me)
def login(
    data: LoginRequest, db: DbSession, response: Response, current: SessionCookie = None
) -> Me:
    """E-posta + şifre; başarılıysa yeni oturum çerezi (httpOnly) yazılır."""
    user = service.authenticate(db, data.email, data.password)
    if user is None:
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED, "E-posta ya da şifre hatalı", "not_authenticated"
        )
    # Önceki oturum (varsa) kapatılır: giriş her zaman yeni belirteçle başlar.
    end_session(db, current)
    set_session_cookie(response, create_session(db, user))
    return service.me(db, user)


@router.get("/auth/demo", response_model=DemoInfo)
def demo_accounts(db: DbSession) -> DemoInfo:
    """Sunum modu: giriş ekranındaki demo hesapları ve katılım kodları. Kapalıysa 404."""
    _require_demo()
    return demo.demo_info(db)


@router.post("/auth/demo-login", response_model=Me)
def demo_login(
    data: DemoLoginRequest, db: DbSession, response: Response, current: SessionCookie = None
) -> Me:
    """Sunum modu: seçilen roldeki geliştirme hesabına şifresiz giriş. Kapalıysa 404."""
    _require_demo()
    user = demo.demo_user(db, data.role)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Demo hesabı yok")
    end_session(db, current)
    set_session_cookie(response, create_session(db, user))
    return service.me(db, user)


def _require_demo() -> None:
    # Kapalıyken yanıt, olmayan bir adresinkiyle aynıdır: uç noktanın varlığı belli edilmez.
    if not settings.demo_login:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(db: DbSession, response: Response, current: SessionCookie = None) -> None:
    end_session(db, current)
    clear_session_cookie(response)


@router.get("/me", response_model=Me)
def get_me(user: AuthUser, db: DbSession) -> Me:
    """Oturumdaki kullanıcı, ders üyelikleri ve onay durumu."""
    return service.me(db, user.user)


@router.put("/me/consent", response_model=Consent)
def update_consent(data: ConsentUpdate, user: AuthUser, db: DbSession) -> Consent:
    """Aydınlatma metninin güncel sürümünü onaylar; araştırma kaydını açar/kapatır (ADR-4)."""
    try:
        return service.update_consent(db, user.user, data)
    except service.InvalidInput as exc:
        raise ApiError(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc), "validation_error") from exc


@router.delete("/me/data", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_data(user: AuthUser, db: DbSession) -> None:
    """Verilerimi sil (ADR-4): bütün sohbetlerim ve mesajlarım silinir; hesap kalır."""
    service.delete_my_data(db, user.user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(user: AuthUser, db: DbSession, response: Response) -> None:
    """Hesabı ve ona bağlı bütün kişisel veriyi siler; oturum kapanır."""
    service.delete_account(db, user.user)
    clear_session_cookie(response)
