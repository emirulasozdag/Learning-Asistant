from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from app.schemas.common import ErrorCode


class ApiError(HTTPException):
    """Makine tarafından okunan kodu olan uygulama hatası: `{detail, code}` (CONTRACTS.md §5)."""

    def __init__(
        self,
        status_code: int,
        detail: str,
        code: ErrorCode,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code, detail, headers)
        self.code = code


async def api_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return JSONResponse(
        {"detail": exc.detail, "code": exc.code}, status_code=exc.status_code, headers=exc.headers
    )
