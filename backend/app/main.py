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

app = FastAPI(title="Interactive Learning Assistant API", version="0.0.1")

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
