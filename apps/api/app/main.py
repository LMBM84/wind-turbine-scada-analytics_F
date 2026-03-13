"""
Wind Turbine SCADA Analytics — FastAPI Application Entry Point
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.core.database import engine, create_all_tables
from app.core.redis import get_redis_client
from app.routers import scada, analytics, anomalies, turbines, websocket_router
from shared.config.settings import settings
from shared.utils.logging import configure_logging

logger = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────
#  Lifespan (startup / shutdown)
# ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    configure_logging(level=settings.log_level, json_output=settings.environment == "production")
    logger.info("Starting SCADA API", env=settings.environment)

    # Startup
    await create_all_tables()
    redis = await get_redis_client()
    app.state.redis = redis
    logger.info("Database and Redis connections established")

    yield  # ← App runs here

    # Shutdown
    await redis.aclose()
    await engine.dispose()
    logger.info("Shutdown complete")


# ─────────────────────────────────────────────────────────────
#  Application factory
# ─────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="Wind Turbine SCADA Analytics API",
        description=(
            "Production-grade REST + WebSocket API for wind turbine monitoring, "
            "power curve analysis, and ML-powered anomaly detection. "
            "Data: Kelmarsh Wind Farm (CC-BY-4.0)."
        ),
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── Middleware ────────────────────────────────────────────
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Request timing middleware ─────────────────────────────
    @app.middleware("http")
    async def add_process_time_header(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        response.headers["X-Process-Time"] = f"{elapsed:.4f}s"
        return response

    # ── Exception handlers ────────────────────────────────────
    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def generic_handler(request: Request, exc: Exception):
        logger.error("Unhandled exception", path=request.url.path, error=str(exc))
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    # ── Routers ───────────────────────────────────────────────
    app.include_router(turbines.router, prefix="/api/v1/turbines", tags=["turbines"])
    app.include_router(scada.router, prefix="/api/v1/scada", tags=["scada"])
    app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"])
    app.include_router(anomalies.router, prefix="/api/v1/anomalies", tags=["anomalies"])
    app.include_router(websocket_router.router, prefix="/ws", tags=["websocket"])

    # ── Health / info endpoints ───────────────────────────────
    @app.get("/health", tags=["system"])
    async def health_check():
        return {"status": "ok", "version": "2.0.0", "environment": settings.environment}

    @app.get("/", tags=["system"])
    async def root():
        return {
            "name": settings.app_name,
            "docs": "/docs",
            "health": "/health",
        }

    return app


app = create_app()
