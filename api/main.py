# api/main.py

import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import settings
from core.logger import get_logger
from api.crm_mock import router as crm_router
from api.voice_router import router as voice_router
from api.chat_router import router as chat_router
from api.metrics_router import router as metrics_router

logger = get_logger(__name__)


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs once on startup and once on shutdown.
    Use this for initializing DB connections, warming up models, etc.
    """
    logger.info(
        "app.startup",
        env=settings.app_env.value,
        host=settings.app_host,
        port=settings.app_port,
    )
    yield
    logger.info("app.shutdown")


# ── App Factory ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="AgAI-7 Voice and Chat Scheduling Agent",
    description=(
        "Gemini-powered AI scheduling agent for field service businesses. "
        "Handles appointment booking, rescheduling, and cancellations via "
        "voice calls and chat messages with full CRM integration."
    ),
    version="1.0.0",
    contact={
        "name": "Muhammad Umair | Datawebify",
        "url": "https://datawebify.com",
    },
    lifespan=lifespan,
)


# ── Middleware ────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Log every request with method, path, status code, and duration."""
    start = time.time()
    try:
        response = await call_next(request)
        duration_ms = round((time.time() - start) * 1000, 2)
        print(f"[{response.status_code}] {request.method} {request.url.path} {duration_ms}ms")
        return response
    except Exception as exc:
        duration_ms = round((time.time() - start) * 1000, 2)
        print(f"[500] {request.method} {request.url.path} {duration_ms}ms ERROR: {exc}")
        raise


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(crm_router)
app.include_router(voice_router)
app.include_router(chat_router)
app.include_router(metrics_router)


# ── Root and Health Endpoints ─────────────────────────────────────────────────

@app.get("/", tags=["Root"])
async def root() -> dict:
    return {
        "project": "AgAI-7 Voice and Chat Scheduling Agent",
        "brand": "Datawebify",
        "version": "1.0.0",
        "status": "online",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", tags=["Root"])
async def health_check() -> dict:
    return {
        "status": "healthy",
        "env": settings.app_env.value,
        "routers": ["crm", "voice", "chat", "metrics"],
    }


# ── Global Exception Handler ──────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        error=str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "An unexpected error occurred.",
            "detail": str(exc),
        },
    )