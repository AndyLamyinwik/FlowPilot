import hashlib
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from threading import Lock
from typing import Callable, Iterator
from uuid import UUID, uuid4

from app.db.database import Database
from app.db.workflows import WorkflowRepository
from app.models.execution import ExecutionRecord, TriggerType
from app.schemas.execution import WorkflowExecutionResult
from app.services.execution.engine import ExecutionEngine
from app.services.history import HistoryService, duration_ms

logger = logging.getLogger("flowpilot.execution_service")


class ExecutionConflict(Exception):
    def __init__(self) -> None:
        super().__init__("Workflow already has an active operation")


class WorkflowNotFound(Exception):
    def __init__(self) -> None:
        super().__init__("Workflow not found")


class ExecutionStorageError(Exception):
    def __init__(self) -> None:
        super().__init__("Execution history storage unavailable")


class ExecutionServiceError(Exception):
    def __init__(self) -> None:
        super().__init__("Workflow execution could not be completed")


class ExecutionService:
    """One process-wide entry point for execution, exclusion and history writes."""

    def __init__(
        self, database: Database, engine_factory: Callable[[], ExecutionEngine], *,
        store_outputs: bool = False, history_max_bytes: int = 262_144,
        retention_days: int = 30,
    ) -> None:
        self.database = database
        self.engine_factory = engine_factory
        self.workflows = WorkflowRepository(database)
        self.history = HistoryService(
            database, store_outputs=store_outputs, history_max_bytes=history_max_bytes,
            retention_days=retention_days,
        )
        self._guard = Lock()
        # Only currently held IDs are retained; historical workflows do not leak locks.
        self._active: set[UUID] = set()

    @contextmanager
    def exclusive(self, workflow_id: UUID) -> Iterator[None]:
        with self._guard:
            if workflow_id in self._active:
                raise ExecutionConflict()
            self._active.add(workflow_id)
        try:
            yield
        finally:
            with self._guard:
                self._active.discard(workflow_id)

    def execute(
        self, workflow_id: UUID, *, trigger_type: TriggerType = "manual",
        scheduled_at: datetime | None = None,
        run_if: Callable[[], bool] | None = None,
        engine: ExecutionEngine | None = None,
    ) -> WorkflowExecutionResult | None:
        try:
            with self.exclusive(workflow_id):
                if run_if is not None and not run_if():
                    return None
                record = self.workflows.get(workflow_id)
                if record is None:
                    raise WorkflowNotFound()
                executor = engine if engine is not None else self.engine_factory()
                snapshot = executor.validate(record.definition, trigger_type=trigger_type)
                definition_hash = hashlib.sha256(json.dumps(
                    snapshot.model_dump(mode="json"), ensure_ascii=False,
                    sort_keys=True, separators=(",", ":"), allow_nan=False,
                ).encode("utf-8")).hexdigest()
                execution_id = uuid4()
                started_at = datetime.now(UTC)
                try:
                    self.history.repository.create_running(
                        execution_id, workflow_id, trigger_type, started_at, definition_hash,
                    )
                except sqlite3.Error:
                    # Never start external effects unless their running record is durable.
                    raise ExecutionStorageError() from None
                try:
                    result = executor.execute(
                        workflow_id, snapshot, execution_id=execution_id,
                        started_at=started_at, trigger_type=trigger_type,
                        scheduled_at=scheduled_at,
                    )
                except BaseException as error:
                    finished_at = datetime.now(UTC)
                    interrupted = not isinstance(error, Exception)
                    failure = ExecutionRecord(
                        execution_id, workflow_id, trigger_type,
                        "interrupted" if interrupted else "failed", started_at,
                        finished_at, duration_ms(started_at, finished_at), [],
                        {"code": "EXECUTION_INTERRUPTED" if interrupted else "EXECUTION_FAILED",
                         "message": "Execution interrupted" if interrupted else "Workflow execution failed",
                         "node_id": None}, started_at, definition_hash,
                    )
                    try:
                        self.history.repository.finish(failure)
                    except sqlite3.Error:
                        logger.error("Execution finalization failed (execution_id=%s)", execution_id)
                    if interrupted:
                        raise
                    raise ExecutionServiceError() from None
                try:
                    self.history.finish(result, trigger_type, definition_hash)
                except sqlite3.Error:
                    # Side effects may already have occurred: do not retry the workflow.
                    logger.error("Execution finalization failed (execution_id=%s)", execution_id)
                    raise ExecutionStorageError() from None
                return result
        except ExecutionConflict:
            if trigger_type != "schedule":
                raise
            logger.warning("Scheduled execution skipped: active workflow (workflow_id=%s)", workflow_id)
            self.record_skipped(workflow_id, "WORKFLOW_ALREADY_RUNNING", scheduled_at=scheduled_at)
            return None
        except sqlite3.Error:
            raise ExecutionStorageError() from None

    def record_skipped(
        self, workflow_id: UUID, reason_code: str,
        *, scheduled_at: datetime | None = None,
    ) -> None:
        now = datetime.now(UTC)
        execution_id = uuid4()
        # Reasons are generated by scheduler code, never exception messages/config.
        reason = reason_code if reason_code in {
            "WORKFLOW_ALREADY_RUNNING", "SCHEDULE_MISSED", "SCHEDULE_MAX_INSTANCES",
        } else "SCHEDULE_SKIPPED"
        try:
            if self.workflows.get(workflow_id) is None:
                return
            self.history.repository.create_running(execution_id, workflow_id, "schedule", now, "")
            self.history.repository.finish(ExecutionRecord(
                execution_id, workflow_id, "schedule", "skipped", now, now, 0, [],
                {"code": reason, "message": "Scheduled execution skipped", "node_id": None},
                now, "",
            ))
        except sqlite3.Error:
            logger.error("Skipped execution history unavailable (workflow_id=%s)", workflow_id)
