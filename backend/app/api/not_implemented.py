from typing import NoReturn

from fastapi import HTTPException, status


def not_implemented(feature: str) -> NoReturn:
    """İskelet endpoint'leri için ortak 501 cevabı."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"{feature} henüz uygulanmadı",
    )
