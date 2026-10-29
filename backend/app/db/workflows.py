import json
import sqlite3
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.db.database import Database
from app.models.workflow import WorkflowRecord


def _record(row: sqlite3.Row) -> WorkflowRecord:
    return WorkflowRecord(
        id=UUID(row["id"]),
        name=row["name"],
        description=row["description"],
        definition=json.loads(row["definition"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _definition_json(definition: dict[str, Any]) -> str:
    return json.dumps(definition, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


class WorkflowRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_all(self) -> list[WorkflowRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM workflows ORDER BY created_at DESC, id ASC"
            ).fetchall()
        return [_record(row) for row in rows]

    def get(self, workflow_id: UUID) -> WorkflowRecord | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM workflows WHERE id = ?", (str(workflow_id),)
            ).fetchone()
        return _record(row) if row is not None else None

    def create(
        self, name: str, description: str | None, definition: dict[str, Any]
    ) -> WorkflowRecord:
        workflow_id = uuid4()
        now = datetime.now(UTC)
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO workflows (id, name, description, definition, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(workflow_id),
                    name,
                    description,
                    _definition_json(definition),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
        return WorkflowRecord(workflow_id, name, description, definition, now, now)

    def update(
        self,
        workflow_id: UUID,
        name: str,
        description: str | None,
        definition: dict[str, Any],
    ) -> WorkflowRecord | None:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE workflows
                SET name = ?, description = ?, definition = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    name,
                    description,
                    _definition_json(definition),
                    datetime.now(UTC).isoformat(),
                    str(workflow_id),
                ),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM workflows WHERE id = ?", (str(workflow_id),)
            ).fetchone()
        return _record(row)

    def delete(self, workflow_id: UUID) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM workflows WHERE id = ?", (str(workflow_id),)
            )
            return cursor.rowcount > 0
