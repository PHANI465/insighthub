"""
backend/app/main.py

FastAPI application entry point for InsightHub.

Startup sequence
────────────────
  1. Inject Azure Key Vault secrets into os.environ (if configured)
  2. Validate all required settings are present
  3. Initialise Application Insights telemetry
  4. Register all API routers
  5. Start serving requests

Middleware stack (applied in reverse registration order)
──────────────────────────────────────────────────────────
  TrustedHostMiddleware → blocks unexpected Host headers
  CORSMiddleware        → allows the React frontend origin
  GZipMiddleware        → compresses large metric responses
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pyodbc
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, insights, metrics, powerbi, search
from app.core.appinsights import init_telemetry
from app.core.config import get_settings
from app.core.database import get_db, execute_scalar
from app.core.keyvault import inject_keyvault_secrets_into_env
from app.models.schemas import HealthResponse

log = logging.getLogger(__name__)


# ── Lifespan (startup / shutdown events) ─────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: load Key Vault secrets → validate settings → init telemetry.
    Shutdown: nothing to tear down (pyodbc connections are per-request).
    """
    # 1. Key Vault — inject secrets into env before Settings() is created
    settings_pre = get_settings()
    inject_keyvault_secrets_into_env(settings_pre.azure_keyvault_url)

    # 2. Reload settings (will pick up any newly injected env vars)
    from app.core.config import invalidate_settings_cache
    invalidate_settings_cache()
    settings = get_settings()

    # 3. Application Insights
    init_telemetry(settings.applicationinsights_connection_string)

    log.info("InsightHub API %s started.", settings.app_version)
    log.info("  Database : %s / %s", settings.db_server, settings.db_name)
    log.info("  Debug    : %s", settings.debug)

    yield

    log.info("InsightHub API shutting down.")


# ── Application factory ───────────────────────────────────────────────────────

def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "InsightHub REST API — AI-powered business analytics platform. "
            "Provides KPI metrics, AI-powered search (RAG), executive insights, "
            "and Power BI embedded report tokens."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── Middleware ────────────────────────────────────────────────────────────
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
        max_age=3600,
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(auth.router)
    app.include_router(metrics.router)
    app.include_router(search.router)
    app.include_router(insights.router)
    app.include_router(powerbi.router)

    # ── Global error handler ─────────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """
        Catch-all error handler.
        Returns a generic error message — never exposes internal details.
        OWASP A09: Security Logging and Monitoring — logs full details server-side.
        """
        from app.core.appinsights import track_exception
        track_exception(exc, {"path": str(request.url.path)})
        log.exception("Unhandled exception on %s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An internal server error occurred. Please try again later."},
        )

    # ── Health endpoint (public — no auth required) ───────────────────────────
    @app.get(
        "/api/health",
        response_model=HealthResponse,
        tags=["Health"],
        summary="Service health check",
    )
    def health_check() -> HealthResponse:
        """
        Returns database connectivity status.
        Used by Azure App Service health probes and load balancers.
        """
        db_status = "connected"
        try:
            with get_db() as conn:
                result = execute_scalar(conn, "SELECT 1")
                if result != 1:
                    db_status = "error: unexpected result"
        except Exception as exc:
            db_status = f"error: {type(exc).__name__}"

        overall = "healthy" if db_status == "connected" else "degraded"
        return HealthResponse(
            status=overall,
            version=settings.app_version,
            database=db_status,
            timestamp=datetime.now(timezone.utc),
        )

    return app


# ── Entry point ───────────────────────────────────────────────────────────────

app = create_app()

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="info",
    )
