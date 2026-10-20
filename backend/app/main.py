import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint

from app.api import (
    ask,
    auth,
    courses,
    health,
    instructor,
    learning,
    materials,
    practice,
    rubrics,
    sources,
)
from app.api.errors import ApiError, api_error_handler
from app.core.config import settings
from app.db.session import SessionLocal
from app.embeddings.provider import get_embedder
from app.retrieval.index import stale_chunk_count

logger = logging.getLogger(__name__)


def _warm_up_embedder() -> None:
    try:
        embedder = get_embedder()
        embedder.embed_query("ısınma")
    except Exception:
        logger.exception("Embedding modeli önceden yüklenemedi; ilk istekte yeniden denenecek")
        return
    _warn_stale_vectors(embedder.identity)


def _warn_stale_vectors(identity: str) -> None:
    """Model değiştiyse ya da eski vektörler kimliksizse anlamsal arama onları kullanmaz."""
    try:
        with SessionLocal() as db:
            stale = stale_chunk_count(db, identity)
    except Exception:
        return  # Veritabanı henüz hazır değil; sorun ilk istekte görünür.
    if stale:
        logger.warning(
            "%d parça etkin embedder'la (%s) vektörleştirilmemiş; anlamsal arama bunları "
            "kullanmaz. Yeniden üretmek için: python -m app.scripts.reembed",
            stale,
            identity,
        )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Embedding modeli arka planda belleğe alınır; ilk soru/yükleme beklemesin.
    threading.Thread(target=_warm_up_embedder, daemon=True).start()
    yield


app = FastAPI(title="Interactive Learning Assistant API", version="0.0.1", lifespan=lifespan)

app.add_exception_handler(ApiError, api_error_handler)

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@app.middleware("http")
async def reject_cross_site_writes(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    """CSRF savunması: oturum çerezle taşındığı için durum değiştiren istek yalnızca izinli
    kökenden (CORS_ORIGINS ya da API'nin kendisi) kabul edilir. Origin göndermeyen istemciler
    (curl, testler) tarayıcı değildir, çerezi kendileri vermek zorundadır."""
    origin = request.headers.get("origin")
    if request.method not in _SAFE_METHODS and origin is not None:
        own = f"{request.url.scheme}://{request.headers.get('host', '')}"
        if origin not in settings.cors_origins and origin != own:
            return JSONResponse({"detail": "Bu kökenden gelen isteğe izin verilmiyor"}, 403)
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(materials.router)
app.include_router(ask.router)
app.include_router(sources.router)
app.include_router(practice.router)
app.include_router(learning.router)
app.include_router(instructor.router)
app.include_router(rubrics.router)
