import logging
import sqlite3
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response
from starlette.concurrency import run_in_threadpool

from app.api.router import api_router
from app.api.executions import build_engine
from app.core.config import Settings
from app.core.logging import configure_logging
from app.db.database import Database
from app.core.instance import InstanceLock
from app.services.execution_service import (
    ExecutionService, ExecutionConflict, ExecutionStorageError, WorkflowNotFound,
)
from app.services.execution.validation import ExecutionValidationError
from app.services.scheduler import SchedulerService

logger = logging.getLogger("flowpilot")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        database = Database(settings.database_path)
        owner = InstanceLock(settings.database_path)
        owner.acquire()
        try:
            database.initialize()
            application.state.database = database
            service = ExecutionService(
                database, lambda: build_engine(settings),
                store_outputs=settings.store_execution_outputs,
                history_max_bytes=settings.history_max_record_bytes,
                retention_days=settings.history_retention_days,
            )
            application.state.execution_service = service
            scheduler = SchedulerService(
                database, service, enabled=settings.scheduler_enabled,
                workers=settings.scheduler_workers,
            )
            application.state.scheduler = scheduler
            await run_in_threadpool(service.history.recover_interrupted)
            await run_in_threadpool(service.history.cleanup)
            await run_in_threadpool(scheduler.start)
            logger.info("FlowPilot started; single backend owner acquired")
            try:
                yield
            finally:
                await run_in_threadpool(scheduler.shutdown)
        finally:
            owner.release()
            logger.info("FlowPilot stopped")

    application = FastAPI(title="FlowPilot API", version="0.1.0", lifespan=lifespan)
    application.state.settings = settings
    application.include_router(api_router)

    @application.exception_handler(WorkflowNotFound)
    async def workflow_not_found(request: Request, error: WorkflowNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "Workflow not found"})

    @application.exception_handler(ExecutionConflict)
    async def execution_conflict(request: Request, error: ExecutionConflict) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": "Workflow has an active execution"})

    @application.exception_handler(ExecutionValidationError)
    async def invalid_execution(request: Request, error: ExecutionValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": {
            "code": "WORKFLOW_NOT_EXECUTABLE",
            "errors": [issue.model_dump(mode="json") for issue in error.errors],
        }})

    @application.exception_handler(ExecutionStorageError)
    @application.exception_handler(sqlite3.Error)
    async def unavailable_storage(request: Request, error: Exception) -> JSONResponse:
        logger.error("SQLite operation failed; request could not be completed")
        return JSONResponse(status_code=503, content={"detail": "Execution storage unavailable"})

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        # Pydantic's input/context may contain rejected credentials; never echo them.
        errors = [
            {key: item[key] for key in ("type", "loc", "msg") if key in item}
            for item in error.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": errors})

    @application.middleware("http")
    async def handle_errors(request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            return await call_next(request)
        except Exception:
            logger.exception("Unhandled request error: %s %s", request.method, request.url.path)
            return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    application.add_middleware(
        TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts, www_redirect=False,
    )
    # CORS wraps Host validation and the error boundary, including their errors.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Accept", "Content-Type"],
        expose_headers=["X-FlowPilot-Schedule-Enabled", "X-FlowPilot-Schedule-Error"],
    )

    return application


app = create_app()
