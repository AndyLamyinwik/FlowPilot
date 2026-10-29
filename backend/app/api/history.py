from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.workflows import Repository
from app.schemas.history import (
    ExecutionHistoryDetail,
    ExecutionHistoryPage,
    ExecutionStatus,
    ExecutionSummary,
)

router = APIRouter(tags=["execution history"])


@router.get("/workflows/{workflow_id}/executions", response_model=ExecutionHistoryPage)
def list_executions(
    workflow_id: UUID,
    request: Request,
    repository: Repository,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: ExecutionStatus | None = None,
) -> ExecutionHistoryPage:
    if repository.get(workflow_id) is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    history = request.app.state.execution_service.history.repository
    records, total = history.list_for_workflow(
        workflow_id, limit=limit, offset=offset, status=status
    )
    return ExecutionHistoryPage(
        items=[ExecutionSummary.model_validate(record, from_attributes=True) for record in records],
        total=total, limit=limit, offset=offset,
    )


@router.get("/executions/{execution_id}", response_model=ExecutionHistoryDetail)
def get_execution(execution_id: UUID, request: Request) -> ExecutionHistoryDetail:
    record = request.app.state.execution_service.history.repository.get(execution_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    return ExecutionHistoryDetail.model_validate(record, from_attributes=True)
