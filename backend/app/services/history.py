import json
import logging
import re
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.db.database import Database
from app.db.executions import ExecutionRepository
from app.models.execution import ExecutionRecord, TriggerType
from app.schemas.execution import ExecutionError, WorkflowExecutionResult
from app.schemas.workflow import SECRET_KEYS

logger = logging.getLogger("flowpilot.history")
_REDACTED = "[REDACTED]"


def duration_ms(started: datetime | None, finished: datetime | None) -> int | None:
    if started is None or finished is None:
        return None
    return max(0, int((finished - started).total_seconds() * 1000))


def safe_error(error: ExecutionError | None, *, workflow: bool = False) -> dict | None:
    """Do not persist arbitrary exception or executor-provided message text."""
    if error is None:
        return None
    code = error.code if re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", error.code) else "EXECUTION_FAILED"
    return {
        "code": code,
        "message": "Workflow execution failed" if workflow else "Node execution failed",
        "node_id": error.node_id,
    }


def _redact(value: Any, depth: int = 0) -> Any:
    if depth >= 64:
        return _REDACTED
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            normalized = "".join(ch for ch in key.casefold() if ch.isalnum())
            result[key] = (
                _REDACTED
                if normalized in SECRET_KEYS or normalized in {"token", "credentials"}
                else _redact(child, depth + 1)
            )
        return result
    if isinstance(value, list):
        return [_redact(child, depth + 1) for child in value]
    return value


def _size(record: ExecutionRecord) -> int:
    return len(json.dumps(
        asdict(record), ensure_ascii=False, allow_nan=False,
        separators=(",", ":"), default=str,
    ).encode("utf-8"))


class HistoryService:
    def __init__(
        self, database: Database, *, store_outputs: bool = False,
        history_max_bytes: int = 262_144, retention_days: int = 30,
    ) -> None:
        if type(history_max_bytes) is not int or history_max_bytes < 4096:
            raise ValueError("History record limit must be at least 4096 bytes")
        if type(retention_days) is not int or not 1 <= retention_days <= 3650:
            raise ValueError("History retention must be between 1 and 3650 days")
        self.repository = ExecutionRepository(database)
        self.store_outputs = store_outputs
        self.history_max_bytes = history_max_bytes
        self.retention_days = retention_days

    def finish(
        self, result: WorkflowExecutionResult, trigger_type: TriggerType,
        definition_hash: str,
    ) -> ExecutionRecord:
        nodes = []
        for item in result.node_results:
            nodes.append({
                "node_id": item.node_id, "status": item.status,
                "output": _redact(item.output) if self.store_outputs else None,
                "error": safe_error(item.error),
                "started_at": item.started_at.isoformat() if item.started_at else None,
                "finished_at": item.finished_at.isoformat() if item.finished_at else None,
                "duration_ms": duration_ms(item.started_at, item.finished_at),
            })
        record = ExecutionRecord(
            execution_id=result.execution_id, workflow_id=result.workflow_id,
            trigger_type=trigger_type, status=result.status,
            started_at=result.started_at, finished_at=result.finished_at,
            duration_ms=duration_ms(result.started_at, result.finished_at),
            node_results=nodes, error=safe_error(result.error, workflow=True),
            created_at=result.started_at, definition_hash=definition_hash,
            outputs_stored=self.store_outputs,
        )
        record = self._bound_record(record)
        self.repository.finish(record)
        return record

    def _bound_record(self, record: ExecutionRecord) -> ExecutionRecord:
        if _size(record) <= self.history_max_bytes:
            return record
        # Preserve terminal status/timing first. No partially sliced JSON output.
        nodes = [{**item, "output": None} for item in record.node_results]
        record = replace(record, node_results=nodes, outputs_stored=False, history_truncated=True)
        if _size(record) <= self.history_max_bytes:
            return record
        # IDs are identity references: retain them exactly or omit the whole
        # nullable reference, never slice distinct IDs into the same prefix.
        if (
            record.error is not None
            and _size(replace(record, node_results=[])) > self.history_max_bytes
        ):
            record = replace(record, error={**record.error, "node_id": None})
        low, high = 0, len(nodes)
        while low < high:
            middle = (low + high + 1) // 2
            if _size(replace(record, node_results=nodes[:middle])) <= self.history_max_bytes:
                low = middle
            else:
                high = middle - 1
        return replace(record, node_results=nodes[:low])

    def recover_interrupted(self, *, now: datetime | None = None) -> int:
        count = self.repository.recover_running(now or datetime.now(UTC))
        if count:
            logger.warning("Execution recovery marked interrupted records (count=%d)", count)
        return count

    def cleanup(self, *, now: datetime | None = None) -> int:
        cutoff = (now or datetime.now(UTC)) - timedelta(days=self.retention_days)
        # One bounded batch per tick avoids retention monopolizing SQLite writes.
        count = self.repository.delete_expired(cutoff)
        if count:
            logger.info("Execution history retention removed records (count=%d)", count)
        return count
