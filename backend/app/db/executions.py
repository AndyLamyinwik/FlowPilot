import json
import sqlite3
from datetime import UTC, datetime
from uuid import UUID

from app.db.database import Database
from app.models.execution import ExecutionRecord, ExecutionStatus, TriggerType


def _record(row: sqlite3.Row) -> ExecutionRecord:
    return ExecutionRecord(
        execution_id=UUID(row["id"]),
        workflow_id=UUID(row["workflow_id"]),
        trigger_type=row["trigger_type"],
        status=row["status"],
        started_at=datetime.fromisoformat(row["started_at"]),
        finished_at=(
            datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None
        ),
        duration_ms=row["duration_ms"],
        node_results=json.loads(row["node_results"]),
        error=json.loads(row["error"]) if row["error"] else None,
        created_at=datetime.fromisoformat(row["created_at"]),
        definition_hash=row["definition_hash"],
        outputs_stored=bool(row["outputs_stored"]),
        history_truncated=bool(row["history_truncated"]),
    )


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Execution timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat()


class ExecutionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_running(
        self,
        execution_id: UUID,
        workflow_id: UUID,
        trigger_type: TriggerType,
        started_at: datetime,
        definition_hash: str,
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO workflow_executions
                    (id, workflow_id, trigger_type, status, started_at, created_at,
                     definition_hash)
                VALUES (?, ?, ?, 'running', ?, ?, ?)
                """,
                (str(execution_id), str(workflow_id), trigger_type, _utc(started_at),
                 _utc(started_at), definition_hash),
            )

    def finish(self, record: ExecutionRecord) -> None:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE workflow_executions
                SET status = ?, finished_at = ?, duration_ms = ?, node_results = ?,
                    error = ?, outputs_stored = ?, history_truncated = ?
                WHERE id = ? AND workflow_id = ? AND status = 'running'
                """,
                (record.status,
                 _utc(record.finished_at) if record.finished_at else None,
                 record.duration_ms, _json(record.node_results),
                 _json(record.error) if record.error else None,
                 int(record.outputs_stored), int(record.history_truncated),
                 str(record.execution_id), str(record.workflow_id)),
            )
            if cursor.rowcount != 1:
                raise sqlite3.DatabaseError("Execution record could not be finalized")

    def get(self, execution_id: UUID) -> ExecutionRecord | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM workflow_executions WHERE id = ?", (str(execution_id),)
            ).fetchone()
        return _record(row) if row else None

    def list_for_workflow(
        self, workflow_id: UUID, *, limit: int = 20, offset: int = 0,
        status: ExecutionStatus | None = None,
    ) -> tuple[list[ExecutionRecord], int]:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("Invalid history pagination")
        query = "workflow_id = ?"
        parameters: list[object] = [str(workflow_id)]
        if status is not None:
            query += " AND status = ?"
            parameters.append(status)
        with self.database.connect() as connection:
            total = connection.execute(
                f"SELECT count(*) FROM workflow_executions WHERE {query}", parameters
            ).fetchone()[0]
            rows = connection.execute(
                f"SELECT * FROM workflow_executions WHERE {query} "
                "ORDER BY started_at DESC, id ASC LIMIT ? OFFSET ?",
                [*parameters, limit, offset],
            ).fetchall()
        return [_record(row) for row in rows], total

    def recover_running(self, now: datetime) -> int:
        error = _json({
            "code": "EXECUTION_INTERRUPTED",
            "message": "Execution interrupted by application restart.",
            "node_id": None,
        })
        # A single startup owner must be established before this method is called.
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT id, started_at FROM workflow_executions WHERE status = 'running'"
            ).fetchall()
            for row in rows:
                started = datetime.fromisoformat(row["started_at"])
                duration = max(0, int((now - started).total_seconds() * 1000))
                connection.execute(
                    """
                    UPDATE workflow_executions SET status = 'interrupted',
                        finished_at = ?, duration_ms = ?, error = ?
                    WHERE id = ? AND status = 'running'
                    """,
                    (_utc(now), duration, error, row["id"]),
                )
        return len(rows)

    def delete_expired(self, cutoff: datetime, *, batch_size: int = 500) -> int:
        if not 1 <= batch_size <= 500:
            raise ValueError("Invalid retention batch size")
        # Bounded transactions let engine writes interleave with retention work.
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM workflow_executions WHERE id IN (
                    SELECT id FROM workflow_executions
                    WHERE status != 'running' AND finished_at IS NOT NULL
                        AND finished_at < ?
                    ORDER BY finished_at ASC LIMIT ?
                )
                """,
                (_utc(cutoff), batch_size),
            )
        return cursor.rowcount
