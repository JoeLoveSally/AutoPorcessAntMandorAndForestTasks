from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from domain_data import StepStatus


@dataclass(frozen=True, slots=True)
class StepRecord:
    run_id: str
    workflow: str
    step: str
    status: StepStatus
    updated_at: datetime
    observation_id: str | None
    detail: str | None


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS step_state (
                    run_id TEXT NOT NULL,
                    workflow TEXT NOT NULL,
                    step TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    observation_id TEXT,
                    detail TEXT,
                    PRIMARY KEY (run_id, step)
                );
                CREATE INDEX IF NOT EXISTS step_state_workflow_idx
                ON step_state(workflow, step, updated_at DESC);
                CREATE TABLE IF NOT EXISTS process_lock (
                    name TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    acquired_at TEXT NOT NULL,
                    pid INTEGER
                );
                """
            )
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(process_lock)")
            }
            if "pid" not in columns:
                connection.execute("ALTER TABLE process_lock ADD COLUMN pid INTEGER")

    def save_step(
        self,
        run_id: str,
        workflow: str,
        step: str,
        status: StepStatus,
        observation_id: str | None = None,
        detail: str | None = None,
    ) -> StepRecord:
        updated = datetime.now(timezone.utc)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO step_state
                    (run_id, workflow, step, status, updated_at, observation_id, detail)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, step) DO UPDATE SET
                    status=excluded.status,
                    updated_at=excluded.updated_at,
                    observation_id=excluded.observation_id,
                    detail=excluded.detail
                """,
                (run_id, workflow, step, status.value, updated.isoformat(), observation_id, detail),
            )
        return StepRecord(run_id, workflow, step, status, updated, observation_id, detail)

    def latest_step(self, workflow: str, step: str) -> StepRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT run_id, workflow, step, status, updated_at, observation_id, detail
                FROM step_state
                WHERE workflow=? AND step=?
                ORDER BY updated_at DESC LIMIT 1
                """,
                (workflow, step),
            ).fetchone()
        if row is None:
            return None
        return StepRecord(row[0], row[1], row[2], StepStatus(row[3]), datetime.fromisoformat(row[4]), row[5], row[6])

    def acquire_lock(self, name: str, owner: str) -> bool:
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT pid FROM process_lock WHERE name=?", (name,)
            ).fetchone()
            if existing is not None:
                pid = existing[0]
                if pid is None or _process_alive(pid):
                    return False
                connection.execute("DELETE FROM process_lock WHERE name=?", (name,))
            try:
                connection.execute(
                    "INSERT INTO process_lock(name, owner, acquired_at, pid) VALUES (?, ?, ?, ?)",
                    (name, owner, datetime.now(timezone.utc).isoformat(), os.getpid()),
                )
            except sqlite3.IntegrityError:
                return False
        return True

    def release_lock(self, name: str, owner: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM process_lock WHERE name=? AND owner=?", (name, owner))


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
