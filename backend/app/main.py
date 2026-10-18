import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    ask,
    courses,
    health,
    instructor,
    learning,
    materials,
    practice,
    rubrics,
    sources,
)
from app.core.config import settings
from app.embeddings.provider import get_embedder

logger = logging.getLogger(__name__)


def _warm_up_embedder() -> None:
    try:
        get_embedder().embed_query("ısınma")
    except Exception:
        logger.exception("Embedding modeli önceden yüklenemedi; ilk istekte yeniden denenecek")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Embedding modeli arka planda belleğe alınır; ilk soru/yükleme beklemesin.
    threading.Thread(target=_warm_up_embedder, daemon=True).start()
    yield


app = FastAPI(title="Interactive Learning Assistant API", version="0.0.1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(courses.router)
app.include_router(materials.router)
app.include_router(ask.router)
app.include_router(sources.router)
app.include_router(practice.router)
app.include_router(learning.router)
app.include_router(instructor.router)
app.include_router(rubrics.router)
