"""FastAPI application factory for LabMeter Suite."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import logging
import os
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_error_handlers
from app.api.routers import alerts, analytics, auth, calendar, energy, forecasts, imports, labs, models, readings, reports
from app.auth.rate_limit import LoginLimiter
from app.config import BASE_DIR, CORS_ORIGINS, ENABLE_API_DOCS, HSTS_ENABLED, LOGIN_WINDOW_MINUTES, MAX_IMPORT_BYTES, MODEL_DIR
from app.ml.registry import ModelRegistry
from datetime import timedelta
from app.db.session import make_engine, make_session_factory


logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("labmeter")

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


def resolve_interface_file(root: Path, full_path: str) -> Optional[Path]:
    """Return the file inside the built interface folder that a URL path names, or None.

    Resolves symbolic links and '..' first, then checks the result is still inside root.
    """
    if not full_path:
        return None
    candidate = (root / full_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def create_app(session_factory=None, max_import_bytes: int = MAX_IMPORT_BYTES,
               model_dir: Optional[Path] = None, frontend_dist: Optional[Path] = None) -> FastAPI:
    docs_url = "/docs" if ENABLE_API_DOCS else None
    openapi_url = "/openapi.json" if ENABLE_API_DOCS else None
    app = FastAPI(title="LabMeter Suite API", version="0.4.0", docs_url=docs_url,
                  redoc_url=None, openapi_url=openapi_url)
    app.state.session_factory = session_factory or make_session_factory(make_engine())
    app.state.max_import_bytes = max_import_bytes
    app.state.model_registry = ModelRegistry(Path(model_dir) if model_dir else Path(MODEL_DIR))
    app.state.login_limiter = LoginLimiter(window=timedelta(minutes=LOGIN_WINDOW_MINUTES))

    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_methods=["GET", "POST", "PUT", "PATCH"],
        allow_headers=["Content-Type", "Authorization"],
    )
    register_error_handlers(app)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        request_id = uuid.uuid4().hex
        logger.exception("unhandled error request_id=%s method=%s path=%s", request_id, request.method, request.url.path)
        return JSONResponse(status_code=500, content={"error": {
            "code": "internal_error",
            "message": "something went wrong; the error has been logged",
            "details": {"request_id": request_id},
        }})

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        if HSTS_ENABLED:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    @app.get("/api/health", tags=["system"])
    def health():
        return {"status": "ok"}

    for router in (auth.router, labs.router, readings.router, imports.router, analytics.router, forecasts.router,
                   models.router, alerts.router, calendar.router, energy.router, reports.router):
        app.include_router(router, prefix="/api")

    # Serve the built interface from the same origin when it exists, so one service can host everything.
    # Registered last, so every /api route above takes precedence.
    dist = Path(frontend_dist) if frontend_dist else BASE_DIR / "frontend" / "dist"
    if dist.is_dir() and (dist / "index.html").is_file():
        root = dist.resolve()

        @app.get("/{full_path:path}", include_in_schema=False)
        def interface(full_path: str):
            if full_path == "api" or full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="not found")
            found = resolve_interface_file(root, full_path)
            return FileResponse(found if found is not None else root / "index.html")

    return app


app = create_app()
