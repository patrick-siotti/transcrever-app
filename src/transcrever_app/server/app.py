"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from transcrever_app.server.api.routes.folders import router as folders_router
from transcrever_app.server.api.routes.system import router as system_router
from transcrever_app.server.api.routes.transcriptions import router as transcriptions_router
from transcrever_app.server.config import AppSettings
from transcrever_app.server.instance_lock import InstanceLock
from transcrever_app.server.logging_config import close_local_logging, configure_local_logging
from transcrever_app.server.persistence.database import (
    create_session_factory,
    create_sqlite_engine,
    upgrade_schema,
)
from transcrever_app.server.services.maintenance_service import run_startup_maintenance
from transcrever_app.server.worker.runner import LocalJobRunner


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """Create one local-only application instance."""
    resolved_settings = settings or AppSettings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        instance_lock = InstanceLock(resolved_settings.data_dir)
        instance_lock.acquire()
        local_logger = None
        engine = None
        try:
            local_logger = configure_local_logging(resolved_settings.data_dir)
            engine = create_sqlite_engine(resolved_settings.database_path)
            upgrade_schema(engine)
            app.state.settings = resolved_settings
            app.state.local_logger = local_logger
            app.state.engine = engine
            app.state.session_factory = create_session_factory(engine)
            with app.state.session_factory() as session:
                app.state.maintenance_report = run_startup_maintenance(
                    session,
                    resolved_settings.runs_dir,
                )
            app.state.runner = None
            if resolved_settings.worker_enabled:
                app.state.runner = LocalJobRunner(
                    app.state.session_factory,
                    logger=local_logger,
                )
                app.state.runner.start()
            yield
            if app.state.runner is not None:
                app.state.runner.stop()
        finally:
            if engine is not None:
                engine.dispose()
            if local_logger is not None:
                close_local_logging(local_logger)
            instance_lock.release()

    app = FastAPI(
        title="Transcrever App",
        version="0.2.0",
        lifespan=lifespan,
        docs_url="/docs" if resolved_settings.debug else None,
        redoc_url=None,
    )
    _configure_error_contract(app)
    app.include_router(system_router)
    app.include_router(folders_router)
    app.include_router(transcriptions_router)
    _mount_frontend(app)
    return app


def _configure_error_contract(app: FastAPI) -> None:
    """Attach request correlation and a stable API error envelope."""

    @app.middleware("http")
    async def correlate_request(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        started_at = perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger = getattr(request.app.state, "local_logger", None)
        if logger is not None:
            duration_ms = (perf_counter() - started_at) * 1000
            logger.info(
                "request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
                request_id,
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )
        return response

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> Response:
        if not request.url.path.startswith("/api/"):
            return await http_exception_handler(request, exc)
        message = (
            exc.detail if isinstance(exc.detail, str) else "A operação não pôde ser concluída."
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": _error_code(exc.status_code),
                "message": message,
                "details": None if isinstance(exc.detail, str) else exc.detail,
                "request_id": request.state.request_id,
            },
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_exception(
        request: Request,
        exc: RequestValidationError,
    ) -> Response:
        if not request.url.path.startswith("/api/"):
            raise exc
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "code": "validation_error",
                "message": "Revise os dados informados.",
                "details": jsonable_encoder(exc.errors()),
                "request_id": request.state.request_id,
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(request: Request, exc: Exception) -> Response:
        if not request.url.path.startswith("/api/"):
            raise exc
        logger = getattr(request.app.state, "local_logger", None)
        if logger is not None:
            logger.exception("request_id=%s unexpected_api_error", request.state.request_id)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": "internal_error",
                "message": "O aplicativo encontrou um erro interno.",
                "details": None,
                "request_id": request.state.request_id,
            },
        )


def _error_code(status_code: int) -> str:
    """Map an HTTP status to a stable, non-sensitive error code."""
    return {
        400: "bad_request",
        404: "not_found",
        409: "conflict",
        413: "payload_too_large",
        422: "validation_error",
        500: "internal_error",
    }.get(status_code, "request_failed")


def _mount_frontend(app: FastAPI) -> None:
    """Serve the compiled SPA without requiring Node at runtime."""
    dist_dir = Path(__file__).resolve().parent / "static"
    index_file = dist_dir / "index.html"
    assets_dir = dist_dir / "assets"
    if not index_file.is_file() or not assets_dir.is_dir():
        return
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{spa_path:path}", include_in_schema=False)
    def serve_spa(spa_path: str) -> FileResponse:
        if spa_path.startswith("api/"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Endpoint não encontrado.")
        return FileResponse(index_file)
