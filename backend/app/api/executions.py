from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.workflows import Repository
from app.core.http_policy import HTTPPolicy
from app.core.config import Settings
from app.schemas.execution import ExecutionInputError, WorkflowExecutionResult
from app.services.execution.context import ExecutionLimits
from app.services.execution.engine import ExecutionEngine
from app.services.execution.executor import create_default_executor_registry
from app.services.execution.safe_http import SafeHttpClient
from app.services.execution.validation import ExecutionValidationError

router = APIRouter(prefix="/workflows", tags=["executions"])


def get_engine(request: Request) -> ExecutionEngine:
    return build_engine(request.app.state.settings)


def build_engine(settings: Settings) -> ExecutionEngine:
    """Identical executors and limits for API and scheduler invocations."""
    return ExecutionEngine(
        registry=create_default_executor_registry(
            SafeHttpClient(
                HTTPPolicy(
                    allowed_hosts=tuple(settings.http_allowed_hosts),
                    allow_insecure=settings.http_allow_insecure,
                    max_request_bytes=settings.http_max_request_bytes,
                    max_response_bytes=settings.http_max_response_bytes,
                )
            )
        ),
        limits=ExecutionLimits(
            max_nodes=settings.execution_max_nodes,
            max_output_bytes=settings.execution_max_output_bytes,
        )
    )


Engine = Annotated[ExecutionEngine, Depends(get_engine)]


@router.post(
    "/{workflow_id}/execute",
    response_model=WorkflowExecutionResult,
    responses={
        404: {"description": "Workflow not found"},
        409: {"description": "Workflow already has an active execution"},
        503: {"description": "Execution history storage unavailable"},
        422: {
            "model": ExecutionInputError,
            "description": "Invalid workflow ID or workflow is not executable",
        },
    },
)
def execute_workflow(
    workflow_id: UUID, request: Request, repository: Repository, engine: Engine
) -> WorkflowExecutionResult:
    """Execute a manual workflow through the shared history and concurrency service."""
    try:
        return request.app.state.execution_service.execute(workflow_id, engine=engine)
    except ExecutionValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "WORKFLOW_NOT_EXECUTABLE",
                "errors": [issue.model_dump(mode="json") for issue in error.errors],
            },
        ) from None
