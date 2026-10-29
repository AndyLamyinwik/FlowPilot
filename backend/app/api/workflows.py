from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.db.workflows import WorkflowRepository
from app.schemas.errors import WorkflowInputError
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowDefinition,
    WorkflowRead,
    WorkflowUpdate,
    WorkflowValidationReport,
)
from app.services.workflow_validation import validate_workflow

router = APIRouter(prefix="/workflows", tags=["workflows"])
validation_responses = {
    422: {"model": WorkflowInputError, "description": "Invalid request schema or workflow structure"}
}


def get_repository(request: Request) -> WorkflowRepository:
    return WorkflowRepository(request.app.state.database)


Repository = Annotated[WorkflowRepository, Depends(get_repository)]


def _validated_definition(definition: WorkflowDefinition) -> dict:
    report = validate_workflow(definition)
    if not report.can_save:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "INVALID_WORKFLOW_STRUCTURE",
                "errors": [issue.model_dump(mode="json") for issue in report.structural.errors],
            },
        )
    return definition.model_dump(mode="json")


@router.get("", response_model=list[WorkflowRead])
def list_workflows(repository: Repository) -> list[WorkflowRead]:
    return [WorkflowRead.model_validate(record) for record in repository.list_all()]


@router.post(
    "", response_model=WorkflowRead, status_code=status.HTTP_201_CREATED,
    responses=validation_responses,
)
def create_workflow(payload: WorkflowCreate, response: Response, repository: Repository) -> WorkflowRead:
    definition = _validated_definition(payload.definition)
    record = repository.create(payload.name, payload.description, definition)
    response.headers["Location"] = f"/api/workflows/{record.id}"
    return WorkflowRead.model_validate(record)


@router.get("/{workflow_id}", response_model=WorkflowRead)
def get_workflow(workflow_id: UUID, repository: Repository) -> WorkflowRead:
    record = repository.get(workflow_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return WorkflowRead.model_validate(record)


@router.put("/{workflow_id}", response_model=WorkflowRead, responses=validation_responses)
def update_workflow(
    workflow_id: UUID, payload: WorkflowUpdate, request: Request,
    response: Response, repository: Repository,
) -> WorkflowRead:
    definition = _validated_definition(payload.definition)
    scheduler = request.app.state.scheduler
    with scheduler.mutation():
        record = repository.update(workflow_id, payload.name, payload.description, definition)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
        schedule = scheduler.workflow_updated(workflow_id)
    response.headers["X-FlowPilot-Schedule-Enabled"] = str(schedule.enabled).lower()
    if schedule.last_error:
        response.headers["X-FlowPilot-Schedule-Error"] = schedule.last_error
    return WorkflowRead.model_validate(record)


@router.delete(
    "/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT,
    responses={409: {"description": "Workflow has an active execution"}},
)
def delete_workflow(workflow_id: UUID, request: Request, repository: Repository) -> Response:
    # Same guard as execution closes the check/delete race without a long SQL transaction.
    with request.app.state.execution_service.exclusive(workflow_id):
        scheduler = request.app.state.scheduler
        with scheduler.mutation():
            if not repository.delete(workflow_id):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
            scheduler.workflow_deleted(workflow_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{workflow_id}/validate", response_model=WorkflowValidationReport)
def validate_saved_workflow(workflow_id: UUID, repository: Repository) -> WorkflowValidationReport:
    record = repository.get(workflow_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return validate_workflow(WorkflowDefinition.model_validate(record.definition))
