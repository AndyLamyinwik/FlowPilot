from fastapi import APIRouter

from app.api.executions import router as executions_router
from app.api.health import router as health_router
from app.api.node_types import router as node_types_router
from app.api.workflows import router as workflows_router
from app.api.schedules import router as schedules_router
from app.api.history import router as history_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(workflows_router)
api_router.include_router(node_types_router)
api_router.include_router(executions_router)
api_router.include_router(schedules_router)
api_router.include_router(history_router)
