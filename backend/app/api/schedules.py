from uuid import UUID

from fastapi import APIRouter, Request

from app.schemas.execution import ExecutionInputError
from app.schemas.schedule import ScheduleRead, ScheduleUpdate

router = APIRouter(prefix="/workflows", tags=["schedules"])


@router.get("/{workflow_id}/schedule", response_model=ScheduleRead)
def get_schedule(workflow_id: UUID, request: Request) -> ScheduleRead:
    return request.app.state.scheduler.get(workflow_id)


@router.put(
    "/{workflow_id}/schedule",
    response_model=ScheduleRead,
    responses={422: {"model": ExecutionInputError}},
)
def update_schedule(workflow_id: UUID, payload: ScheduleUpdate, request: Request) -> ScheduleRead:
    return request.app.state.scheduler.set_enabled(workflow_id, payload.enabled)
