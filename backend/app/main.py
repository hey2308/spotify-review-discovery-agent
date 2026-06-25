from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.routers import (
    health,
    meta,
    overview,
    questions,
    quotes,
    segments,
    themes,
    unmet_needs,
)
from core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Spotify Discovery Intelligence API",
    version=settings.app_version,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(overview.router, prefix="/api")
app.include_router(themes.router, prefix="/api")
app.include_router(questions.router, prefix="/api")
app.include_router(quotes.router, prefix="/api")
app.include_router(segments.router, prefix="/api")
app.include_router(unmet_needs.router, prefix="/api")
app.include_router(meta.router, prefix="/api")


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Spotify Discovery Intelligence API", "docs": "/api/docs"}


@app.get("/docs", include_in_schema=False)
def docs_redirect() -> RedirectResponse:
    return RedirectResponse(url="/api/docs")


@app.get("/redoc", include_in_schema=False)
def redoc_redirect() -> RedirectResponse:
    return RedirectResponse(url="/api/redoc")
