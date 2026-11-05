"""FastAPI application entry point."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

import truststore
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import admin, assistant, sops
from app.connectors.sharepoint.graph_client import GraphError
from app.core.config import get_settings
from app.core.logging import configure_logging

log = logging.getLogger("app")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.use_system_trust_store:
        # Use the OS certificate store for outbound HTTPS (Graph, Anthropic), so corporate
        # TLS-inspection certificates trusted by Windows are trusted here too.
        truststore.inject_into_ssl()

    app = FastAPI(
        title="Avi.Intelligence API",
        version="0.1.0",
        docs_url="/api/docs" if settings.app_env != "production" else None,
        openapi_url="/api/openapi.json" if settings.app_env != "production" else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        expose_headers=["Content-Disposition"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        log.info(
            "http.request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return response

    @app.exception_handler(GraphError)
    async def graph_error_handler(_request: Request, exc: GraphError) -> JSONResponse:
        log.warning("sharepoint.error", extra={"status": exc.status, "code": exc.code, "error": str(exc)})
        return JSONResponse(status_code=502, content={"detail": f"SharePoint error: {exc}"})

    @app.get("/api/health", tags=["Health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(sops.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")
    app.include_router(assistant.router, prefix="/api/v1")
    return app


app = create_app()
