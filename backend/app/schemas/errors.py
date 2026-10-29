from typing import Literal

from pydantic import BaseModel

from app.schemas.workflow import ValidationIssue


class RequestValidationIssue(BaseModel):
    type: str
    loc: list[str | int]
    msg: str


class WorkflowStructureError(BaseModel):
    code: Literal["INVALID_WORKFLOW_STRUCTURE"]
    errors: list[ValidationIssue]


class WorkflowInputError(BaseModel):
    detail: list[RequestValidationIssue] | WorkflowStructureError
