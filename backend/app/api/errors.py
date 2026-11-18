import math

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
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


async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """FastAPI'nin 422 yanıtıyla aynı biçim (`{detail: [...]}`); tek fark, hatalı girdideki sonsuz
    ya da NaN sayıların metne çevrilmesi (#25). Aksi hâlde JSON'a yazılamayan girdi (ör.
    `time_s: 1e999`) 422 yerine 500 verirdi."""
    assert isinstance(exc, RequestValidationError)
    return JSONResponse({"detail": _json_safe(jsonable_encoder(exc.errors()))}, status_code=422)


def _json_safe(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    return value
