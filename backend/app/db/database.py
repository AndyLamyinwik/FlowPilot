import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class Database:
    path: Path

    def initialize(self) -> None:
        """Add missing tables and indexes without replacing existing workflow data."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY NOT NULL,
                    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
                    description TEXT,
                    definition TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_schedules (
                    workflow_id TEXT PRIMARY KEY NOT NULL
                        REFERENCES workflows(id) ON DELETE CASCADE,
                    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_error TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_executions (
                    id TEXT PRIMARY KEY NOT NULL,
                    workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
                    trigger_type TEXT NOT NULL CHECK (trigger_type IN ('manual', 'schedule')),
                    status TEXT NOT NULL CHECK (
                        status IN ('running', 'success', 'failed', 'interrupted', 'skipped')
                    ),
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    duration_ms INTEGER,
                    node_results TEXT NOT NULL DEFAULT '[]',
                    error TEXT,
                    created_at TEXT NOT NULL,
                    definition_hash TEXT NOT NULL,
                    outputs_stored INTEGER NOT NULL DEFAULT 0 CHECK (outputs_stored IN (0, 1)),
                    history_truncated INTEGER NOT NULL DEFAULT 0 CHECK (history_truncated IN (0, 1))
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_executions_workflow_started "
                "ON workflow_executions (workflow_id, started_at DESC, id ASC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_executions_status_started "
                "ON workflow_executions (status, started_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_executions_finished "
                "ON workflow_executions (finished_at)"
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                yield connection
        finally:
            connection.close()
