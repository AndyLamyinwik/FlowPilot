import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.db.database import Database


@dataclass(frozen=True)
class ScheduleRecord:
    workflow_id: UUID
    enabled: bool
    created_at: datetime
    updated_at: datetime
    last_error: str | None


def _record(row: sqlite3.Row) -> ScheduleRecord:
    return ScheduleRecord(
        workflow_id=UUID(row["workflow_id"]),
        enabled=bool(row["enabled"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        last_error=row["last_error"],
    )


class ScheduleRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get(self, workflow_id: UUID) -> ScheduleRecord | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM workflow_schedules WHERE workflow_id = ?", (str(workflow_id),)
            ).fetchone()
        return _record(row) if row is not None else None

    def list_enabled(self) -> list[ScheduleRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM workflow_schedules WHERE enabled = 1 ORDER BY workflow_id"
            ).fetchall()
        return [_record(row) for row in rows]

    def set_enabled(
        self, workflow_id: UUID, enabled: bool, *, last_error: str | None = None
    ) -> ScheduleRecord:
        now = datetime.now(UTC).isoformat()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO workflow_schedules
                    (workflow_id, enabled, created_at, updated_at, last_error)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(workflow_id) DO UPDATE SET
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at,
                    last_error = excluded.last_error
                """,
                (str(workflow_id), int(enabled), now, now, last_error),
            )
            row = connection.execute(
                "SELECT * FROM workflow_schedules WHERE workflow_id = ?", (str(workflow_id),)
            ).fetchone()
        return _record(row)

    def delete(self, workflow_id: UUID) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "DELETE FROM workflow_schedules WHERE workflow_id = ?", (str(workflow_id),)
            )
